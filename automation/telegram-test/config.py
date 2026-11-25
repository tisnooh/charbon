"""Fail-closed settings. This build cannot publish to the official channel."""
from __future__ import annotations

import os
from dataclasses import dataclass

TEST_CHANNEL_ID = -1003912244927


def enabled(name: str) -> bool:
    return os.getenv(name, 'false').strip().lower() == 'true'


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_key: str
    openai_model: str
    owner_id: int
    channel_id: int
    sqlite_path: str
    publishing_enabled: bool
    assistant_enabled: bool
    allow_webhook_takeover: bool

    @classmethod
    def load(cls) -> 'Settings':
        token = os.getenv('TELEGRAM_BOT_TOKEN','').strip()
        owner = os.getenv('OWNER_TELEGRAM_ID', '').strip()
        channel = os.getenv('TEST_CHANNEL_ID','').strip()
        if not token or not owner or not channel:
            raise ValueError('Missing required bot token, owner ID or test channel ID')
        if int(channel) != TEST_CHANNEL_ID:
            raise ValueError('Safety stop: only CHARBON TEST is an allowed channel')
        if int(owner) <= 0:
            raise ValueError('OWNER_TELEGRAM_ID must be a positive integer')
        return cls(
            bot_token=token,
            openai_key=os.getenv('OPENAI_API_KEY','').strip(),
            openai_model=os.getenv('OPENAI_MODEL','gpt-5-mini').strip(),
            owner_id=int(owner), channel_id=int(channel),
            sqlite_path=os.getenv('SQLITE_PATH','/data/charbon-test.sqlite3'),
            publishing_enabled=enabled('ENABLE_PUBLISH'),
            assistant_enabled=enabled('ENABLE_ASSISTANT'),
            allow_webhook_takeover=enabled('ALLOW_WEBHOOK_TAKEOVER'),
        )
