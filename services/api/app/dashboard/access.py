"""The guild manager rule for the dashboard."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from api import ErrorCode, ManagedGuild

from app.dashboard.discord import DiscordClient, OAuthTokenSet
from app.dashboard.sessions import Session, SessionStore
from app.errors import ApiError

__all__ = ("ADMINISTRATOR", "MANAGE_GUILD", "GuildAccess", "is_guild_manager")

ADMINISTRATOR = 1 << 3
MANAGE_GUILD = 1 << 5
_REFRESH_MARGIN = timedelta(minutes=1)


def is_guild_manager(guild: dict) -> bool:
	"""Check whether the user owns the guild or has Administrator or Manage Server.

	Args:
		guild: One entry of Discord's ``/users/@me/guilds``.

	Returns:
		Whether the user is a guild manager.
	"""
	permissions = int(guild.get("permissions", 0))
	return bool(guild.get("owner")) or bool(permissions & (ADMINISTRATOR | MANAGE_GUILD))


class GuildAccess:
	"""Checks guild managers against the user's Discord guild list, cached in Redis.

	Args:
		discord: The Discord client.
		sessions: The session store, for saving refreshed Discord tokens.
		redis: The cache.
		ttl: How long a result is cached. A demoted user keeps access this long.
	"""

	def __init__(self, discord: DiscordClient, sessions: SessionStore, redis: aioredis.Redis, ttl: timedelta) -> None:
		self._discord = discord
		self._sessions = sessions
		self._redis = redis
		self._ttl = ttl

	async def managed_guilds(self, session: Session) -> list[ManagedGuild]:
		"""List the guilds the session's user manages, with or without the bot.

		Args:
			session: The user's dashboard session.

		Returns:
			The managed guilds.

		Raises:
			ApiError: ``unauthorized`` if Discord rejects the user's tokens, which also ends the session.
				``discord_unavailable`` if Discord fails.
		"""
		key = f"dashboard:managed:{session.id}"
		cached = await self._redis.get(key)
		if cached is not None:
			return [ManagedGuild.model_validate(guild) for guild in json.loads(cached)]
		access_token = await self._fresh_access_token(session)
		guilds = [
			ManagedGuild(id=guild["id"], name=guild["name"], icon=guild.get("icon"))
			for guild in await self._discord.current_user_guilds(access_token)
			if is_guild_manager(guild)
		]
		payload = json.dumps([guild.model_dump(mode="json") for guild in guilds])
		await self._redis.set(key, payload, ex=self._ttl)
		return guilds

	async def require_manager(self, session: Session, guild_id: int) -> None:
		"""Check that the session's user may configure a guild.

		Args:
			session: The user's dashboard session.
			guild_id: The guild.

		Raises:
			ApiError: ``forbidden`` if the user isn't a guild manager of it. ``not_found`` if the bot isn't in it.
				Also anything `managed_guilds` raises.
		"""
		if not any(guild.id == guild_id for guild in await self.managed_guilds(session)):
			raise ApiError(ErrorCode.FORBIDDEN, "you are not a manager of this guild")
		if not await self._bot_in_guild(guild_id):
			raise ApiError(ErrorCode.NOT_FOUND, "the bot is not in this guild")

	async def _bot_in_guild(self, guild_id: int) -> bool:
		"""Check whether the bot is in a guild, with caching.

		Args:
			guild_id: The guild.

		Returns:
			Whether the bot is a member.
		"""
		key = f"dashboard:bot_in_guild:{guild_id}"
		cached = await self._redis.get(key)
		if cached is not None:
			return cached in (b"1", "1")
		present = await self._discord.bot_in_guild(guild_id)
		await self._redis.set(key, "1" if present else "0", ex=self._ttl)
		return present

	async def _fresh_access_token(self, session: Session) -> str:
		"""Get the session's Discord access token, refreshed if it expires within a minute.

		Args:
			session: The user's dashboard session.

		Returns:
			A valid access token.

		Raises:
			ApiError: ``unauthorized`` if the refresh fails, which also ends the session. ``discord_unavailable`` if
				Discord fails.
		"""
		if session.discord.expires_at - _REFRESH_MARGIN > datetime.now(UTC):
			return session.discord.access_token
		try:
			tokens: OAuthTokenSet = await self._discord.refresh(session.discord.refresh_token)
		except ApiError as exc:
			if exc.code is ErrorCode.UNAUTHORIZED:
				await self._sessions.revoke(session.id)
			raise
		await self._sessions.update_tokens(session.id, tokens)
		return tokens.access_token
