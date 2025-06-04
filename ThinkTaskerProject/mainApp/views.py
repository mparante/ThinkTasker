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
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Case, When, Value, IntegerField

from .models import ActionablePattern, ExtractedTask, ProcessedEmail, ThinkTaskerUser, ReferenceDocument
from .forms import ExtractedTaskForm
from datetime import datetime, timedelta
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from bs4 import BeautifulSoup
from django.utils import timezone
from langdetect import detect, LangDetectException
from collections import defaultdict
from . import todo, task_description, read_email

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
    query = request.GET.get("q", "")
    base_qs = ExtractedTask.objects.filter(user=request.user).annotate(priority_rank=priority_order, status_rank=status_order)

    all_tasks = base_qs
    if query:
        all_tasks = all_tasks.filter(Q(subject__icontains=query) | Q(task_description__icontains=query))
    all_tasks = all_tasks.order_by('priority_rank', 'status_rank', 'deadline')

    todo_tasks = base_qs.filter(status="Open").order_by('priority_rank', 'deadline')
    ongoing_tasks = base_qs.filter(status="Ongoing").order_by('priority_rank', 'deadline')
    completed_tasks = base_qs.filter(status="Completed").order_by('priority_rank', 'deadline')

    return render(request, "dashboard.html", {
        "todo_tasks": todo_tasks,
        "ongoing_tasks": ongoing_tasks,
        "completed_tasks": completed_tasks,
        "all_tasks": all_tasks,
        "query": query,
    })

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
    now = timezone.localtime(timezone.now())
    today = now.date()

    # Update overdue tasks to next available hour if date is less than today
    overdue_tasks = ExtractedTask.objects.filter(
        user=user,
        status__in=["Open", "Ongoing"],
        deadline__date__lt=today
    ).order_by('deadline')

    if overdue_tasks:
        assign_deadline_and_priority_batch(user, overdue_tasks, now=now)

    last_sync = user.last_synced_datetime
    all_emails = []
    if last_sync:
        received_after = last_sync.strftime("%Y-%m-%d %H:%M")
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
        full_body = pe.body_preview if pe and hasattr(pe, "body_preview") else fetch_full_email_body(message_id, access_token)
        combined_text = subject + " " + full_body
        if is_english(combined_text):
            all_docs_tokens.append(clean_email_text(combined_text))

    unread_emails = fetch_unread_emails(access_token)
    if not unread_emails:
        messages.info(request, "No new unread emails to process.")
        user.last_synced_datetime = timezone.now()
        user.save(update_fields=['last_synced_datetime'])
        return redirect("outlook-inbox")

    actionable_new_tasks = []
    message_ids_to_mark_read = []

    for m in unread_emails:
        subject = m.get("subject", "")
        message_id = m["id"]
        preview = m.get("bodyPreview", "")
        full_body = fetch_full_email_body(message_id, access_token)
        text_for_extraction = subject + " " + full_body
        is_flagged = m.get("flag", {}).get("flagStatus", "") == "flagged"
        is_important = m.get("importance", "") == "high"
        to_recipients = [
            r.get("emailAddress", {}).get("address", "").lower()
            for r in m.get("toRecipients", [])
        ]
        web_link = m.get("webLink", "")
        if not is_english(text_for_extraction): continue
        if user.email.lower() not in to_recipients: continue
        if ProcessedEmail.objects.filter(message_id=message_id, user=user).exists(): continue

        actionable_patterns = extract_actionable_items(subject + " " + preview)
        is_actionable = bool(actionable_patterns)
        if is_actionable:
            cleaned_tokens = clean_email_text(text_for_extraction)
            terms = set(cleaned_tokens)
            tfidf_sum, cf_sum, ct = 0, 0, 1.0
            for term in terms:
                tf = compute_tf(term, cleaned_tokens)
                idf = compute_idf(term, all_docs_tokens)
                cf = compute_cf(term, all_docs_tokens)
                ct = max(ct, get_contextual_weight(term))
                tfidf_sum += tf * idf * ct
                cf_sum += cf
            if is_flagged or is_important:
                ct += 1.0
            tfidf_norm = min((tfidf_sum * ct) / TFIDF_MAX, 1)
            cf_norm = min(cf_sum / CF_MAX, 1)
            alpha, beta = 0.7, 0.3
            score = alpha * tfidf_norm + beta * cf_norm

            extracted_deadline = extract_deadline(full_body, sent_date=parse_iso_datetime(m.get("receivedDateTime")))
            actionable_new_tasks.append({
                "subject": subject,
                "body": full_body,
                "preview": preview,
                "score": score,
                "actionable_patterns": [{"pattern": p.pattern, "priority": p.priority} for p in actionable_patterns],
                "priority": (
                    "Urgent" if score >= 0.7 else
                    "Important" if score >= 0.4 else
                    "Medium" if score >= 0.2 else
                    "Low"
                ),
                "extracted_deadline": extracted_deadline,
                "message_id": message_id,
                "web_link": web_link,
                "to_recipients": to_recipients,
                "raw_email": m,
            })
            message_ids_to_mark_read.append(message_id)

    assign_deadline_and_priority_batch(user, actionable_new_tasks)
    task_objs = []
    for task in actionable_new_tasks:

        pe = ProcessedEmail.objects.create(
            user=user,
            message_id=task["message_id"],
            subject=task["subject"],
            body_preview=task["preview"],
            is_actionable=True,
            web_link=task["web_link"],
            is_reference=True,
            to_recipients=task["to_recipients"],
        )
        todo_task_id, todo_list_id = todo.create_todo_task(
            access_token, task["subject"], task["preview"][:500], task["assigned_deadline"]
        )
        et = ExtractedTask.objects.create(
            user=user,
            email=pe,
            subject=task["subject"],
            task_description=task_description.extract_task_from_email(clean_email_text(task["body"])),
            actionable_patterns=task["actionable_patterns"],
            priority=task["priority"],
            deadline=task["assigned_deadline"],
            status="Open",
            todo_task_id=todo_task_id,
            todo_list_id=todo_list_id,
        )
        task_objs.append({
            "id": et.id,
            "subject": et.subject,
            "task_description": et.task_description,
            "priority": et.priority,
            "deadline": et.deadline,
            "status": et.status,
        })

    # Batch mark all processed emails as read
    if message_ids_to_mark_read:
        read_email.batch_mark_emails_as_read(message_ids_to_mark_read, access_token)

    # Update last synced date
    now_str = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")
    user.last_synced_datetime = timezone.now()
    user.save(update_fields=['last_synced_datetime'])
    # Return JSON for AJAX update
    return JsonResponse({
        "success": True,
        "new_tasks": task_objs,
        "last_synced": now_str,
    })

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

