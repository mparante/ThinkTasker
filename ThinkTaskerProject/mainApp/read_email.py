import requests

# This function is used to mark emails as read in batches using the Microsoft Graph API.
def batch_mark_emails_as_read(message_ids, access_token):
    def chunked(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]
    url = "https://graph.microsoft.com/v1.0/$batch"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    # 20 is Graph API batch limit
    for chunk in chunked(message_ids, 20):
        batch_requests = [
            {
                "id": str(i),
                "method": "PATCH",
                "url": f"/me/messages/{message_id}",
                "headers": {"Content-Type": "application/json"},
                "body": {"isRead": True}
            }
            for i, message_id in enumerate(chunk)
        ]
        batch_payload = {"requests": batch_requests}
        resp = requests.post(url, json=batch_payload, headers=headers)
        if resp.status_code != 200:
            print(f"Batched marking emails as read failed: {resp.status_code} {resp.text}")
