import calendar
import dateutil
import msal, uuid, requests, re, math, pickle
import logging

from django.db import IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q, Case, When, Value, IntegerField

from .models import ActionablePattern, ExtractedTask, ProcessedEmail, ThinkTaskerUser, ReferenceDocument
from .forms import ExtractedTaskForm
from datetime import datetime, timedelta
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from bs4 import BeautifulSoup
from django.utils import timezone
from langdetect import detect, LangDetectException
from . import todo, task_description
from calendar import month_name
# import nltk
# nltk.download('punkt_tab')
# nltk.download('stopwords')

TFIDF_MAX = 20.0
CF_MAX = 2.0
WORK_START = 9
WORK_END = 18

logger = logging.getLogger(__name__)

priority_order = Case(
    When(priority='Urgent', then=Value(1)),
    When(priority='Important', then=Value(2)),
    When(priority='Medium', then=Value(3)),
    When(priority='Low', then=Value(4)),
    default=Value(5),
    output_field=IntegerField()
)

status_order = Case(
    When(status='Open', then=Value(1)),
    When(status='Ongoing', then=Value(2)),
    When(status='Completed', then=Value(3)),
    default=Value(4),
    output_field=IntegerField()
)

def is_english(text):
    try:
        return detect(text) == 'en'
    except LangDetectException:
        return False
    
# View to render the login page
def login_view(request):
    return render(request, "login.html")

# View to handle user registration
def register(request):
    if request.method == "POST":
        email = request.POST.get("email")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        department = request.POST.get("department")
        username = email

        if ThinkTaskerUser.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect("login")
        
        user = ThinkTaskerUser.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            department=department,
            is_active=True,
            is_approved=False,
        )
        user.save()

        messages.success(request, "Registration successful! Await admin approval.")
        return redirect("login")
    return redirect("login")

# Pickled MSAL token cache to persist across requests used in graph_login and graph_callback functions
def _load_token_cache(session):
    cache = msal.SerializableTokenCache()
    if session.get("token_cache"):
        cache.deserialize(session["token_cache"])
    return cache

# Save the MSAL token cache to the session used in graph_login and graph_callback functions
def _save_token_cache(session, cache):
    if cache.has_state_changed:
        session["token_cache"] = cache.serialize()

# Helper function to build the MSAL ConfidentialClientApplication instance for graph_login and graph_callback functions
def _build_msal_app(token_cache):
    return msal.ConfidentialClientApplication(
        client_id=settings.GRAPH_CLIENT_ID,
        client_credential=settings.GRAPH_CLIENT_SECRET,
        authority=settings.GRAPH_AUTHORITY,
        token_cache=token_cache
    )

# Function to initiate Microsoft Graph login flow
def graph_login(request):
    token_cache = _load_token_cache(request.session)
    msal_app = _build_msal_app(token_cache)
    request.session["msal_state"] = str(uuid.uuid4())
    auth_url = msal_app.get_authorization_request_url(
        scopes=settings.GRAPH_SCOPE,
        state=request.session["msal_state"],
        redirect_uri=settings.GRAPH_REDIRECT_URI,
    )
    _save_token_cache(request.session, token_cache)
    return redirect(auth_url)

