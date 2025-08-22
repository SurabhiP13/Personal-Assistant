from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file("token.json")
service = build("gmail", "v1", credentials=creds)

# Replace with a real message ID from list_emails
message_id = "198ccd37e5a5752c"
service.users().messages().delete(userId="me", id=message_id).execute()
print("Deleted successfully")
