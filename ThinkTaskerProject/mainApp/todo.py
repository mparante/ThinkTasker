# This script is for Microsoft To Do task integration using Microsoft Graph API.
import requests

def get_todo_list_id(access_token):
    url = "https://graph.microsoft.com/v1.0/me/todo/lists"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    data = resp.json()
    if data.get("value"):
        # Use the first (default) list
        return data["value"][0]["id"]
    else:
        payload = {"displayName": "Tasks"}
        create_resp = requests.post(url, headers=headers, json=payload)
        if create_resp.status_code == 201:
            return create_resp.json()["id"]
        else:
            print("Could not create list:", create_resp.json())
            return None

def create_todo_task(access_token, title, description, due_date):
    list_id = get_todo_list_id(access_token)
    if not list_id:
        print("No default To Do list found.")
        return None, None
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"
    data = {"title": title}
    if description:
        data["body"] = {"content": description, "contentType": "text"}
    if due_date:
        data["dueDateTime"] = {
            "dateTime": due_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC"
        }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, json=data, headers=headers)
    print("POST Response:", resp)
    if resp.status_code == 201:
        return resp.json().get("id"), list_id   # Return both!
    else:
        print("To Do task creation failed:", resp.text)
        return None, None

def update_todo_task(access_token, list_id, todo_task_id, title=None, description=None, due_date=None, status=None):
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{todo_task_id}"
    data = {}
    if title is not None:
        data["title"] = title
    if description is not None:
        data["body"] = {"content": description, "contentType": "text"}
    if due_date:
        data["dueDateTime"] = {
            "dateTime": due_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC"
        }
    if status:
        data["status"] = status
    if not data:
        return True
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    resp = requests.patch(url, json=data, headers=headers)
    print("PATCH Response code:", resp.status_code)
    print("PATCH Response text:", resp.text)
    return resp.status_code in (200, 204)

def mark_todo_task_completed(access_token, list_id, todo_task_id):
    return update_todo_task(access_token, list_id, todo_task_id, status="completed")

def delete_todo_task(access_token, list_id, todo_task_id):
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{todo_task_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    resp = requests.delete(url, headers=headers)
    return resp.status_code == 204
