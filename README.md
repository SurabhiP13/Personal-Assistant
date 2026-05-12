# Personal-Assistant (MCP)

A small Model Context Protocol (MCP) stack that gives an LLM access to your **terminal** and **Gmail account** as tools. Built with [FastMCP](https://github.com/jlowin/fastmcp), Google Gemini, and LangGraph.

The project ships:

- **One server** (`servers/server__v2.py`) exposing terminal + Gmail tools over MCP.
- **Two reference clients** that connect to it:
  - `clients/mcp-client/client.py` — direct Gemini SDK + MCP **stdio** transport.
  - `clients/mcp-client/langchain_mcp_client_stdio.py` — LangGraph React agent + MCP **SSE** transport.

---

## Architecture

```
        ┌────────────────────────┐                   ┌──────────────────────────┐
        │  client.py             │ ── stdio ───────▶ │  server__v2.py           │
        │  (Google GenAI SDK     │                   │   ─ run_command          │
        │   + MCP stdio_client)  │                   │   ─ Gmail (messages,     │
        └────────────────────────┘                   │     labels, drafts,      │
                                                     │     bulk-labeling)       │
        ┌─────────────────────────────────┐          │                          │
        │ langchain_mcp_client_stdio.py   │ ── SSE ──▶                          │
        │ (LangGraph create_react_agent + │          └──────────────────────────┘
        │  MCP sse_client)                │
        └─────────────────────────────────┘
```

The server can run in either `stdio` (subprocess pipe) or `sse` (HTTP server on `http://127.0.0.1:8000/sse`) mode. `client.py` auto-spawns the server in stdio mode. The LangGraph client expects the server to already be running in SSE mode.

---

## Prerequisites

| Requirement | Version | Why |
|---|---|---|
| Python | **3.13.x** | Pinned `>=3.13, <3.14` (pydantic-core's PyO3 doesn't yet support 3.14) |
| [`uv`](https://github.com/astral-sh/uv) | latest | Project + Python version management |
| Google account | — | For Gmail access + Gemini API key |

If you're on macOS with Homebrew:

```bash
brew install uv
```

---

## One-time setup

### 1. Install Python 3.13 and project dependencies

```bash
# clone the repo (skip if already done)
git clone <repo-url> Personal-Assistant
cd Personal-Assistant

# install Python 3.13 once (uv manages it under ~/.local/share/uv/python)
uv python install 3.13

# install server dependencies
cd servers
uv sync --python 3.13

# install client dependencies
cd ../clients/mcp-client
uv sync --python 3.13

cd ../..
```

### 2. Get a Gemini API key

1. Open [Google AI Studio → API keys](https://aistudio.google.com/apikey).
2. Click **Create API key**.
3. Copy the value.

### 3. Create the client `.env`

```bash
# from repo root
cat > clients/mcp-client/.env <<EOF
GEMINI_API_KEY=your-key-here
GOOGLE_API_KEY=your-key-here
EOF
```

(Both names point at the same key — `client.py` reads `GEMINI_API_KEY`, the LangGraph client reads `GOOGLE_API_KEY`.)

### 4. Set up Gmail OAuth

The server uses OAuth user credentials, **not** a service account.

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create (or select) a project.
3. **APIs & Services → Library** → enable the **Gmail API**.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Name: anything (e.g. `mcp-personal-assistant`)
5. **Download JSON** and save it as `servers/credentials.json`.
6. **APIs & Services → OAuth consent screen**:
   - User type: External
   - Add your own Google account under **Test users** (otherwise Google blocks the sign-in).

`token.json` is created **automatically** on the first Gmail tool call (see "First run" below).

### 5. Choose a Gemini model

The clients default to `gemini-2.0-flash-lite` — free tier, available out of the box. If you have billing enabled and want a stronger model, change the model name in `clients/mcp-client/client.py` and `clients/mcp-client/langchain_mcp_client_stdio.py` (e.g. `gemini-2.0-flash`, `gemini-1.5-pro`).

---

## Running it

### Option A — direct Gemini client (recommended for first run)

```bash
cd clients/mcp-client
uv run python client.py ../../servers/server__v2.py
```

The client automatically spawns `server__v2.py` as a stdio subprocess. You'll see the registered tools printed and a `Query:` prompt.

### Option B — LangGraph SSE client

Requires the server to be running separately.

**Terminal 1 — server:**

```bash
cd servers
uv run python server__v2.py --server_type sse
# Uvicorn listens on http://127.0.0.1:8000/sse
```

**Terminal 2 — client:**

```bash
cd clients/mcp-client
uv run python langchain_mcp_client_stdio.py
```

Override the SSE URL with `MCP_SSE_URL=http://host:port/sse uv run python ...`.

### First run

On your first Gmail query (e.g. `list my unread emails`) a browser window will open asking you to sign in and grant Gmail access. After you approve, `servers/token.json` is written and subsequent runs skip the browser entirely.

---

## Available tools

### Terminal

| Tool | Args | Description |
|---|---|---|
| `run_command` | `command: str, timeout: int = 30` | Runs a shell command inside `~/understanding-mcp/workspace`. Returns JSON with `stdout`, `stderr`, `exit_code`. |

### Gmail — messages

| Tool | Description |
|---|---|
| `list_emails(query, max_results)` | Search inbox with Gmail query syntax |
| `get_email(message_id)` | Full body + headers |
| `get_unread_emails()` | Shortcut for `is:unread` |
| `send_email(to, subject, body)` | Send a plain-text email |
| `delete_email(message_id)` | Move to Trash (recoverable) |
| `delete_emails_in_label(label_name)` | Trash every message under a label, paginated |

### Gmail — labels

| Tool | Description |
|---|---|
| `gmail.list_labels` | List all user + system labels |
| `gmail.create_label(name)` | Create a new label |
| `gmail.update_label(label_id, new_name)` | Rename a label |
| `gmail.delete_label(label_id)` | Delete a label |

### Gmail — bulk labeling

| Tool | Description |
|---|---|
| `gmail.label_emails(message_ids, label_name, create_if_missing)` | Apply a label to a list of message IDs |
| `gmail.search_and_label(query, label_name, create_if_missing, max_results)` | Search by Gmail query and label every match in one shot |

### Gmail — drafts

| Tool | Description |
|---|---|
| `gmail.list_drafts` | List drafts |
| `gmail.get_draft(draft_id)` | Get full draft content |
| `gmail.create_draft(to, subject, body)` | Create a new draft |
| `gmail.update_draft(draft_id, to, subject, body)` | Update existing draft (preserves unchanged fields) |

---

## Example prompts

Once you have a `Query:` prompt:

```
list my unread emails
draft a reply to the latest email from alice@example.com asking for the deck
label every email from newsletter@substack.com as "Substack" — create the label if missing
delete all emails under the label "Promotions"
run command: ls -la
```

The agent will pick the right tools automatically.

---

## Tests

A pytest suite lives in `tests/`. Three flavors:

| File | Type | Hits network? |
|---|---|---|
| `test_client_helpers.py` | Unit (mocked) | No |
| `test_e2e_server.py` | E2E — spawns the real server over stdio | No |
| `test_e2e_gmail.py` | E2E — real Gmail API (read-only) | Yes |

### Setup a combined test venv (separate from the two project venvs)

```bash
# from repo root
uv venv && source .venv/bin/activate
uv pip install pytest pytest-asyncio mcp google-genai \
               google-auth google-auth-oauthlib google-api-python-client \
               python-dotenv
```

### Run

```bash
pytest                                       # unit + non-Gmail E2E
pytest tests/test_client_helpers.py          # unit only
pytest tests/test_e2e_server.py              # spawn-server E2E
GMAIL_E2E=1 pytest tests/test_e2e_gmail.py   # live Gmail (read-only)
```

The Gmail E2E is **read-only by design** (auth + `list_labels` + `list_emails` + `list_drafts`). Mutating tests are intentionally omitted so the suite can't affect your inbox.

---

## Troubleshooting

### `error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)`

You have Python 3.14 and `uv` picked it up. Pin to 3.13:

```bash
uv python install 3.13
uv sync --python 3.13
```

The `pyproject.toml` files are already pinned to `>=3.13, <3.14` to prevent this from recurring.

### `McpError: Connection closed` when starting the client

The server subprocess crashed before the MCP handshake completed. Most likely cause: client and server are running with different Python venvs, and the server's venv is missing a dependency.

`client.py` is already wired to use `servers/.venv/bin/python` if it exists. Make sure you ran `uv sync` inside `servers/` *after* running it in `clients/mcp-client/`. Re-run `uv sync` in `servers/` if unsure.

### `Uvicorn running on http://127.0.0.1:8000` — but the LLM client crashes

The server started in **SSE** mode (the default) when the LLM client expected **stdio**. This only matters for `client.py`, which now passes `--server_type stdio` explicitly when spawning the server. If you see this, make sure you're running the latest `client.py`.

### `429 RESOURCE_EXHAUSTED` from Gemini

Your free-tier quota is exhausted *or* the model you're using isn't on the free tier. Either:
- Switch to `gemini-2.0-flash-lite` (free tier, current default), or
- Add billing in [Google AI Studio](https://aistudio.google.com).

### `404 NOT_FOUND` / `gemini-1.5-flash is not found for API version v1beta`

Some older Gemini model names are deprecated in the newer `google-genai` SDK. Use `gemini-2.0-flash-lite` (free) or `gemini-2.0-flash` (paid).

### Browser doesn't open at server startup

Expected. The OAuth flow is lazy — it only runs when the **first Gmail tool is called**. Connect a client and issue a Gmail query like `list my unread emails`.

### `Label '...' not found` in `label_emails` / `search_and_label`

Pass `create_if_missing: true` to auto-create the label, or create it first via `gmail.create_label`.

---

## Project layout

```
Personal-Assistant/
├── servers/
│   ├── server__v2.py            # main MCP server (terminal + Gmail)
│   ├── server__v1.py            # earlier version, kept for reference
│   ├── credentials.json         # OAuth client (you provide)
│   ├── token.json               # OAuth token (auto-generated on first run)
│   ├── pyproject.toml
│   └── uv.lock
├── clients/
│   └── mcp-client/
│       ├── client.py                          # direct Gemini + MCP stdio
│       ├── langchain_mcp_client_stdio.py      # LangGraph + MCP SSE
│       ├── .env                               # GEMINI_API_KEY + GOOGLE_API_KEY (you provide)
│       ├── pyproject.toml
│       └── uv.lock
├── tests/
│   ├── conftest.py
│   ├── test_client_helpers.py
│   ├── test_e2e_server.py
│   ├── test_e2e_gmail.py
│   └── README.md
├── pytest.ini
└── README.md
```

---

## Security notes

- `run_command` executes **arbitrary shell commands** by design. Only expose this server to trusted callers (i.e. your own client running locally).
- `servers/credentials.json` and `servers/token.json` grant full Gmail access. **Never commit them.** A `.gitignore` entry for both is strongly recommended.
- `.env` similarly contains your Gemini API key — keep it out of version control.

---

## License

Personal project — no license declared.