# Function to handle the callback from Microsoft Graph after user authentication
def graph_callback(request):
    if request.GET.get("state") != request.session.get("msal_state"):
        return render(request, "error.html", {"message": "State mismatch."})
    code = request.GET.get("code")
    token_cache = _load_token_cache(request.session)
    msal_app = _build_msal_app(token_cache)
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=settings.GRAPH_SCOPE,
        redirect_uri=settings.GRAPH_REDIRECT_URI,
    )
    _save_token_cache(request.session, token_cache)
    if "access_token" in result:
        access_token = result["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        user_resp = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        userinfo = user_resp.json()
        email = userinfo.get("mail") or userinfo.get("userPrincipalName")

        try:
            user = ThinkTaskerUser.objects.get(email=email)
            user.refresh_from_db() # Refresh user from DB on login callback when registering --force reload
            if not user.is_approved:
                messages.error(request, "Your account is not approved by admin yet.")
                return redirect("login")
            login(request, user)
            request.session["graph_token"] = result
            return redirect("dashboard")
        except ThinkTaskerUser.DoesNotExist:
            return render(request, "login.html", {
                "show_register": True,
                "ms_email": email,
                "ms_first_name": userinfo.get("givenName", ""),
                "ms_last_name": userinfo.get("surname", ""),
            })
    else:
        return render(request, "dashboard", {"message": result.get("error_description")})

# Helper function to get the MS Graph access token from the session or acquire it if not present
# This function is called at sync_emails_view and CRUD operations for tasks
def _get_graph_token(request):
    token_dict = request.session.get("graph_token")
    if token_dict and "access_token" in token_dict:
        access_token = token_dict["access_token"]
        if access_token and "." in access_token:
            return access_token

    # Fallback: silent refresh using MSAL cache
    token_cache = _load_token_cache(request.session)
    msal_app = _build_msal_app(token_cache)
    email = getattr(request.user, "email", None)
    if not email:
        return None
    accounts = msal_app.get_accounts(username=email)
    if not accounts:
        return None
    result = msal_app.acquire_token_silent(settings.GRAPH_SCOPE, accounts[0])
    _save_token_cache(request.session, token_cache)
    if not result or "access_token" not in result:
        return None
    request.session["graph_token"] = result
    return result["access_token"]

# Helper function to get calendar weeks for the calendar view
# This function is called at index view
def get_calendar_weeks(user, year, month):
    tasks = ExtractedTask.objects.filter(
        user=user,
        deadline__year=year,
        deadline__month=month,
        status__in=["Open", "Ongoing"]
    )
    # Count tasks per day
    task_counts = {}
    for t in tasks:
        d = t.deadline
        task_counts[d] = task_counts.get(d, 0) + 1

    # Decide fullness per day
    FULL_THRESHOLD = 8
    cal = calendar.Calendar(firstweekday=6)
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        week_list = []
        for day in week:
            count = task_counts.get(day, 0)
            week_list.append({
                'day': day.day if day.month == month else '',
                'date': day,
                'task_count': count,
                'is_full': count >= FULL_THRESHOLD,
                'is_busy': count >= FULL_THRESHOLD // 2 and count < FULL_THRESHOLD,
                'is_free': 0 < count < FULL_THRESHOLD // 2,
            })
        weeks.append(week_list)
    return weeks

# View for the main dashboard
@login_required
def index(request):
    user = ThinkTaskerUser.objects.get(pk=request.user.pk)
    needs_first_sync = not bool(user.last_synced_datetime)
    #Logging
    print("last_synced_datetime =", user.last_synced_datetime)
    print("needs_first_sync =", needs_first_sync)

    query = request.GET.get("q", "")
    base_qs = ExtractedTask.objects.filter(user=request.user).annotate(
        priority_rank=priority_order, 
        status_rank=status_order,
        is_urgent=Case(
            When(priority_rank=1, then=Value(True)),
            default=Value(False),
            output_field=IntegerField()),
        is_urgent_and_delayed=Case(
            When(priority_rank=1, is_delayed=True, then=Value(True)),
            default=Value(False),
            output_field=IntegerField()),)

    # For Task List View
    all_tasks = base_qs
    if query:
        all_tasks = all_tasks.filter(Q(subject__icontains=query) | Q(task_description__icontains=query))
    all_tasks = all_tasks.order_by(
        '-is_urgent_and_delayed',
        '-is_delayed',
        '-is_urgent',
        'priority_rank', 
        'deadline', 
        'status_rank')
    active_tasks = all_tasks.exclude(status="Completed").order_by(
        '-is_urgent_and_delayed',
        '-is_delayed',
        '-is_urgent',
        'priority_rank', 
        'deadline', 
        'status_rank')

    # For Kanban View
    todo_tasks = base_qs.filter(status="Open").order_by(
        '-is_urgent_and_delayed',
        '-is_delayed',
        '-is_urgent',
        'priority_rank', 
        'deadline', 
        'status_rank')
    
    ongoing_tasks = base_qs.filter(status="Ongoing").order_by(
        '-is_urgent_and_delayed',
        '-is_delayed',
        '-is_urgent',
        'priority_rank', 
        'deadline', 
        'status_rank')
    completed_tasks = base_qs.filter(status="Completed").order_by(
        '-is_urgent_and_delayed',
        '-is_delayed',
        '-is_urgent',
        'priority_rank', 
        'deadline', 
        'status_rank')
    
    for task in active_tasks:
        task.is_delayed = task.deadline and task.deadline < timezone.localdate()
        task.save(update_fields=['is_delayed'])

    # For Calendar View
    today = timezone.localtime(timezone.now())
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    calendar_weeks = get_calendar_weeks(request.user, year, month)
    has_tasks = any(any(day['task_count'] > 0 for day in week) for week in calendar_weeks)

    return render(request, "dashboard.html", {
        # For Sync Status
        'needs_first_sync': needs_first_sync,
        # For Kanban View
        "todo_tasks": todo_tasks,
        "ongoing_tasks": ongoing_tasks,
        "completed_tasks": completed_tasks,
        # For Task List View
        "all_tasks": all_tasks,
        "active_tasks": active_tasks,
        "query": query,
        # For Calendar View
        'calendar_weeks': calendar_weeks,
        'year': year,
        'month': month,
        'month_name': month_name[month],
        'today': today,
        'has_tasks': has_tasks,
    })

# View to get the tasks by date for the calendar view
@login_required
def tasks_by_date(request):
    date_str = request.GET.get('date')

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        print("Invalid date format at tasks_by_date")
    
    tasks = ExtractedTask.objects.filter(
        user=request.user, 
        deadline=date_obj,
        status__in=["Open", "Ongoing"]
    ).order_by('priority', 'deadline')

    result = [{
        'id': t.id,
        'subject': t.subject,
        'priority': t.priority,
        'task_description': t.task_description,
        'deadline': t.deadline.strftime('%Y-%m-%d') if t.deadline else None,
    } for t in tasks]
    
    return JsonResponse({'tasks': result})

# Helper function to fetch full email body from the user's inbox
# This function is called at sync_emails_view
def fetch_full_email_body(message_id, access_token):
    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}?$select=body"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("body", {}).get("content", "")
    return ""

