import msal, uuid, requests, spacy, re

from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q

from .models import ActionablePattern, ExtractedTask, ProcessedEmail, ThinkTaskerUser
from .forms import ExtractedTaskForm
from datetime import datetime

# This is the english language model for spaCy, a natural language processing library.
# It is used for processing and analyzing text data.
nlp = spacy.load("en_core_web_sm")

# This function builds a Microsoft Authentication Library (MSAL) application instance.
# It uses the client ID, client secret, and authority from the settings.
def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        client_id = settings.GRAPH_CLIENT_ID,
        client_credential = settings.GRAPH_CLIENT_SECRET,
        authority = settings.GRAPH_AUTHORITY,
        token_cache = cache
    )

# This function retrieves all active patterns from the database.
# It filters the ActionablePattern model to get only those patterns that are marked as active.
# The function returns a queryset of active patterns.
def get_active_patterns():
    return ActionablePattern.objects.filter(is_active=True)

# This function renders the login page.
# It is called when the user accesses the login URL.
def login_view(request):
    return render(request, "login.html")

# This function handles the registration of new users.
# It checks if the email is already registered and creates a new user if not.
# It sets the username to the email and the password to the provided password.
# The user is marked as active but not approved.
# After successful registration, a success message is displayed and the user is redirected to the login page.
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

# This function retrieves the user's profile information from Microsoft Graph API.
# It uses the access token stored in the session to make a request to the API.
# If the token is not found, it redirects to the login page.
# If the request is successful, it renders the profile page with the user's information.
# The profile page displays the user's name and email address.
def profile(request):
    access_token = _get_graph_token(request)
    if not access_token:
        return redirect("login")

    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    graph_endpoint = "https://graph.microsoft.com/v1.0/me"
    resp = requests.get(graph_endpoint, headers=headers)
    resp.raise_for_status()
    user = resp.json()

    return render(request, "profile.html", {"user": user})

# Login view for Microsoft Graph API
# This function initiates the OAuth2 authorization code flow.
# It redirects the user to the Microsoft login page.
def graph_login(request):
    msal_app = _build_msal_app()

    request.session["msal_state"] = str(uuid.uuid4())
    auth_url = msal_app.get_authorization_request_url(
        scopes = settings.GRAPH_SCOPE,
        state  = request.session["msal_state"],
        redirect_uri = settings.GRAPH_REDIRECT_URI
    )
    return redirect(auth_url)

# This function handles the callback from Microsoft Graph API after the user has logged in.
# It retrieves the authorization code from the request and exchanges it for an access token.
# It then uses the access token to fetch the user's profile information from Microsoft Graph API.
# If the user is found in the database, it logs them in and redirects to the dashboard.
# If the user is not found, it renders the login page with the user's email and name.
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

# This function retrieves the access token from the session.
# If the token is not found, it returns None.
# This is used to check if the user is logged in and has a valid token.
# If the token is found, it can be used to make requests to the Microsoft Graph API.
def _get_graph_token(request):
    token_dict = request.session.get("graph_token")
    if not token_dict:
        return None
    return token_dict.get("access_token")

