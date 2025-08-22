import os
import subprocess
import json
import base64
import argparse
from email.mime.text import MIMEText

from mcp.server.fastmcp import FastMCP

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# ============================================================
# MCP SERVER INIT
# ============================================================
mcp = FastMCP("terminal+gmail")

# Cross-platform home/workspace setup
DEFAULT_HOME = os.path.expanduser("~")  # path for saving files for the terminal tool
if not os.path.isdir(DEFAULT_HOME):
    DEFAULT_HOME = (
        os.environ.get("USERPROFILE")
        or os.environ.get("HOMEPATH")
        or "C:\\Users\\Public"
    )

DEFAULT_WORKSPACE = os.path.join(DEFAULT_HOME, "understanding-mcp", "workspace")
os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)


# ============================================================
# TERMINAL TOOL
# ============================================================
@mcp.tool()
async def run_command(command: str) -> str:
    """
    Run a terminal command inside the workspace directory.
    """
    try:
        result = subprocess.run(
            command, shell=True, cwd=DEFAULT_WORKSPACE, capture_output=True, text=True
        )
        return result.stdout or result.stderr
    except Exception as e:
        return str(e)


# ============================================================
# GMAIL TOOLING
# ============================================================
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",  # read only
    "https://www.googleapis.com/auth/gmail.send",  # send emails
    "https://www.googleapis.com/auth/gmail.modify",  # for delete, mark read, etc.
]


class GmailTool:
    def __init__(self):
        self.service = None

    def auth(self):
        """Authenticate Gmail API with token.json and credentials.json"""
        creds = None
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        except FileNotFoundError:
            pass

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=8080, access_type="offline")

            with open("token.json", "w") as token:
                token.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)

        return True

    def list_emails(self, query="", max_results=10):
        if not self.service:
            self.auth()
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        emails = []
        for msg in results.get("messages", []):
            email_data = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata")
                .execute()
            )

            headers = {
                h["name"]: h["value"] for h in email_data["payload"].get("headers", [])
            }
            emails.append(
                {
                    "id": msg["id"],
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                    "snippet": email_data.get("snippet", ""),
                }
            )
        return emails

    def get_email(self, message_id):
        if not self.service:
            self.auth()
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        body = self._get_body(msg["payload"])

        return {
            "id": message_id,
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }

    def _get_body(self, payload):
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="ignore"
                        )
                        break
        else:
            if payload["mimeType"] == "text/plain":
                data = payload["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode(
                        "utf-8", errors="ignore"
                    )
        return body

    def delete_email(self, message_id):
        """Delete an email permanently"""

        if not self.service:
            self.auth()

        self.service.users().messages().delete(userId="me", id=message_id).execute()
        return {"status": "deleted", "id": message_id}

    def send_email(self, to, subject, body):
        """Send an email"""
        if not self.service:
            self.auth()

        # Construct the message
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        send_result = (
            self.service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        return send_result


gmail = GmailTool()


@mcp.tool()
def list_emails(query: str = "", max_results: int = 10) -> str:
    """List Gmail emails with optional search query"""
    try:
        emails = gmail.list_emails(query, max_results)
        return json.dumps(emails, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_email(message_id: str) -> str:
    """Get full Gmail email content by ID"""
    try:
        email = gmail.get_email(message_id)
        return json.dumps(email, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_unread_emails() -> str:
    """Get unread Gmail emails"""
    try:
        emails = gmail.list_emails("is:unread", 20)
        return json.dumps(emails, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send a Gmail email"""
    try:
        result = gmail.send_email(to, subject, body)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def delete_email(message_id: str) -> str:
    """Delete a Gmail email by ID"""
    try:
        result = gmail.delete_email(message_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================
# MAIN ENTRY
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server_type", type=str, default="sse", choices=["sse", "stdio"]
    )
    args = parser.parse_args()
    print("Starting Terminal + Gmail MCP server...")
    mcp.run(args.server_type)
