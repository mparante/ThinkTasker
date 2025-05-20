import msal, uuid, requests
import spacy, re
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.conf import settings
from bs4 import BeautifulSoup
from .models import ActionablePattern
from datetime import datetime

# This is the english language model for spaCy, a natural language processing library.
# It is used for processing and analyzing text data.
nlp = spacy.load("en_core_web_sm")

stubTasks = [
        {
        'id': 1,
        'title': 'Task #1',
        'description': 'This is the description of Task #1',
        'completed': False,
        'ongoing': False,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id': 2,
        'title': 'Task #2',
        'description': 'This is the description of Task #2',
        'completed': False,
        'ongoing': True,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id': 3,
        'title': 'Task #3',
        'description': 'This is the description of Task #3',
        'completed': False,
        'ongoing': True,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id': 4,
        'title': 'Task #4',
        'description': 'This is the description of Task #4',
        'completed': False,
        'ongoing': False,
        'priority': 'High',
        'deadline_date': None,
        },
        {
        'id':53,
        'title': 'Task #5',
        'description': 'This is the description of Task #5',
        'completed': True,
        'ongoing': False,
        'priority': 'High',
        'deadline_date': None,
        },
    ]

# This function renders the main dashboard page.
# It retrieves the list of tasks and categorizes them into three groups: todo, ongoing, and completed.
# The tasks are filtered based on their status and passed to the template for rendering.
# The function uses a stub list of tasks for demonstration purposes.
def index(request):
    tasks = stubTasks if settings.DEBUG else []
    context = {
        'todo_tasks': [t for t in tasks if not t['completed'] and not t['ongoing']],
        'ongoing_tasks': [t for t in tasks if t['ongoing'] and not t['completed']],
        'completed_tasks': [t for t in tasks if t['completed']],
    }
    return render(request, 'index.html', context)

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
        "&$select=subject,bodyPreview,receivedDateTime,from,isRead"
    )

    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("value", [])
    else:
        return []
    

# This function marks an email as read in the user's Outlook inbox after fetch_emails function is called.   
# def mark_email_as_read(request, message_id):
#     access_token = _get_graph_token(request)
#     if not access_token:
#         return False
#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json"
#     }
#     url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
#     data = {"isRead": True}
#     resp = requests.patch(url, headers=headers, json=data)
#     return resp.status_code == 200

# This function extracts actionable items from the given text.
# It uses the active patterns from the database to identify words, phrases, or regex patterns that indicate an actionable item.
# The function iterates through the patterns and checks if any of them match the text.
# If a match is found, the pattern is added to the list of found patterns.
# The function returns a list of found patterns.
def extract_actionable_items(text):
    patterns = ActionablePattern.objects.filter(is_active=True)
    found_patterns = []
    for pattern in patterns:
        if pattern.pattern_type == 'word':
            # word boundary, case insensitive
            if re.search(rf'\b{re.escape(pattern.pattern)}\b', text, re.IGNORECASE):
                found_patterns.append(pattern)
        elif pattern.pattern_type == 'phrase':
            if pattern.pattern.lower() in text.lower():
                found_patterns.append(pattern)
        elif pattern.pattern_type == 'regex':
            if re.search(pattern.pattern, text, re.IGNORECASE):
                found_patterns.append(pattern)
    return found_patterns

# This function renders the login page.
# It is called when the user accesses the login URL.
def login_view(request):
    return render(request, 'login.html')

# This function handles the login for non-Lenovo users.
def nonlenovo_login(request):
    if request.method == 'POST':
        # TODO: authenticate & redirect
        return redirect('dashboard')
    return redirect('login')

# Registration view for non-Lenovo users
def register(request):
    if request.method == 'POST':
        # TODO: validate, create user, redirect
        return redirect('login')
    return redirect('login')

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

# Callback view for Microsoft Graph API
# This function handles the response from Microsoft after the user has logged in.
# It exchanges the authorization code for an access token.
# If successful, it stores the token in the session and redirects to the dashboard.
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
        request.session["graph_token"] = result
        return redirect("dashboard")
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

# This function retrieves the user's Outlook inbox messages.
# It uses the access token stored in the session to make a request to the Microsoft Graph API.
# If the token is not found, it returns an empty list.
# The function fetches the most recent messages and extracts actionable items from the subject and preview text.
def outlook_inbox(request):
    access_token = _get_graph_token(request)
    if access_token:
        raw_messages = fetch_emails(request, top=20)
        emails = []
        for m in raw_messages:
            subject = m.get("subject", "")
            preview = m.get("bodyPreview", "")
            actionable_items = extract_actionable_items(subject + " " + preview)
            emails.append({
                "id": m["id"],
                "subject": subject,
                "preview": preview,
                "received": parse_iso_datetime(m.get("receivedDateTime")),
                "actionable_items": [
                    {"pattern": pat.pattern, "priority": pat.priority} for pat in actionable_items
                ],
            })
            print(m.get("receivedDateTime"))
            # mark_email_as_read(request, m["id"])
    else:
        emails = []

    return render(request, "emails.html", {"emails": emails})

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