# @login_required
# def task_list(request):
#     query = request.GET.get("q", "")
#     tasks = ExtractedTask.objects.filter(user=request.user)
#     if query:
#         tasks = tasks.filter(
#             Q(subject__icontains=query) |
#             Q(task_description__icontains=query)
#         )
#     tasks = tasks.annotate(priority_rank=priority_order).order_by('priority_rank', 'deadline', '-created_at')
#     return render(request, "task_list.html", {"tasks": tasks, "query": query})

@login_required
def create_task(request):
    if request.method == "POST":
        form = ExtractedTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            task.is_actionable = True
            
            # Use user-set deadline if provided, else auto-assign
            deadline_str = request.POST.get("deadline")
            if deadline_str:
                task.deadline = timezone.make_aware(datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M"))
            else:
                task.deadline = get_next_available_hour(request.user, timezone.localtime(timezone.now()))

            # To Do task creation
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
            return redirect("dashboard")
    else:
        return redirect("dashboard")

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
            return redirect("dashboard")
    else:
        return redirect("dashboard")

@login_required
@require_POST
def delete_task(request, task_id):
    task = ExtractedTask.objects.get(id=task_id, user=request.user)
    # To Do task deletion
    access_token = _get_graph_token(request)
    if task.todo_task_id:
        todo.delete_todo_task(access_token, task.todo_list_id, task.todo_task_id)
    task.delete()
    return redirect("dashboard")

@login_required
def settings_view(request):
    return render(request, "settings.html")

@login_required
def help_docs(request):
    return render(request, "help_docs.html")

def clean_email_text(text):
    text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    text = re.sub(r"(?i)(Best regards|Regards|BR|Sent from my|Sincerely|Thanks|Thank you|Yours truly|Cheers)[\s\S]+", "", text)
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

def extract_deadline(text, sent_date=None):
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
    now = sent_date if sent_date else timezone.now()
    # Default time for deadlines when the date string does not specify a time
    base_hour = 10

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            date_str = match.group(1) if match.groups() else match.group(0)
            date_str = date_str.strip()
            try:
                # Always parse with dayfirst=False (US style) MM/DD/YYYY
                deadline = dateutil.parser.parse(date_str, default=now, fuzzy=True, dayfirst=False)
                # Fix: "TypeError: can't compare offset-naive and offset-aware datetimes"
                # Make deadline timezone-aware
                if timezone.is_naive(deadline):
                    deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
                deadline = deadline.replace(second=0, microsecond=0)
                # If no explicit time, set to base_hour
                if 'AM' not in date_str.upper() and 'PM' not in date_str.upper() and deadline.hour == 0:
                    deadline = deadline.replace(hour=base_hour, minute=0)
                if deadline.year < 2000:
                    continue
                return deadline
            except Exception:
                pass

            lc = date_str.lower()
            if 'today' in lc or 'now' in lc:
                dt = now.replace(hour=base_hour, minute=0, second=0, microsecond=0)
                return dt if not timezone.is_naive(dt) else timezone.make_aware(dt, timezone.get_current_timezone())
            elif 'tomorrow' in lc:
                dt = add_weekdays(now, 1).replace(hour=base_hour, minute=0, second=0, microsecond=0)
                return dt if not timezone.is_naive(dt) else timezone.make_aware(dt, timezone.get_current_timezone())
            elif 'days' in lc:
                days = int(re.findall(r'\d+', date_str)[0])
                dt = add_weekdays(now, days).replace(hour=base_hour, minute=0, second=0, microsecond=0)
                return dt if not timezone.is_naive(dt) else timezone.make_aware(dt, timezone.get_current_timezone())
            elif 'next week' in lc:
                days_ahead = (0 - now.weekday() + 7) % 7 or 7
                dt = (now + timedelta(days=days_ahead)).replace(hour=base_hour, minute=0, second=0, microsecond=0)
                return dt if not timezone.is_naive(dt) else timezone.make_aware(dt, timezone.get_current_timezone())
            elif 'next month' in lc:
                first = first_of_next_month(now)
                dt = first.replace(hour=base_hour, minute=0, second=0, microsecond=0)
                return dt if not timezone.is_naive(dt) else timezone.make_aware(dt, timezone.get_current_timezone())
            elif pattern.startswith('next ([A-Za-z]+)'):
                weekday_str = match.group(1)
                weekdays = {day.lower(): i for i, day in enumerate(calendar.day_name)}
                if weekday_str.lower() in weekdays:
                    days_ahead = (weekdays[weekday_str.lower()] - now.weekday() + 7) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    dt = (now + timedelta(days=days_ahead)).replace(hour=base_hour, minute=0, second=0, microsecond=0)
                    return dt if not timezone.is_naive(dt) else timezone.make_aware(dt, timezone.get_current_timezone())
    return None

def assign_deadline_and_priority_batch(user, actionable_tasks, now=None):

    if now is None:
        now = timezone.now()
    WORK_HOURS = [9, 10, 11, 13, 14, 15, 16, 17, 18]

    # Group new actionable tasks by day
    tasks_by_day = defaultdict(list)
    for t in actionable_tasks:
        d = t["extracted_deadline"]
        # If deadline is past (delayed), schedule for today or else use extracted
        day = (d if d and d >= now else now).astimezone(timezone.get_current_timezone()).date()
        t["original_day"] = day
        tasks_by_day[day].append(t)

    # For each day, process all open and new tasks together
    for day, new_tasks in tasks_by_day.items():
        # Get all open (DB) tasks for that day
        existing_tasks = list(
            ExtractedTask.objects.filter(
                user=user,
                deadline__date=day,
                status="Open"
            ).order_by('deadline')
        )
        combined = []
        for t in existing_tasks:
            combined.append({
                "is_new": False,
                "obj": t,
                "priority": t.priority,
                "subject": t.subject,
                "deadline": t.deadline,
            })
        for t in new_tasks:
            combined.append({
                "is_new": True,
                "obj": t,
                "priority": t["priority"],
                "subject": t["subject"],
                "deadline": t["extracted_deadline"],
            })

        # Sort high priority first, then earlier deadline first
        combined.sort(key=lambda x: (-get_priority_rank(x["priority"]), x["deadline"] or now))

        local_now = timezone.localtime(now)
        if day == local_now.date():
            # For today, assign after current hour (in Asia/Tokyo)
            hour_idx = 0
            while hour_idx < len(WORK_HOURS) and WORK_HOURS[hour_idx] <= local_now.hour:
                hour_idx += 1
        else:
            hour_idx = 0

        assigned_tasks = []
        for task in combined:
            if hour_idx >= len(WORK_HOURS):
                break
            assign_time = datetime.combine(day, datetime.min.time()).replace(
                hour=WORK_HOURS[hour_idx], minute=0, second=0, microsecond=0,
                tzinfo=timezone.get_current_timezone()
            )
            task["assigned_deadline"] = assign_time
            assigned_tasks.append(task)
            hour_idx += 1

        # Recursively overflow to next working day if too many tasks
        overflow = combined[len(assigned_tasks):]
        if overflow:
            for t in overflow:
                t["extracted_deadline"] = add_weekdays(datetime.combine(day, datetime.min.time()), 1)
            assign_deadline_and_priority_batch(user, [t["obj"] for t in overflow], now=add_weekdays(now, 1))

        # Bulk update all existing tasks that need a new deadline
        tasks_to_update = []
        for t in assigned_tasks:
            if not t["is_new"] and t["obj"].deadline != t["assigned_deadline"]:
                t["obj"].deadline = t["assigned_deadline"]
                tasks_to_update.append(t["obj"])
            elif t["is_new"]:
                t["obj"]["assigned_deadline"] = t["assigned_deadline"]

        if tasks_to_update:
            ExtractedTask.objects.bulk_update(tasks_to_update, ['deadline'])

def get_next_available_hour(user, day):
    existing_deadlines = list(
        ExtractedTask.objects.filter(
            user=user,
            deadline__date=day.date()
        ).values_list('deadline', flat=True)
    )
    taken_hours = {d.hour for d in existing_deadlines if d}
    for hour in range(WORK_START, WORK_END + 1):
        if hour not in taken_hours:
            return day.replace(hour=hour, minute=0, second=0, microsecond=0)
    next_day = add_weekdays(day, 1)
    return next_day.replace(hour=WORK_START, minute=0, second=0, microsecond=0)

@login_required
def recommended_deadline(request):
    priority = request.GET.get("priority", "Medium")
    urgent = (priority == "Urgent")
    recommended_dt = get_next_available_hour(request.user, timezone.localtime(timezone.now()))
    recommended_str = recommended_dt.strftime("%Y-%m-%d %H:%M")
    return JsonResponse({"recommended_deadline": recommended_str})

def get_priority_rank(priority):
    return {"Urgent": 3, "Important": 2, "Medium": 1, "Low": 0}.get(priority, 0)

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

def fetch_unread_emails(access_token, folder="Inbox"):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    emails = []
    url = (
        f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"
        "?$filter=isRead eq false"
        "&$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink,importance,toRecipients"
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
