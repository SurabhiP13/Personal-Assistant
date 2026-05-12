# Tests

## Setup

The repo uses `uv` with one environment per subpackage. The tests touch both
the server (`servers/server__v2.py`) and the client (`clients/mcp-client/client.py`),
so create a single combined env at the repo root:

```bash
cd /Users/sur/Downloads/Repositories/Personal-Assistant
uv venv
source .venv/bin/activate
uv pip install \
    pytest pytest-asyncio \
    mcp google-genai google-auth google-auth-oauthlib google-api-python-client \
    python-dotenv
```

## Running

```bash
# All non-Gmail tests (unit + server E2E)
pytest

# Just unit tests
pytest tests/test_client_helpers.py

# Just server E2E (spawns server__v2.py over stdio)
pytest tests/test_e2e_server.py

# Live Gmail E2E (read-only). Requires servers/token.json and credentials.json.
GMAIL_E2E=1 pytest tests/test_e2e_gmail.py
```

## What's covered

| File | Type | Touches network? |
|---|---|---|
| `test_client_helpers.py` | Unit | No |
| `test_e2e_server.py` | E2E | No (subprocess only) |
| `test_e2e_gmail.py` | E2E | Yes — real Gmail API |

`test_e2e_gmail.py` is read-only by design. Mutating tests
(send / trash / create_draft) are intentionally omitted so the suite cannot
affect your inbox. Add them locally if you want fuller coverage.
