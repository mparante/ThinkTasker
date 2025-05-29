import calendar
import dateutil
import msal, uuid, requests, re, math, nltk
import logging

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
from django.utils import timezone
from langdetect import detect, LangDetectException
from . import todo

TFIDF_MAX = 20.0
CF_MAX = 2.0

logger = logging.getLogger(__name__)
#nltk.download('punkt')
#nltk.download('stopwords')

def is_english(text):
    try:
        return detect(text) == 'en'
    except LangDetectException:
        return False

def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        client_id = settings.GRAPH_CLIENT_ID,
        client_credential = settings.GRAPH_CLIENT_SECRET,
        authority = settings.GRAPH_AUTHORITY,
        token_cache = cache
    )

def get_active_patterns():
    return ActionablePattern.objects.filter(is_active=True)

def login_view(request):
    return render(request, "login.html")

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

@login_required
def profile(request):
    access_token = _get_graph_token(request)
    if not access_token:
        return redirect("login")
    headers = {"Authorization": f"Bearer {access_token}"}
    graph_endpoint = "https://graph.microsoft.com/v1.0/me"
    resp = requests.get(graph_endpoint, headers=headers)
    resp.raise_for_status()
    user = resp.json()
    return render(request, "profile.html", {"user": user})

def graph_login(request):
    msal_app = _build_msal_app()
    request.session["msal_state"] = str(uuid.uuid4())
    auth_url = msal_app.get_authorization_request_url(
        scopes = settings.GRAPH_SCOPE,
        state  = request.session["msal_state"],
        redirect_uri = settings.GRAPH_REDIRECT_URI
    )
    return redirect(auth_url)

