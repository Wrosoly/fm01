"""Authentication for the Internal API and the Dashboard API."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fm01_schemas import ErrorCode, Snowflake

from app.dashboard.sessions import Session
from app.errors import ApiError
from app.state import AppState, get_state

__all__ = ("CurrentSession", "ManagedGuildId", "Origin", "State", "require_internal")

State = Annotated[AppState, Depends(get_state)]

_bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def _token(credentials: HTTPAuthorizationCredentials | None) -> str:
	"""Get the bearer token from the credentials.

	Args:
		credentials: The parsed ``Authorization`` header, if any.

	Returns:
		The bearer token.

	Raises:
		ApiError: ``unauthorized`` if there is no token.
	"""
	if credentials is None or not credentials.credentials:
		raise ApiError(ErrorCode.UNAUTHORIZED, "missing bearer token")
	return credentials.credentials


async def require_internal(state: State, credentials: Credentials) -> None:
	"""Allow only callers with ``API_INTERNAL_TOKEN``.

	Args:
		state: The app state.
		credentials: The parsed ``Authorization`` header, if any.

	Raises:
		ApiError: ``unauthorized`` if the token is missing or wrong.
	"""
	if not hmac.compare_digest(_token(credentials).encode(), state.config.internal_token.encode()):
		raise ApiError(ErrorCode.UNAUTHORIZED, "invalid internal token")


Origin = Annotated[
	str | None,
	Header(
		alias="X-Fm01-Origin",
		description="The calling bot instance. Echoed in the change events it causes, so it can skip them.",
	),
]


async def current_session(state: State, credentials: Credentials) -> Session:
	"""Get the dashboard session of the bearer token.

	Args:
		state: The app state.
		credentials: The parsed ``Authorization`` header, if any.

	Returns:
		The session.

	Raises:
		ApiError: ``unauthorized`` if the token is missing, unknown or expired.
	"""
	session = await state.sessions.get(_token(credentials))
	if session is None:
		raise ApiError(ErrorCode.UNAUTHORIZED, "invalid or expired session")
	return session


CurrentSession = Annotated[Session, Depends(current_session)]


async def managed_guild_id(guild_id: Snowflake, state: State, session: CurrentSession) -> int:
	"""Check that the session's user is a guild manager of the guild.

	Args:
		guild_id: The ``guild_id`` path parameter.
		state: The app state.
		session: The caller's dashboard session.

	Returns:
		The guild ID.

	Raises:
		ApiError: ``forbidden`` or ``not_found``. See `GuildAccess.require_manager`.
	"""
	await state.access.require_manager(session, guild_id)
	return guild_id


ManagedGuildId = Annotated[int, Depends(managed_guild_id)]
