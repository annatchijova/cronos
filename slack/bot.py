"""
CRONOS — Bolt async app factory.
Wires together: slash commands, demo agent message handler,
action handler for "Explain →" buttons.
"""

import logging

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from config import Config
from cronos.store import TraceStore
from slack.commands import register_commands
from demo.agent import DemoAgent

log = logging.getLogger("cronos.bot")


def create_app(config: Config, store: TraceStore) -> tuple[AsyncApp, AsyncSocketModeHandler]:
    """
    Build and wire the Bolt app.
    Returns (app, handler) — caller must await handler.start().
    """
    app = AsyncApp(
        token=config.SLACK_BOT_TOKEN,
        signing_secret=config.SLACK_SIGNING_SECRET,
    )

    # Slash commands
    register_commands(app, store)

    # Demo agent — reacts to @mentions or keywords in watched channels
    demo = DemoAgent(store)

    @app.event("app_mention")
    async def handle_mention(event, say, client):
        channel = event.get("channel", "")
        user    = event.get("user", "")
        text    = event.get("text", "")
        ts      = event.get("ts", "")
        await demo.handle_message(
            text=text,
            channel_id=channel,
            user_id=user,
            thread_ts=ts,
            say=say,
            client=client,
        )

    @app.event("message")
    async def handle_message(event, say, client):
        # Only handle messages in watched channels (if configured)
        channel = event.get("channel", "")
        if config.WATCH_CHANNELS and channel not in config.WATCH_CHANNELS:
            return
        # Skip bot messages and retries
        if event.get("bot_id") or event.get("subtype") in ("bot_message", "message_changed"):
            return
        user = event.get("user", "")
        text = event.get("text", "")
        ts   = event.get("ts", "")
        if not text or not user:
            return
        await demo.handle_message(
            text=text,
            channel_id=channel,
            user_id=user,
            thread_ts=ts,
            say=say,
            client=client,
        )

    # "Explain →" button in trace list
    @app.action("cronos_explain_trace")
    async def handle_explain_button(ack, body, respond):
        await ack()
        trace_id = body["actions"][0]["value"]
        trace = store.load_trace(trace_id)
        if not trace:
            await respond(text=f"Trace `{trace_id[:8]}` not found.")
            return
        from slack.output import format_trace_explain
        await respond(
            blocks=format_trace_explain(trace),
            text="CRONOS trace explanation",
            replace_original=False,
        )

    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    return app, handler