# Helper function to fetch all emails from the user's inbox
# This function is called at sync_emails_view
def fetch_all_emails(access_token, folder="Inbox"):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    emails = []
    url = (
        f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"
        "?$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink,importance,toRecipients"
        "&$top=50"
    )
    while url:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            break
        data = resp.json()
        emails.extend(data.get("value", []))
        url = data.get("@odata.nextLink", None)
    return emails

# This function is called at sync_emails_view to mark emails as read.
def batch_mark_emails_as_read(message_ids, access_token):
    url_base = "https://graph.microsoft.com/v1.0/me/messages/"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    for msg_id in message_ids:
        url = url_base + msg_id
        resp = requests.patch(url, headers=headers, json={"isRead": True})
        if resp.status_code not in (200, 204):
            print(f"Failed to mark {msg_id} as read:", resp.text)

# Helper function to clean all fetched emails from the user's inbox
# This function is called at sync_emails_view and fetch_full_email_body
def clean_email_text(text):
    text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    text = re.sub(r"(?i)(Best regards|Regards|BR|Sent from my|Sincerely|Thanks|Thank you|Yours truly|Cheers)[\s\S]+", "", text)
    text = re.sub(r"(?i)^(hi|hello|dear|good morning|good afternoon|good evening)[^,]*,?", "", text.strip())
    tokens = word_tokenize(text.lower())
    stop_words = set(stopwords.words('english'))
    tokens = [word for word in tokens if word.isalnum() and word not in stop_words]
    return tokens

# Function to check if a text is in English
# This function is called at sync_emails_view
def get_reference_tokens():
    references = ReferenceDocument.objects.all()
    all_tokens = []
    for ref in references:
        combined = (ref.subject or "") + " " + ref.body
        if not is_english(combined):
            continue
        if ref.tokens:
            all_tokens.append(ref.tokens)
        else:
            tokens = clean_email_text(combined)
            all_tokens.append(tokens)
    
    processed_refs = ProcessedEmail.objects.filter(is_reference=True)
    for pe in processed_refs:
        combined = (pe.subject or "") + " " + (pe.body_preview or "")
        if is_english(combined):
            tokens = clean_email_text(combined)
            all_tokens.append(tokens)
    return all_tokens

def compute_tf(term, doc_tokens):
    count = doc_tokens.count(term)
    return 1 + math.log10(count) if count > 0 else 0

def compute_idf(term, all_docs_tokens):
    N = len(all_docs_tokens)
    df = sum(1 for tokens in all_docs_tokens if term in tokens)
    if df == 0:
        return 0
    return math.log10(N / df)

def compute_cf(term, all_docs_tokens):
    N = len(all_docs_tokens)
    count = sum(tokens.count(term) for tokens in all_docs_tokens)
    return count / N if N > 0 else 0

