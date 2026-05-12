"""
Shared pytest configuration.

Adds the project's `clients/mcp-client` and `servers` directories to sys.path
so tests can import `client` and `server__v2` directly without packaging.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for sub in ("clients/mcp-client", "servers"):
    path = os.path.join(ROOT, sub)
    if path not in sys.path:
        sys.path.insert(0, path)
