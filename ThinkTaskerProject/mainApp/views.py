import msal, uuid, requests
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.conf import settings

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

def index(request):
    tasks = stubTasks if settings.DEBUG else []
    context = {
        'todo_tasks': [t for t in tasks if not t['completed'] and not t['ongoing']],
        'ongoing_tasks': [t for t in tasks if t['ongoing'] and not t['completed']],
        'completed_tasks': [t for t in tasks if t['completed']],
    }
    return render(request, 'index.html', context)

def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        client_id     = settings.GRAPH_CLIENT_ID,
        client_credential = settings.GRAPH_CLIENT_SECRET,
        authority     = settings.GRAPH_AUTHORITY,
        token_cache   = cache
    )

def login_view(request):
    return render(request, 'login.html')

def nonlenovo_login(request):
    if request.method == 'POST':
        # TODO: authenticate & redirect
        return redirect('dashboard')
    return redirect('login')

def register(request):
    if request.method == 'POST':
        # TODO: validate, create user, redirect
        return redirect('login')
    return redirect('login')

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
        request.session["graph_token"] = result
        return redirect("dashboard")
    else:
        return render(request, "error.html", {"message": result.get("error_description")})