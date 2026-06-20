"""
CRONOS — entry point.
Validates credentials, initializes the store, starts the Bolt Socket Mode handler.
"""

import asyncio
import logging

from config import Config
from cronos.store import TraceStore
from slack.bot import create_app

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("cronos.main")


async def main() -> None:
    config = Config()
    config.validate_credentials()

    log.info("CRONOS starting — DB: %s", config.CRONOS_DB_PATH)
    store = TraceStore(config.CRONOS_DB_PATH)

    _, handler = create_app(config, store)
    log.info("CRONOS ready — Socket Mode connected")
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
