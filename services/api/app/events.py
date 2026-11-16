"""Change events for bot instances, over the Redis event bus."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from fm01_schemas import EVENTS_CHANNEL, InvalidateSetting

__all__ = ("Announcer",)

logger = logging.getLogger(__name__)


class Announcer:
	"""Publishes events to bot instances.

	Args:
		redis: The Redis the event bus runs on.
	"""

	def __init__(self, redis: aioredis.Redis) -> None:
		self._redis = redis

	async def setting_changed(self, key: str, guild_id: int, origin: str | None) -> None:
		"""Tell bot instances to reload a guild setting. Logs Redis failures instead of raising.

		Args:
			key: The setting's key on the bot's ``GuildSettings``.
			guild_id: The guild whose setting changed.
			origin: The bot instance that caused the change. ``None`` for the dashboard.
		"""
		event = InvalidateSetting(key=key, guild_id=guild_id, origin=origin)
		try:
			await self._redis.publish(EVENTS_CHANNEL, event.model_dump_json())
		except aioredis.RedisError:
			# The write already committed. Stale bot caches until they reload beat failing the request.
			logger.exception(f"Failed to announce change of setting {key!r} for guild {guild_id}")
