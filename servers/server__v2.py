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

# Resolve Gmail credential files relative to this script so the server can be
# launched from any working directory (e.g. via stdio from an MCP client).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, "credentials.json")


# ============================================================
# TERMINAL TOOL
# ============================================================
@mcp.tool()
async def run_command(command: str, timeout: int = 30) -> str:
    """
    Run a terminal command inside the workspace directory.

    Returns combined stdout, stderr, and exit code. Times out after `timeout`
    seconds (default 30) to avoid hanging the server on long-running commands.

    Note: this tool executes arbitrary shell commands by design. Only expose
    it to trusted callers.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=DEFAULT_WORKSPACE,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return json.dumps(
            {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            indent=2,
        )
    except subprocess.TimeoutExpired as e:
        return json.dumps(
            {
                "exit_code": None,
                "error": f"Command timed out after {timeout}s",
                "stdout": e.stdout or "",
                "stderr": e.stderr or "",
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


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
        # A missing or corrupted token.json should fall through to the OAuth
        # flow rather than crashing the server.
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
            creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(
                    port=8080, access_type="offline", prompt="consent"
                )

            with open(TOKEN_PATH, "w") as token:
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
        """
        Extract a readable body from a Gmail payload.

        Walks nested multipart trees (e.g. multipart/mixed -> multipart/alternative
        -> text/plain) and prefers text/plain. Falls back to text/html if no
        plain-text part exists.
        """

        def decode(data):
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        plain_text = None
        html_text = None

        def walk(part):
            nonlocal plain_text, html_text
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if mime == "text/plain" and data and plain_text is None:
                plain_text = decode(data)
            elif mime == "text/html" and data and html_text is None:
                html_text = decode(data)
            for sub in part.get("parts", []) or []:
                walk(sub)

        walk(payload)
        return plain_text or html_text or ""

    def delete_email(self, message_id):
        """Move an email to Trash (recoverable, not a permanent delete)."""

        if not self.service:
            self.auth()

        self.service.users().messages().trash(userId="me", id=message_id).execute()
        return {"status": "trashed", "id": message_id}

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

    def _resolve_label_id(self, label_name):
        """Look up a label ID by (case-insensitive) name. Returns None if missing."""
        labels = (
            self.service.users().labels().list(userId="me").execute().get("labels", [])
        )
        return next(
            (l["id"] for l in labels if l["name"].lower() == label_name.lower()), None
        )

    def _batch_modify(self, message_ids, add_label_ids=None, remove_label_ids=None):
        """Apply add/remove label changes to a list of message IDs in 1000-ID chunks."""
        BATCH_SIZE = 1000
        for i in range(0, len(message_ids), BATCH_SIZE):
            chunk = message_ids[i : i + BATCH_SIZE]
            self.service.users().messages().batchModify(
                userId="me",
                body={
                    "ids": chunk,
                    "addLabelIds": add_label_ids or [],
                    "removeLabelIds": remove_label_ids or [],
                },
            ).execute()

    def delete_emails_in_label(self, label_name):
        """Delete all emails under a given label in batch"""
        if not self.service:
            self.auth()

        label_id = self._resolve_label_id(label_name)
        if not label_id:
            return {"error": f"Label '{label_name}' not found"}

        # 2. Get all messages under that label, paging until exhausted
        message_ids = []
        page_token = None
        while True:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", labelIds=[label_id], pageToken=page_token)
                .execute()
            )
            message_ids.extend(m["id"] for m in results.get("messages", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break

        if not message_ids:
            return {"status": "no emails found under this label"}

        self._batch_modify(message_ids, add_label_ids=["TRASH"])
        return {"status": "deleted", "count": len(message_ids), "label": label_name}

    def label_emails(self, message_ids, label_name, create_if_missing=False):
        """
        Apply a label to a list of message IDs.

        If `create_if_missing` is True and the label does not exist, it is
        created first. Returns a summary dict with status, count, and the
        resolved label id.
        """
        if not self.service:
            self.auth()

        if not message_ids:
            return {"status": "no message ids provided", "count": 0}

        label_id = self._resolve_label_id(label_name)
        if not label_id:
            if not create_if_missing:
                return {"error": f"Label '{label_name}' not found"}
            created = self.create_label(label_name)
            label_id = created["id"]

        self._batch_modify(list(message_ids), add_label_ids=[label_id])
        return {
            "status": "labeled",
            "count": len(message_ids),
            "label": label_name,
            "label_id": label_id,
        }

    def search_and_label(self, query, label_name, create_if_missing=False, max_results=None):
        """
        Search emails by Gmail query syntax and apply a label to every match.

        `query` uses the same syntax as the Gmail search bar
        (e.g. "from:newsletter@x.com", "subject:invoice older_than:30d").
        Paginates through all results unless `max_results` is set as a cap.
        """
        if not self.service:
            self.auth()

        label_id = self._resolve_label_id(label_name)
        if not label_id:
            if not create_if_missing:
                return {"error": f"Label '{label_name}' not found"}
            created = self.create_label(label_name)
            label_id = created["id"]

        # Paginate through search results
        message_ids = []
        page_token = None
        while True:
            req = self.service.users().messages().list(
                userId="me",
                q=query,
                pageToken=page_token,
                maxResults=500,
            )
            results = req.execute()
            message_ids.extend(m["id"] for m in results.get("messages", []))
            if max_results is not None and len(message_ids) >= max_results:
                message_ids = message_ids[:max_results]
                break
            page_token = results.get("nextPageToken")
            if not page_token:
                break

        if not message_ids:
            return {"status": "no emails matched query", "query": query, "count": 0}

        self._batch_modify(message_ids, add_label_ids=[label_id])
        return {
            "status": "labeled",
            "count": len(message_ids),
            "query": query,
            "label": label_name,
            "label_id": label_id,
        }

    # ========================
    # LABEL MANAGEMENT
    # ========================
    def list_labels(self):
        if not self.service:
            self.auth()
        return (
            self.service.users().labels().list(userId="me").execute().get("labels", [])
        )

    def create_label(
        self, name, label_list_visibility="labelShow", message_list_visibility="show"
    ):
        if not self.service:
            self.auth()
        label_obj = {
            "name": name,
            "labelListVisibility": label_list_visibility,
            "messageListVisibility": message_list_visibility,
        }
        return (
            self.service.users().labels().create(userId="me", body=label_obj).execute()
        )

    def update_label(
        self,
        label_id,
        new_name=None,
        label_list_visibility=None,
        message_list_visibility=None,
    ):
        if not self.service:
            self.auth()
        # Use `is not None` so callers can pass an empty string to explicitly
        # clear a field; bare truthiness would silently skip it.
        label_obj = {}
        if new_name is not None:
            label_obj["name"] = new_name
        if label_list_visibility is not None:
            label_obj["labelListVisibility"] = label_list_visibility
        if message_list_visibility is not None:
            label_obj["messageListVisibility"] = message_list_visibility
        return (
            self.service.users()
            .labels()
            .update(userId="me", id=label_id, body=label_obj)
            .execute()
        )

    def delete_label(self, label_id):
        if not self.service:
            self.auth()
        self.service.users().labels().delete(userId="me", id=label_id).execute()
        return {"status": "deleted", "id": label_id}

    # ========================
    # DRAFT MANAGEMENT
    # ========================
    def _build_raw_message(self, to, subject, body):
        message = MIMEText(body)
        if to:
            message["to"] = to
        if subject:
            message["subject"] = subject
        return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    def list_drafts(self, max_results=20):
        if not self.service:
            self.auth()
        results = (
            self.service.users()
            .drafts()
            .list(userId="me", maxResults=max_results)
            .execute()
        )
        return results.get("drafts", [])

    def get_draft(self, draft_id):
        if not self.service:
            self.auth()
        draft = (
            self.service.users()
            .drafts()
            .get(userId="me", id=draft_id, format="full")
            .execute()
        )
        msg = draft.get("message", {})
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = self._get_body(msg.get("payload", {})) if msg.get("payload") else ""
        return {
            "id": draft.get("id"),
            "message_id": msg.get("id"),
            "subject": headers.get("Subject", ""),
            "to": headers.get("To", ""),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }

    def create_draft(self, to, subject, body):
        if not self.service:
            self.auth()
        raw = self._build_raw_message(to, subject, body)
        return (
            self.service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )

    def update_draft(self, draft_id, to=None, subject=None, body=None):
        if not self.service:
            self.auth()

        # Pull existing draft so we can preserve unchanged fields
        existing = self.get_draft(draft_id)
        new_to = to if to is not None else existing.get("to", "")
        new_subject = subject if subject is not None else existing.get("subject", "")
        new_body = body if body is not None else existing.get("body", "")

        raw = self._build_raw_message(new_to, new_subject, new_body)
        return (
            self.service.users()
            .drafts()
            .update(
                userId="me",
                id=draft_id,
                body={"message": {"raw": raw}},
            )
            .execute()
        )


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
    """Move a Gmail email to Trash by ID (recoverable, not permanent)."""
    try:
        result = gmail.delete_email(message_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def delete_emails_in_label(label_name: str) -> str:
    """Delete all emails under a specific Gmail label"""
    try:
        result = gmail.delete_emails_in_label(label_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


# ===== LABELS =====
@mcp.tool("gmail.list_labels")
def list_labels():
    return gmail.list_labels()


@mcp.tool("gmail.create_label")
def create_label(name: str):
    return gmail.create_label(name)


@mcp.tool("gmail.update_label")
def update_label(label_id: str, new_name: str = None):
    return gmail.update_label(label_id, new_name=new_name)


@mcp.tool("gmail.delete_label")
def delete_label(label_id: str):
    return gmail.delete_label(label_id)


# ===== BULK LABELING =====
@mcp.tool("gmail.label_emails")
def label_emails(
    message_ids: list[str],
    label_name: str,
    create_if_missing: bool = False,
) -> str:
    """
    Apply a label to a list of Gmail message IDs.

    Set `create_if_missing=True` to auto-create the label if it doesn't exist.
    """
    try:
        result = gmail.label_emails(
            message_ids, label_name, create_if_missing=create_if_missing
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool("gmail.search_and_label")
def search_and_label(
    query: str,
    label_name: str,
    create_if_missing: bool = False,
    max_results: int = None,
) -> str:
    """
    Search Gmail with `query` (e.g. "from:newsletter@x.com") and apply
    `label_name` to every matching message.

    Paginates through all matches unless `max_results` is given as a cap.
    Set `create_if_missing=True` to auto-create the label if it doesn't exist.
    """
    try:
        result = gmail.search_and_label(
            query,
            label_name,
            create_if_missing=create_if_missing,
            max_results=max_results,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


# ===== DRAFTS =====
@mcp.tool("gmail.list_drafts")
def list_drafts():
    return gmail.list_drafts()


@mcp.tool("gmail.get_draft")
def get_draft(draft_id: str):
    return gmail.get_draft(draft_id)


@mcp.tool("gmail.create_draft")
def create_draft(to: str, subject: str, body: str):
    return gmail.create_draft(to, subject, body)


@mcp.tool("gmail.update_draft")
def update_draft(draft_id: str, to: str = None, subject: str = None, body: str = None):
    return gmail.update_draft(draft_id, to=to, subject=subject, body=body)


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
