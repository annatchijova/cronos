"""
CRONOS — dashboard entry point.

    python -m web

Environment:
    CRONOS_DB_PATH   SQLite database to read (default: cronos.db)
    CRONOS_WEB_HOST  bind address (default: 127.0.0.1)
    CRONOS_WEB_PORT  port (default: 8300)
"""

import os

import uvicorn


def main() -> None:
    host = os.environ.get("CRONOS_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("CRONOS_WEB_PORT", "8300"))
    uvicorn.run("web.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