def get_contextual_weight(term):
    high_priority_terms = {'urgent', 'ASAP', 'emergency', 'field issue', 'escalate', 'critical', 'immediate attention'}
    return 2.0 if term in high_priority_terms else 1.0

# Helper function to fetch all emails from the user's inbox
# This function is called at sync_emails_view
def extract_actionable_items(text):
    patterns = ActionablePattern.objects.filter(is_active=True)
    found_patterns = []
    for pattern in patterns:
        if pattern.pattern_type == "word":
            if re.search(rf"\b{re.escape(pattern.pattern)}\b", text, re.IGNORECASE):
                found_patterns.append(pattern)
        elif pattern.pattern_type == "phrase":
            if pattern.pattern.lower() in text.lower():
                found_patterns.append(pattern)
        elif pattern.pattern_type == "regex":
            if re.search(pattern.pattern, text, re.IGNORECASE):
                found_patterns.append(pattern)
    return found_patterns

# Helper function called at sync_emails_view to parse ISO 8601 datetime strings
def parse_iso_datetime(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        print("Error parsing date:", dt_str, e)
        return None

# Helper function of extract_deadline, assign_deadline_and_priority_batch, and get_next_available_hour to add weekdays to a given date
def add_weekdays(start, days):
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current

# Helper function of extract_deadline to get the first day of the next month
def first_of_next_month(dt):
    if dt.month == 12:
        return dt.replace(year=dt.year+1, month=1, day=1)
    else:
        return dt.replace(month=dt.month+1, day=1)

# Function to extract deadlines from text, with support for various formats and relative dates
# This function is called at sync_emails_view
def extract_deadline(text, sent_date=None):
    import re, calendar, dateutil
    from datetime import timedelta
    from django.utils import timezone

    patterns = [
        r'\bby ([A-Za-z]+\s\d{1,2}(?:,\s*\d{4})?)',
        r'\bon ([A-Za-z]+\s\d{1,2}(?:,\s*\d{4})?)',
        r'\bin (\d+) days?',
        r'\b(tomorrow|today|now|next week|next month|next [A-Za-z]+)\b',
        r'(\d{4}[\/.-]\d{1,2}[\/.-]\d{1,2})',         # 2025/06/06 or 2025.06.06
        r'(\d{1,2}[\/.-]\d{1,2}[\/.-]\d{4})',         # 06/24/2025 or 06.24.2025
        r'(\d{1,2}:\d{2}(?: ?[APMapm]{2})?)',         # 10:00, 3:00 PM
        r'(\d{1,2} [A-Za-z]+ \d{4})',                 # 6 June 2025
        r'([A-Za-z]+ \d{1,2},? \d{4})',               # June 6, 2025
    ]
    now = sent_date if sent_date else timezone.now().date()

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            date_str = match.group(1) if match.groups() else match.group(0)
            date_str = date_str.strip()
            try:
                # Always parse with dayfirst=False (US style) MM/DD/YYYY
                deadline = dateutil.parser.parse(date_str, default=timezone.now(), fuzzy=True, dayfirst=False)
                return deadline.date().strftime('%Y-%m-%d')
            except Exception:
                pass

            lc = date_str.lower()
            if 'today' in lc or 'now' in lc:
                return now.strftime('%Y-%m-%d')
            elif 'tomorrow' in lc:
                dt = now + timedelta(days=1)
                return dt.strftime('%Y-%m-%d')
            elif 'days' in lc:
                days = int(re.findall(r'\d+', date_str)[0])
                dt = now + timedelta(days=days)
                return dt.strftime('%Y-%m-%d')
            elif 'next week' in lc:
                days_ahead = (0 - now.weekday() + 7) % 7 or 7
                dt = now + timedelta(days=days_ahead)
                return dt.strftime('%Y-%m-%d')
            elif 'next month' in lc:
                if now.month == 12:
                    first = now.replace(year=now.year + 1, month=1, day=1)
                else:
                    first = now.replace(month=now.month + 1, day=1)
                return first.strftime('%Y-%m-%d')
            elif pattern.startswith('next ([A-Za-z]+)'):
                weekday_str = match.group(1)
                weekdays = {day.lower(): i for i, day in enumerate(calendar.day_name)}
                if weekday_str.lower() in weekdays:
                    days_ahead = (weekdays[weekday_str.lower()] - now.weekday() + 7) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    dt = now + timedelta(days=days_ahead)
                    return dt.strftime('%Y-%m-%d')
    return None

# Function to fetch all unread emails from the user's inbox
# This is the core function of ThinkTasker to sync emails
@login_required
def sync_emails_view(request):
    user = request.user
    access_token = _get_graph_token(request)
    now = timezone.localdate()
    logger = logging.getLogger(__name__)

    # Check if user has a valid access token
    print("Access token:", access_token)
    if not access_token:
        logger.warning("User access token invalid or missing; forcing logout.")
        messages.error(request, "Your Microsoft login session expired. Please sign in again.")
        return redirect("login")

    # Fetch all emails (new since last sync or all if no sync yet)
    last_sync = user.last_synced_datetime
    all_emails = []
    if last_sync:
        received_after = last_sync.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            f"https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages"
            f"?$filter=receivedDateTime ge {received_after}"
            "&$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink,importance,toRecipients"
            "&$top=50"
        )
        headers = {"Authorization": f"Bearer {access_token}"}
        while url:
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch emails: {resp.status_code} {resp.text}")
                break
            data = resp.json()
            all_emails.extend(data.get("value", []))
            url = data.get("@odata.nextLink", None)
    else:
        all_emails = fetch_all_emails(access_token)

    # Build reference tokens from known docs and emails
    all_docs_tokens = get_reference_tokens()
    for m in all_emails:
        subject = m.get("subject", "")
        message_id = m["id"]
        pe = ProcessedEmail.objects.filter(message_id=message_id, user=user).first()
        full_body = pe.body_preview if pe and hasattr(pe, "body_preview") else fetch_full_email_body(message_id, access_token)
        combined_text = subject + " " + full_body
        if is_english(combined_text):
            all_docs_tokens.append(clean_email_text(combined_text))

    # Fetch all unread emails with paging
    unread_emails = []
    url = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages"
        "?$filter=isRead eq false"
        "&$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink,importance,toRecipients"
        "&$top=50"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    while url:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch unread emails: {resp.status_code} {resp.text}")
            break
        data = resp.json()
        unread_emails.extend(data.get("value", []))
        url = data.get("@odata.nextLink", None)

    if not unread_emails:
        user.last_synced_datetime = timezone.now()
        user.save(update_fields=['last_synced_datetime'])
        return JsonResponse({
            "success": True,
            "new_tasks": [],
            "last_synced": timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M"),
            "message": "No new unread emails to process."
        })

    actionable_new_tasks = []
    message_ids_to_mark_read = []

    for m in unread_emails:
        subject = m.get("subject", "")
        message_id = m["id"]
        preview = m.get("bodyPreview", "")
        full_body = fetch_full_email_body(message_id, access_token)
        text_for_extraction = subject + " " + full_body
        # Check if the email is flagged or marked as important -- helps prioritize
        is_flagged = m.get("flag", {}).get("flagStatus", "") == "flagged"
        is_important = m.get("importance", "") == "high"
        # Used to check if user is a recipient of the email or just a CC
        to_recipients = [
            r.get("emailAddress", {}).get("address", "").lower()
            for r in m.get("toRecipients", [])
        ]
        web_link = m.get("webLink", "")

        received_datetime = parse_iso_datetime(m.get("receivedDateTime"))

        # Check if the email is in English and if the user is a recipient -- helps filter out mails to process
        if not is_english(text_for_extraction): continue
        if user.email.lower() not in to_recipients: continue

        # Extract actionable patterns from the email subject and preview
        actionable_patterns = extract_actionable_items(subject + " " + preview)
        is_actionable = bool(actionable_patterns)

        # If no actionable patterns found, skip this email
        if not is_actionable: continue

        cleaned_tokens = clean_email_text(text_for_extraction)
        terms = set(cleaned_tokens)
        tfidf_sum, cf_sum, ct = 0, 0, 1.0
        # Compute TF-IDF and contextual weights for the terms
        for term in terms:
            tf = compute_tf(term, cleaned_tokens)
            idf = compute_idf(term, all_docs_tokens)
            cf = compute_cf(term, all_docs_tokens)
            ct = max(ct, get_contextual_weight(term))
            tfidf_sum += tf * idf * ct
            cf_sum += cf
        # Additional contextual weight for flagged or important emails -- urgent tasks often tagged as flagged or important
        if is_flagged or is_important:
            ct += 1.0
        # Normalize the scores
        tfidf_norm = min((tfidf_sum * ct) / TFIDF_MAX, 1)
        cf_norm = min(cf_sum / CF_MAX, 1)
        alpha, beta = 0.7, 0.3
        score = alpha * tfidf_norm + beta * cf_norm

        extracted_deadline = extract_deadline(full_body, sent_date=received_datetime)
        extracted_deadline_date = None
        if extracted_deadline:
            extracted_deadline_date = datetime.strptime(extracted_deadline, "%Y-%m-%d").date()
            days_from_now = (extracted_deadline_date - now).days
        else:
            days_from_now = None

        if (score >= 0.75) or (days_from_now is not None and days_from_now <= 3):
            assigned_priority = "Urgent"
            assigned_deadline = extracted_deadline_date or (now + timedelta(days=3))
        elif (score >= 0.5) or (days_from_now is not None and 4 <= days_from_now <= 5):
            assigned_priority = "Important"
            assigned_deadline = extracted_deadline_date or (now + timedelta(days=5))
        elif (score > 0.25):
            assigned_priority = "Medium"
            assigned_deadline = extracted_deadline_date or (now + timedelta(days=7))
        else:
            assigned_priority = "Low"
            assigned_deadline = extracted_deadline_date or (now + timedelta(days=7))

        actionable_new_tasks.append({
            "subject": subject,
            "body": full_body,
            "preview": preview,
            "score": score,
            "actionable_patterns": [{"pattern": p.pattern, "priority": p.priority} for p in actionable_patterns],
            "priority": assigned_priority,
            "deadline": assigned_deadline,
            "message_id": message_id,
            "web_link": web_link,
            "to_recipients": to_recipients,
            "raw_email": m,
        })
        message_ids_to_mark_read.append(message_id)

    # Mark all processed emails as read
    if message_ids_to_mark_read:
        batch_mark_emails_as_read(message_ids_to_mark_read, access_token)

    task_objs = []

    for task in actionable_new_tasks:
        try:
            pe, created = ProcessedEmail.objects.get_or_create(
                user=user,
                message_id=task["message_id"],
                defaults={
                    "subject": task["subject"],
                    "body_preview": task["preview"],
                    "is_actionable": True,
                    "web_link": task["web_link"],
                    "is_reference": True,
                    "to_recipients": task["to_recipients"],
                }
            )
        except IntegrityError:
            logger.warning(f"ProcessedEmail for {task['message_id']} already exists (race condition). Skipping.")
            continue

        if created:
            try:
                todo_task_id, todo_list_id = todo.create_todo_task(
                    access_token,
                    task["subject"],
                    task["preview"][:500],
                    assigned_deadline
                )
            except Exception as e:
                logger.error(f"Failed to create To Do task for {task['subject']}: {e}")
                todo_task_id, todo_list_id = None, None

            et = ExtractedTask.objects.create(
                user=user,
                email=pe,
                subject=task["subject"],
                task_description=task_description.extract_task_from_email(task["body"]),
                actionable_patterns=task["actionable_patterns"],
                priority=task["priority"],
                deadline=task["deadline"],
                status="Open",
                todo_task_id=todo_task_id,
                todo_list_id=todo_list_id,
            )
            logger.info(f"Created ExtractedTask {et.id} for email {task['message_id']}")
            task_objs.append({
                "id": et.id,
                "subject": et.subject,
                "task_description": et.task_description,
                "priority": et.priority,
                "deadline": et.deadline,
                "status": et.status,
            })
        else:
            logger.info(f"Email {task['message_id']} already processed, skipping task creation.")

    # Update last synced date
    now_str = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")
    user.last_synced_datetime = timezone.now()
    user.save(update_fields=['last_synced_datetime'])

    return JsonResponse({
        "success": True,
        "new_tasks": task_objs,
        "last_synced": now_str,
    })

