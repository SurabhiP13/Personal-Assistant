"""
End-to-end test for the Gmail flow against the **real** Gmail API.

Skipped automatically unless `servers/token.json` and `servers/credentials.json`
exist — these tests will not run in environments without OAuth credentials.

What's covered (read-only / non-destructive only):
  - GmailTool.auth() succeeds and builds a service.
  - list_labels() returns a list (Gmail accounts always have at least INBOX,
    SENT, DRAFT system labels).
  - list_emails() with a small max_results returns a list.
  - list_drafts() returns a list.

Mutating operations (send/delete/create_draft) are intentionally left out so
running the suite cannot affect the user's inbox. Add them locally if you want
to exercise the full surface.

To run:
    GMAIL_E2E=1 pytest tests/test_e2e_gmail.py -v
"""
import os

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH = os.path.join(ROOT, "servers", "token.json")
CREDENTIALS_PATH = os.path.join(ROOT, "servers", "credentials.json")


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("GMAIL_E2E") != "1",
        reason="Set GMAIL_E2E=1 to opt-in to live Gmail tests",
    ),
    pytest.mark.skipif(
        not (os.path.exists(TOKEN_PATH) and os.path.exists(CREDENTIALS_PATH)),
        reason="token.json and credentials.json required for live Gmail tests",
    ),
]


@pytest.fixture(scope="module")
def gmail():
    """Authenticate once and reuse for all tests in this module."""
    from server__v2 import GmailTool  # imported here to defer side effects

    tool = GmailTool()
    tool.auth()
    assert tool.service is not None
    return tool


def test_auth_succeeds(gmail):
    """auth() should produce a working Gmail service."""
    assert gmail.service is not None


def test_list_labels_returns_system_labels(gmail):
    """Every Gmail account has system labels — INBOX should always be present."""
    labels = gmail.list_labels()
    assert isinstance(labels, list)
    assert len(labels) > 0
    names = {l["name"] for l in labels}
    assert "INBOX" in names


def test_list_emails_returns_list(gmail):
    """list_emails should return a list (possibly empty for new accounts)."""
    emails = gmail.list_emails(query="", max_results=1)
    assert isinstance(emails, list)
    if emails:
        # Sanity-check the shape if there's at least one email.
        first = emails[0]
        assert "id" in first
        assert "subject" in first
        assert "from" in first


def test_list_drafts_returns_list(gmail):
    """list_drafts should return a list (possibly empty)."""
    drafts = gmail.list_drafts()
    assert isinstance(drafts, list)
