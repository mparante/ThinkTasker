import requests
from django.conf import settings

def graph_user(request):
    token = request.session.get("graph_token")
    if not token:
        return {}
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    r = requests.get(
        "https://graph.microsoft.com/v1.0/me?$select=givenName",
        headers=headers
    )
    if r.status_code == 200:
        return {"given_name": r.json().get("givenName")}
    return {}