# View to create a new task
@login_required
def create_task(request):
    if request.method == "POST":
        form = ExtractedTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            task.is_actionable = True
            access_token = _get_graph_token(request)
            
            todo_task_id, todo_list_id = todo.create_todo_task(
                access_token,
                task.subject,
                task.task_description,
                task.deadline
            )
            task.todo_task_id = todo_task_id
            task.todo_list_id = todo_list_id
            task.save()
            messages.success(request, "Task added successfully!")

            view = request.POST.get("view", "kanban")
            return redirect(f"/dashboard/?view={view}")
    else:
        return redirect("dashboard")

# View to edit an existing task
@login_required
def edit_task(request, task_id):
    task = get_object_or_404(ExtractedTask, pk=task_id, user=request.user)
    if request.method == "POST":
        form = ExtractedTaskForm(request.POST, instance=task)
        if form.is_valid():
            updated_task = form.save(commit=False)
            access_token = _get_graph_token(request)
            
            todo_status_map = {
                "open": "notStarted",
                "ongoing": "inProgress",
                "completed": "completed"
            }
            todo_status = todo_status_map.get(updated_task.status.lower(), "notStarted")
            try:
                todo.update_todo_task(
                    access_token,
                    task.todo_list_id,
                    task.todo_task_id,
                    title=updated_task.subject,
                    description=updated_task.task_description,
                    due_date=updated_task.deadline,
                    status=todo_status
                )
            except Exception as e:
                logger.warning(f"Failed to sync To Do update for task {updated_task.todo_task_id}: {e}")
            updated_task.save()
            messages.success(request, "Task updated!")

            view = request.POST.get("view", "kanban")
            return redirect(f"/dashboard/?view={view}")
    else:
        return redirect("dashboard")

