"""The dashboard session store.

Stores only the SHA-256 hash of each session token, and the Discord tokens Fernet-encrypted.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
from cryptography.fernet import Fernet, InvalidToken
from fm01_schemas import DashboardUser

from app.dashboard.discord import TokenSet

__all__ = ("Session", "SessionStore")


@dataclass(frozen=True, slots=True)
class Session:
	"""A signed-in dashboard user.

	Attributes:
		id: The session token's SHA-256 hash, in hex.
		user: The user's Discord profile at sign-in.
		discord: The user's Discord tokens, decrypted.
		expires_at: When the session ends.
	"""

	id: str
	user: DashboardUser
	discord: TokenSet
	expires_at: datetime


def _hash(token: str) -> str:
	"""Hash a session token. Unsalted, since the token is 256 random bits.

	Args:
		token: The session token.

	Returns:
		The SHA-256 hash, in hex.
	"""
	return hashlib.sha256(token.encode()).hexdigest()


class SessionStore:
	"""Creates, reads and ends dashboard sessions.

	Args:
		db: The database pool.
		key: The Fernet key the Discord tokens are encrypted with.
		ttl: How long a new session lasts.
	"""

	def __init__(self, db: asyncpg.Pool, key: str, ttl: timedelta) -> None:
		self._db = db
		self._fernet = Fernet(key.encode())
		self._ttl = ttl

	async def create(self, user: DashboardUser, tokens: TokenSet) -> tuple[str, datetime]:
		"""Open a session for a user. Also deletes expired sessions.

		Args:
			user: The user's Discord profile.
			tokens: The user's Discord tokens.

		Returns:
			The session token and its expiry. The token can't be recovered later.
		"""
		token = secrets.token_urlsafe(32)
		expires_at = datetime.now(UTC) + self._ttl
		async with self._db.acquire() as conn, conn.transaction():
			await conn.execute("DELETE FROM dashboard_sessions WHERE expires_at < now()")
			await conn.execute(
				"INSERT INTO dashboard_sessions "
				"(id, user_id, user_profile, access_token, refresh_token, discord_expires_at, scopes, expires_at) "
				"VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
				_hash(token),
				user.id,
				user.model_dump(mode="json"),
				self._encrypt(tokens.access_token),
				self._encrypt(tokens.refresh_token),
				tokens.expires_at,
				sorted(tokens.scopes),
				expires_at,
			)
		return token, expires_at

	async def get(self, token: str) -> Session | None:
		"""Look up a session by its token.

		Args:
			token: The session token.

		Returns:
			The session. ``None`` if it's unknown, expired or encrypted with an old key.
		"""
		row = await self._db.fetchrow(
			"SELECT * FROM dashboard_sessions WHERE id = $1 AND expires_at > now()", _hash(token)
		)
		if row is None:
			return None
		try:
			tokens = TokenSet(
				access_token=self._decrypt(row["access_token"]),
				refresh_token=self._decrypt(row["refresh_token"]),
				expires_at=row["discord_expires_at"],
				scopes=frozenset(row["scopes"]),
			)
		except InvalidToken:
			return None
		return Session(
			id=row["id"],
			user=DashboardUser.model_validate(row["user_profile"]),
			discord=tokens,
			expires_at=row["expires_at"],
		)

	async def update_tokens(self, session_id: str, tokens: TokenSet) -> None:
		"""Replace a session's Discord tokens.

		Args:
			session_id: The session.
			tokens: The refreshed tokens.
		"""
		await self._db.execute(
			"UPDATE dashboard_sessions SET access_token = $2, refresh_token = $3, discord_expires_at = $4, scopes = $5 "
			"WHERE id = $1",
			session_id,
			self._encrypt(tokens.access_token),
			self._encrypt(tokens.refresh_token),
			tokens.expires_at,
			sorted(tokens.scopes),
		)

	async def revoke(self, session_id: str) -> None:
		"""End a session.

		Args:
			session_id: The session.
		"""
		await self._db.execute("DELETE FROM dashboard_sessions WHERE id = $1", session_id)

	def _encrypt(self, value: str) -> str:
		"""Encrypt a value with the session key.

		Args:
			value: The plaintext.

		Returns:
			The Fernet token.
		"""
		return self._fernet.encrypt(value.encode()).decode()

	def _decrypt(self, value: str) -> str:
		"""Decrypt a value with the session key.

		Args:
			value: The Fernet token.

		Returns:
			The plaintext.

		Raises:
			InvalidToken: The value wasn't encrypted with this key.
		"""
		return self._fernet.decrypt(value.encode()).decode()