#This function parses an ISO 8601 formatted date string.
# It converts the string into a datetime object.
# If the string is empty or None, it returns None.
# If the string cannot be parsed, it prints an error message and returns None.
def parse_iso_datetime(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        print("Error parsing date:", dt_str, e)
        return None

# This function renders the main dashboard page.
# It retrieves the list of tasks and categorizes them into three groups: todo, ongoing, and completed.
# The tasks are filtered based on their status and passed to the template for rendering.
@login_required
def index(request):
    # Query only tasks that came from actionable processed emails
    actionable_tasks = ExtractedTask.objects.filter(
        user=request.user
    ).filter(
        Q(email__is_actionable=True) | Q(email__isnull=True)
    ).distinct()

    # Categorize tasks based on status (adjust as needed)
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
    return render(request, "emails.html", {"processed_emails": processed_emails})

# This function returns a list of the user's most recent UNREAD Outlook messages as dicts.
# It uses the access token stored in the session to make a request to the API.
# If the token is not found, it returns an empty list.
# The function constructs the URL for the API request, including the number of messages to fetch and the fields to select.
# It sends a GET request to the API and checks the response status.
def fetch_emails(request, top=20):
    access_token = _get_graph_token(request)
    if not access_token:
        return []

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    url = (
        "https://graph.microsoft.com/v1.0/"
        "me/mailFolders/Inbox/messages"
        f"?$top={top}"
        "&$filter=isRead eq false"
        "&$select=id,subject,bodyPreview,receivedDateTime,from,isRead,webLink"
    )

    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("value", [])
    else:
        return []    

# This function extracts actionable items from the given text.
# It uses the active patterns from the database to identify words, phrases, or regex patterns that indicate an actionable item.
# The function iterates through the patterns and checks if any of them match the text.
# If a match is found, the pattern is added to the list of found patterns.
# The function returns a list of found patterns.
def extract_actionable_items(text):
    patterns = ActionablePattern.objects.filter(is_active=True)
    found_patterns = []
    for pattern in patterns:
        if pattern.pattern_type == "word":
            # word boundary, case insensitive
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
    access_token = _get_graph_token(request)
    if access_token:
        raw_messages = fetch_emails(request, top=20)
        for m in raw_messages:            
            subject = m.get("subject", "")
            preview = m.get("bodyPreview", "")
            message_id = m["id"]
            web_link = m.get("webLink")
            
            if ProcessedEmail.objects.filter(message_id=message_id, user=request.user).exists():
                continue

            # Extract actionable items
            actionable_patterns = extract_actionable_items(subject + " " + preview)
            actionable_list = [{"pattern": p.pattern, "priority": p.priority} for p in actionable_patterns]
            is_actionable = bool(actionable_patterns)

            # Save the ProcessedEmail
            pe = ProcessedEmail.objects.create(
                user=request.user,
                message_id=message_id,
                subject=subject,
                body_preview=preview,
                is_actionable=is_actionable,
                web_link=web_link,
            )

            # If actionable, save each as a task
            if is_actionable:
                priority = next((p.priority for p in actionable_patterns if p.priority), "")
                # Create one task per actionable email (or per pattern if you want!)
                ExtractedTask.objects.create(
                    user=request.user,
                    email=pe,
                    subject=subject,
                    task_description=preview,
                    actionable_patterns=actionable_list,
                    priority=priority,
                    status="Open",
                )

    # messages.success(request, "Synced latest emails from Outlook.")
    return redirect("outlook-inbox")

# This function updates the status of a task based on the provided task ID and new status.
# It uses the POST method to receive the task ID and new status from the request.
# If the request method is POST, it retrieves the task ID and new status from the request.
# It then tries to find the task in the database using the task ID.
# If the task is found, it updates the status and saves the task.
# If the task is not found, it returns a JSON response indicating failure.
# If the request method is not POST, it returns a JSON response indicating an invalid request.
# The function returns a JSON response indicating success or failure.
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
            return JsonResponse({"success": True})
        except ExtractedTask.DoesNotExist:
            return JsonResponse({"success": False, "error": "Task not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})

@login_required
def task_list(request):
    query = request.GET.get('q', '')
    tasks = ExtractedTask.objects.filter(user=request.user)
    if query:
        tasks = tasks.filter(
            Q(subject__icontains=query) |
            Q(task_description__icontains=query)
        )
    tasks = tasks.order_by('-created_at')
    return render(request, "task_list.html", {"tasks": tasks, "query": query})

@login_required
def create_task(request):
    if request.method == "POST":
        form = ExtractedTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            task.is_actionable = True
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
            form.save()
            return redirect("task_list")
    else:
        form = ExtractedTaskForm(instance=task)
    return render(request, "task_form.html", {"form": form, "task": task})

@login_required
@require_POST
def delete_task(request, task_id):
    task = ExtractedTask.objects.get(id=task_id, user=request.user)
    task.delete()
    return redirect("task_list")