# View to delete a task
@login_required
@require_POST
def delete_task(request, task_id):
    task = ExtractedTask.objects.get(id=task_id, user=request.user)
    # To Do task deletion
    access_token = _get_graph_token(request)
    
    if task.todo_task_id:
        todo.delete_todo_task(access_token, task.todo_list_id, task.todo_task_id)
    task.delete()
    messages.success(request, "Task deleted.")
    
    view = request.POST.get("view", "kanban")
    return redirect(f"/dashboard/?view={view}")

# View to update the task status
@csrf_exempt
@login_required
def update_task_status(request):
    if request.method == "POST":
        task_id = request.POST.get("task_id")
        new_status = request.POST.get("new_status")
        try:
            task = ExtractedTask.objects.get(id=task_id, user=request.user)
            task.status = new_status
            task.save()
            todo_status_map = {
                "open": "notStarted",
                "ongoing": "inProgress",
                "completed": "completed"
            }
            todo_status = todo_status_map.get(new_status.lower(), "notStarted")
            access_token = _get_graph_token(request)

            if task.todo_task_id:
                if todo_status == "completed":
                    todo.mark_todo_task_completed(access_token, task.todo_list_id, task.todo_task_id)
                else:
                    todo.update_todo_task(
                        access_token,
                        task.todo_list_id,
                        task.todo_task_id,
                        title=task.subject,
                        description=task.task_description,
                        due_date=task.deadline,
                        status=todo_status
                    )
            return JsonResponse({"success": True})
        except ExtractedTask.DoesNotExist:
            return JsonResponse({"success": False, "error": "Task not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})

# View to get all tasks in JSON format at Kanban board
@login_required
def all_tasks_json(request):
    tasks = ExtractedTask.objects.filter(user=request.user)
    priority_order = {"Urgent": 1, "Important": 2, "Medium": 3, "Low": 4}
    result = []
    for t in tasks:
        result.append({
            "id": t.id,
            "subject": t.subject,
            "description": t.task_description,
            "priority": t.priority,
            "status": t.status,
            "deadline": t.deadline.strftime('%Y-%m-%d') if t.deadline else None,
            "web_link": t.email.web_link if t.email else "",
            "is_delayed": t.is_delayed,
            
        })

    def sort_key(x):
        priority = x["priority"] or "Medium"
        is_urgent = priority.lower() == "urgent"
        is_delayed = x["is_delayed"]
        # Sort order:
        # 1. Urgent & Delayed
        # 2. Delayed
        # 3. Urgent
        # 4. Priority (Important > Medium > Low)
        # 5. Earliest Deadline
        return (
            -(is_urgent and is_delayed),      # True (1) sorts before False (0)
            -bool(is_delayed),                # Delayed next
            -is_urgent,                       # Urgent next
            priority_order.get(priority, 5),  # Then by priority value
            x["deadline"] or "9999-12-31",    # Earliest deadline first
        )

    result.sort(key=sort_key)
    return JsonResponse({"tasks": result})

# View to delete all completed tasks
@require_POST
@login_required
def delete_completed_tasks(request):
    ExtractedTask.objects.filter(user=request.user, status="Completed").delete()
    return JsonResponse({'success': True})