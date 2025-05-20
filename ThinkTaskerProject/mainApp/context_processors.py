import requests
from django.conf import settings

# This function is a context processor that adds the user's Microsoft Graph information to the context.
# It checks if the user is logged in and has a valid token.
# If the token is found, it makes a request to the Microsoft Graph API to get the user's profile information.
# If the request is successful, it returns the user's given name.
# If the request fails, it returns an empty dictionary.
# For base_generic.html
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