def graph_callback(request):
    if request.GET.get("state") != request.session.get("msal_state"):
        return render(request, "error.html", {"message": "State mismatch."})
    code = request.GET.get("code")
    msal_app = _build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes = settings.GRAPH_SCOPE,
        redirect_uri = settings.GRAPH_REDIRECT_URI
    )
    if "access_token" in result:
        access_token = result["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        user_resp = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        userinfo = user_resp.json()
        email = userinfo.get("mail") or userinfo.get("userPrincipalName")

        try:
            user = ThinkTaskerUser.objects.get(email=email)
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
        return render(request, "error.html", {"message": result.get("error_description")})

def _get_graph_token(request):
    token_dict = request.session.get("graph_token")
    if not token_dict:
        return None
    return token_dict.get("access_token")

def parse_iso_datetime(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        print("Error parsing date:", dt_str, e)
        return None

@login_required
def index(request):
    actionable_tasks = ExtractedTask.objects.filter(
        user=request.user
    ).filter(
        Q(email__is_actionable=True) | Q(email__isnull=True)
    ).distinct()
    todo_tasks = actionable_tasks.filter(status="Open")
    ongoing_tasks = actionable_tasks.filter(status="Ongoing")
    completed_tasks = actionable_tasks.filter(status="Completed")
    context = {
        "todo_tasks": todo_tasks,
        "ongoing_tasks": ongoing_tasks,
        "completed_tasks": completed_tasks,
    }
    return render(request, "index.html", context)

@login_required
def outlook_inbox(request):
    processed_emails = ProcessedEmail.objects.filter(user=request.user).order_by("-processed_at")
    last_synced = request.user.last_synced_datetime
    return render(request, "emails.html", {
        "processed_emails": processed_emails,
        "last_synced": last_synced,
    })

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

@login_required
def sync_emails_view(request):
    user = request.user
    access_token = _get_graph_token(request)

    last_sync = user.last_synced_datetime
    all_emails = []
    if last_sync:
        received_after = last_sync.strftime('%Y-%m-%dT%H:%M:%SZ')
        url = (
            f"https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages"
            f"?$filter=receivedDateTime ge {received_after}"
            "&$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink,importance"
            "&$top=50"
        )
        headers = {"Authorization": f"Bearer {access_token}"}
        while url:
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                break
            data = resp.json()
            all_emails.extend(data.get("value", []))
            url = data.get("@odata.nextLink", None)
    else:
        all_emails = fetch_all_emails(access_token)


    all_docs_tokens = get_reference_tokens()
    for m in all_emails:
        subject = m.get("subject", "")
        message_id = m["id"]
        pe = ProcessedEmail.objects.filter(message_id=message_id, user=user).first()
        if pe and hasattr(pe, "body_preview"):
            full_body = pe.body_preview
        else:
            full_body = fetch_full_email_body(message_id, access_token)
        combined_text = subject + " " + full_body
        if is_english(combined_text):
            all_docs_tokens.append(clean_email_text(combined_text))

    unread_emails = fetch_unread_emails(access_token)
    if not unread_emails:
        messages.info(request, "No new unread emails to process.")
        user.last_synced_datetime = timezone.now()
        user.save(update_fields=['last_synced_datetime'])
        return redirect("outlook-inbox")

    for m in unread_emails:
        subject = m.get("subject", "")
        message_id = m["id"]
        preview = m.get("bodyPreview", "")
        full_body = fetch_full_email_body(message_id, access_token)
        text_for_extraction = subject + " " + full_body
        is_flagged = m.get("flag", {}).get("flagStatus", "") == "flagged"
        is_important = m.get("importance", "") == "high"

        if not is_english(text_for_extraction):
            continue

        web_link = m.get("webLink", "")

        if ProcessedEmail.objects.filter(message_id=message_id, user=user).exists():
            continue

        actionable_patterns = extract_actionable_items(subject + " " + preview)
        actionable_list = [{"pattern": p.pattern, "priority": p.priority} for p in actionable_patterns]
        is_actionable = bool(actionable_patterns)

        pe = ProcessedEmail.objects.create(
            user=user,
            message_id=message_id,
            subject=subject,
            body_preview=preview,
            is_actionable=is_actionable,
            web_link=web_link,
            is_reference=True if is_actionable else False,
        )

        # Logs
        logger.info(
            f"ProcessedEmail created for user '{user.email}': "
            f"MessageID='{message_id}', Subject='{subject}', IsActionable={is_actionable}, "
            f"WebLink='{web_link}', IsReference={pe.is_reference}"
        )
        
        if is_actionable:
            cleaned_tokens = clean_email_text(text_for_extraction)
            terms = set(cleaned_tokens)
            tfidf_sum = 0
            cf_sum = 0
            tfidf_details = {}
            cf_details = {}

            for term in terms:
                tf = compute_tf(term, cleaned_tokens)
                idf = compute_idf(term, all_docs_tokens)
                cf = compute_cf(term, all_docs_tokens)
                ct = get_contextual_weight(term)
                tfidf = tf * idf * ct
                tfidf_sum += tfidf
                cf_sum += cf
                tfidf_details[term] = {'tf': tf, 'idf': idf, 'ct': ct, 'tfidf': tfidf}
                cf_details[term] = cf
            
            if is_flagged or is_important:
                ct += 1.0
            tfidf_norm = min((tfidf_sum * ct) / TFIDF_MAX, 1)
            cf_norm = min(cf_sum / CF_MAX, 1)
            alpha, beta = 0.7, 0.3
            score = alpha * tfidf_norm + beta * cf_norm

            deadline = extract_deadline(full_body)
            priority_label = assign_priority(score, deadline)

            # Logs
            logger.info(f"Processing email '{subject}' for user '{user.email}':")
            logger.info(f"  TF-IDF Details: {tfidf_details}")
            logger.info(f"  CF Details: {cf_details}")
            logger.info(f"  TFIDF Sum: {tfidf_sum}, CF Sum: {cf_sum}")
            logger.info(f"  TFIDF Norm: {tfidf_norm}, CF Norm: {cf_norm}")
            logger.info(f"  Score: {score}")
            logger.info(f"  Extracted Deadline: {deadline}")
            logger.info(f"  Assigned Priority: {priority_label}")

            # Create To Do task
            todo_task_id = todo.create_todo_task(access_token, subject, preview[:500], deadline)

            ExtractedTask.objects.create(
                user=user,
                email=pe,
                subject=subject,
                task_description=preview[:500],
                actionable_patterns=actionable_list,
                priority=priority_label,
                deadline=deadline,
                status="Open",
                todo_task_id=todo_task_id,
            )

        mark_email_as_read(message_id, access_token)

    user.last_synced_datetime = timezone.now()
    user.save(update_fields=['last_synced_datetime'])

    messages.success(request, "Sync completed! All unread actionable emails were processed and prioritized.")
    return redirect("outlook-inbox")

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
                    todo.mark_todo_task_completed(access_token, task.todo_task_id)
                else:
                    todo.update_todo_task(
                        access_token,
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

@login_required
def task_list(request):
    query = request.GET.get("q", "")
    tasks = ExtractedTask.objects.filter(user=request.user)
    if query:
        tasks = tasks.filter(
            Q(subject__icontains=query) |
            Q(task_description__icontains=query)
        )
    priority_order = Case(
        When(priority='Urgent', then=Value(1)),
        When(priority='Important', then=Value(2)),
        When(priority='Medium', then=Value(3)),
        When(priority='Low', then=Value(4)),
        default=Value(5),
        output_field=IntegerField()
    )
    tasks = tasks.annotate(priority_rank=priority_order).order_by('priority_rank', 'deadline', '-created_at')
    return render(request, "task_list.html", {"tasks": tasks, "query": query})

@login_required
def create_task(request):
    if request.method == "POST":
        form = ExtractedTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            task.is_actionable = True
            # To Do task creation
            access_token = _get_graph_token(request)
            todo_task_id = todo.create_todo_task(
                access_token,
                task.subject,
                task.task_description,
                task.deadline
            )
            task.todo_task_id = todo_task_id
            task.save()
            return redirect("task_list")
    else:
        form = ExtractedTaskForm()
    return render(request, "task_form.html", {"form": form})

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
                    updated_task.todo_task_id,
                    title=updated_task.subject,
                    description=updated_task.task_description,
                    due_date=updated_task.deadline,
                    status=todo_status
                )
            except Exception as e:
                logger.warning(f"Failed to sync To Do update for task {updated_task.todo_task_id}: {e}")
            updated_task.save()
            return redirect("task_list")
    else:
        form = ExtractedTaskForm(instance=task)
    return render(request, "task_form.html", {"form": form, "task": task})

@login_required
@require_POST
def delete_task(request, task_id):
    task = ExtractedTask.objects.get(id=task_id, user=request.user)
    # To Do task deletion
    access_token = _get_graph_token(request)
    if task.todo_task_id:
        todo.delete_todo_task(access_token, task.todo_task_id)
    task.delete()
    return redirect("task_list")

@login_required
def settings_view(request):
    return render(request, "settings.html")

@login_required
def help_docs(request):
    return render(request, "help_docs.html")

def clean_email_text(text):
    text = re.sub(r"(?i)(Best regards|Regards|Sent from my|Sincerely|Thanks|Thank you|Yours truly|Cheers)[\s\S]+", "", text)
    text = re.sub(r"(?i)^(hi|hello|dear|good morning|good afternoon|good evening)[^,]*,?", "", text.strip())
    tokens = word_tokenize(text.lower())
    stop_words = set(stopwords.words('english'))
    tokens = [word for word in tokens if word.isalnum() and word not in stop_words]
    return tokens

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

def add_weekdays(start, days):
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current

def first_of_next_month(dt):
    if dt.month == 12:
        return dt.replace(year=dt.year+1, month=1, day=1)
    else:
        return dt.replace(month=dt.month+1, day=1)

def extract_deadline(text, sent_date=None):
    patterns = [
        r'by ([A-Za-z]+\s\d{1,2}(?:,\s*\d{4})?)',
        r'on ([A-Za-z]+\s\d{1,2}(?:,\s*\d{4})?)',
        r'in (\d+) days?',
        r'tomorrow',
        r'today',
        r'now',
        r'next week',
        r'next month',
        r'next ([A-Za-z]+)',
    ]
    now = sent_date if sent_date is not None else timezone.now()

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue

        date_str = match.group(1) if match.groups() else match.group(0)
        try:
            date_str_lc = date_str.lower()
            if 'today' in date_str_lc or 'now' in date_str_lc:
                return now
            elif 'tomorrow' in date_str_lc:
                return add_weekdays(now, 1)
            elif 'days' in date_str_lc:
                days = int(re.findall(r'\d+', date_str)[0])
                return add_weekdays(now, days)
            elif 'next week' in date_str_lc:
                days_ahead = (0 - now.weekday() + 7) % 7 or 7
                return now + timedelta(days=days_ahead)
            elif 'next month' in date_str_lc:
                return first_of_next_month(now)
            elif pattern.startswith('next ([A-Za-z]+)'):
                weekday_str = match.group(1)
                weekdays = {day.lower(): i for i, day in enumerate(calendar.day_name)}
                if weekday_str.lower() in weekdays:
                    days_ahead = (weekdays[weekday_str.lower()] - now.weekday() + 7) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    return now + timedelta(days=days_ahead)
            else:
                deadline = dateutil.parser.parse(date_str, fuzzy=True, default=now)
                if deadline < now:
                    try:
                        deadline = deadline.replace(year=now.year + 1)
                    except Exception:
                        pass
                return deadline
        except Exception:
            continue

    return None

def assign_priority(score, extracted_deadline):
    if score >= 0.7:
        base_priority = 'Important'
    elif score >= 0.4:
        base_priority = 'Medium'
    else:
        base_priority = 'Low'

    if extracted_deadline:
        now = timezone.now()
        delta = (extracted_deadline - now).days
        
        if delta <= 3:
            return 'Urgent'
        elif 4 <= delta <= 5:
            return 'Important'
        elif delta > 30:
            return 'Low'
        else:
            return base_priority
    else:
        return base_priority

def fetch_all_emails(access_token, folder="Inbox"):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    emails = []
    url = (
        f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"
        "?$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink,importance"
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

def fetch_unread_emails(access_token, folder="Inbox"):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    emails = []
    url = (
        f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"
        "?$filter=isRead eq false"
        "&$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink,importance"
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

def fetch_full_email_body(message_id, access_token):
    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}?$select=body"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("body", {}).get("content", "")
    return ""

def mark_email_as_read(message_id, access_token):
    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "isRead": True
    }
    resp = requests.patch(url, json=payload, headers=headers)
    return resp.status_code == 200

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
