"""The API client: the bot's typed wrapper around the Internal API.

Error codes become `InsufficientFunds` or `ValueError`. Transport failures become `ApiUnavailable`.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

import aiohttp
from fm01_schemas import (
	Balance,
	CreditRequest,
	DebitRequest,
	ErrorBody,
	ErrorCode,
	GuildLocale,
	GuildPrefix,
	LeaderboardEntry,
	LocaleOverride,
	MoveRequest,
	Prefix,
	TransferRequest,
	Wallet,
)
from pydantic import BaseModel, TypeAdapter, ValidationError

__all__ = ("ApiClient", "ApiError", "ApiUnavailable", "EconomyApi", "InsufficientFunds", "SettingsApi")

logger = logging.getLogger(__name__)

M = TypeVar("M")

ORIGIN_HEADER = "X-Fm01-Origin"


class ApiUnavailable(Exception):
	"""The API couldn't be reached or failed. The operation's outcome is unknown."""


class ApiError(Exception):
	"""The API refused the request for a reason the caller didn't expect.

	Args:
		status: The HTTP status.
		body: The error the API returned.
	"""

	def __init__(self, status: int, body: ErrorBody) -> None:
		super().__init__(f"{status} {body.code}: {body.message}")
		self.status = status
		self.code = body.code
		self.message = body.message


class InsufficientFunds(Exception):
	"""The wallet doesn't hold enough money for the operation."""


class ApiClient:
	"""One HTTP session to the Internal API, shared by every cog.

	Args:
		base_url: The API's base URL, e.g. ``http://api:8000``.
		token: ``API_INTERNAL_TOKEN``.
		origin: This bot instance's ID, sent as ``X-Fm01-Origin``.
		timeout: Seconds before a request counts as failed.
	"""

	def __init__(self, base_url: str, token: str, origin: str, *, timeout: float = 10) -> None:
		self._base = base_url.rstrip("/") + "/internal"
		self._headers = {"Authorization": f"Bearer {token}", ORIGIN_HEADER: origin}
		self._timeout = aiohttp.ClientTimeout(total=timeout)
		self._session: aiohttp.ClientSession | None = None
		self.economy = EconomyApi(self)
		self.settings = SettingsApi(self)

	async def close(self) -> None:
		"""Close the HTTP session. The next request opens a new one."""
		if self._session and not self._session.closed:
			await self._session.close()

	async def request(
		self, method: str, path: str, result: type[M], *, body: BaseModel | None = None, **params: Any
	) -> M:
		"""Send one request and parse the response.

		Args:
			method: The HTTP method.
			path: The path under ``/internal``.
			result: The type to parse the response as.
			body: The JSON body, if any.
			**params: Query parameters.

		Returns:
			The parsed response.

		Raises:
			ApiUnavailable: The API couldn't be reached, failed (5xx), or answered with something unparsable.
			InsufficientFunds: The API answered ``insufficient_funds``.
			ValueError: The API answered ``same_account`` or ``invalid_request``.
			ApiError: Any other refusal.
		"""
		data = await self.send(method, path, body=body, **params)
		try:
			return TypeAdapter(result).validate_json(data)
		except ValidationError as exc:
			raise ApiUnavailable(f"{method} {path}: unexpected response") from exc

	async def send(self, method: str, path: str, *, body: BaseModel | None = None, **params: Any) -> bytes:
		"""Send one request without parsing the response.

		Args:
			method: The HTTP method.
			path: The path under ``/internal``.
			body: The JSON body, if any.
			**params: Query parameters.

		Returns:
			The raw response body.

		Raises:
			ApiUnavailable: The API couldn't be reached or failed (5xx).
			InsufficientFunds: The API answered ``insufficient_funds``.
			ValueError: The API answered ``same_account`` or ``invalid_request``.
			ApiError: Any other refusal.
		"""
		if self._session is None or self._session.closed:
			self._session = aiohttp.ClientSession(headers=self._headers, timeout=self._timeout)
		payload = body.model_dump(mode="json") if body is not None else None
		try:
			async with self._session.request(method, self._base + path, json=payload, params=params or None) as resp:
				data = await resp.read()
				status = resp.status
		except (aiohttp.ClientError, TimeoutError) as exc:
			raise ApiUnavailable(f"{method} {path}: {exc!r}") from exc

		if status >= 500:
			raise ApiUnavailable(f"{method} {path}: HTTP {status}")
		if status >= 400:
			raise _refusal(status, data, f"{method} {path}")
		return data


def _refusal(status: int, data: bytes, what: str) -> Exception:
	"""Map a 4xx response to an exception.

	Args:
		status: The HTTP status.
		data: The response body.
		what: The method and path, for messages.

	Returns:
		The exception to raise. See `ApiClient.send`.
	"""
	try:
		body = ErrorBody.model_validate_json(data)
	except ValidationError:
		return ApiUnavailable(f"{what}: HTTP {status} without an error body")
	match body.code:
		case ErrorCode.INSUFFICIENT_FUNDS:
			return InsufficientFunds()
		case ErrorCode.SAME_ACCOUNT | ErrorCode.INVALID_REQUEST:
			return ValueError(body.message)
		case ErrorCode.UNAUTHORIZED:
			logger.error("The API rejected API_INTERNAL_TOKEN")
			return ApiUnavailable(f"{what}: {body.message}")
		case _:
			return ApiError(status, body)


class EconomyApi:
	"""The Ledger's operations. Every method can also raise `ApiUnavailable`.

	Args:
		client: The API client.
	"""

	def __init__(self, client: ApiClient) -> None:
		self._client = client

	async def balance(self, guild_id: int, user_id: int) -> Balance:
		"""Get a member's balance.

		Args:
			guild_id: The guild the account belongs to.
			user_id: The member.

		Returns:
			The balance. All zero if the member has no account.
		"""
		return await self._client.request("GET", f"/guilds/{guild_id}/economy/accounts/{user_id}", Balance)

	async def credit(self, guild_id: int, user_id: int, amount: int, wallet: Wallet = "cash") -> Balance:
		"""Add money to a member's wallet, paying off debt first.

		Args:
			guild_id: The guild the account belongs to.
			user_id: The member to pay.
			amount: How much to add. Positive.
			wallet: The wallet the money goes to.

		Returns:
			The new balance.
		"""
		body = CreditRequest(user_id=user_id, amount=amount, wallet=wallet)
		return await self._client.request("POST", f"/guilds/{guild_id}/economy/credit", Balance, body=body)

	async def debit(self, guild_id: int, user_id: int, amount: int, wallet: Wallet = "cash") -> Balance:
		"""Take money from a member's account.

		Args:
			guild_id: The guild the account belongs to.
			user_id: The member to charge.
			amount: How much to take. Positive.
			wallet: The wallet the money comes from. The bank may go negative.

		Returns:
			The new balance.

		Raises:
			InsufficientFunds: ``wallet`` is ``"cash"`` and the member holds less than ``amount``.
		"""
		body = DebitRequest(user_id=user_id, amount=amount, wallet=wallet)
		return await self._client.request("POST", f"/guilds/{guild_id}/economy/debit", Balance, body=body)

	async def move(self, guild_id: int, user_id: int, amount: int, source: Wallet, target: Wallet) -> Balance:
		"""Move money between a member's own wallets (deposit or withdraw).

		Args:
			guild_id: The guild the account belongs to.
			user_id: The member.
			amount: How much to move. Positive.
			source: The wallet the money leaves.
			target: The wallet the money reaches.

		Returns:
			The new balance.

		Raises:
			InsufficientFunds: ``source`` holds less than ``amount``.
		"""
		body = MoveRequest(user_id=user_id, amount=amount, source=source, target=target)
		return await self._client.request("POST", f"/guilds/{guild_id}/economy/move", Balance, body=body)

	async def transfer(self, guild_id: int, sender_id: int, recipient_id: int, amount: int) -> None:
		"""Give cash from one member to another, all or nothing.

		Args:
			guild_id: The guild both accounts belong to.
			sender_id: The member who pays.
			recipient_id: The member who receives.
			amount: How much cash to give. Positive.

		Raises:
			ValueError: The sender is the recipient.
			InsufficientFunds: The sender holds less cash than ``amount``.
		"""
		if sender_id == recipient_id:
			raise ValueError("cannot transfer to the same account")
		body = TransferRequest(sender_id=sender_id, recipient_id=recipient_id, amount=amount)
		await self._client.send("POST", f"/guilds/{guild_id}/economy/transfer", body=body)

	async def leaderboard(self, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
		"""List a guild's richest members.

		Args:
			guild_id: The guild.
			limit: The most members to return, up to 100.

		Returns:
			Members by cash plus bank, richest first.
		"""
		return await self._client.request(
			"GET", f"/guilds/{guild_id}/economy/leaderboard", list[LeaderboardEntry], limit=limit
		)


class SettingsApi:
	"""Guild settings operations. Every method can also raise `ApiUnavailable`.

	Args:
		client: The API client.
	"""

	def __init__(self, client: ApiClient) -> None:
		self._client = client

	async def prefix(self, guild_id: int) -> Prefix:
		"""Get a guild's prefix.

		Args:
			guild_id: The guild.

		Returns:
			The prefix. The default prefix for a new guild.
		"""
		return await self._client.request("GET", f"/guilds/{guild_id}/settings/prefix", Prefix)

	async def set_prefix(self, guild_id: int, value: Prefix) -> None:
		"""Set a guild's prefix.

		Args:
			guild_id: The guild.
			value: The new prefix.
		"""
		await self._client.send("PUT", f"/guilds/{guild_id}/settings/prefix", body=value)

	async def all_prefixes(self) -> list[GuildPrefix]:
		"""List every guild's prefix.

		Returns:
			The prefix of every guild the API knows.
		"""
		return await self._client.request("GET", "/settings/prefix", list[GuildPrefix])

	async def locale(self, guild_id: int) -> str | None:
		"""Get a guild's locale override.

		Args:
			guild_id: The guild.

		Returns:
			The locale. ``None`` if there is no override.
		"""
		return (await self._client.request("GET", f"/guilds/{guild_id}/settings/locale", LocaleOverride)).locale

	async def set_locale(self, guild_id: int, locale: str | None) -> None:
		"""Set a guild's locale override.

		Args:
			guild_id: The guild.
			locale: The locale. ``None`` removes the override.
		"""
		body = LocaleOverride(locale=locale)
		await self._client.send("PUT", f"/guilds/{guild_id}/settings/locale", body=body)

	async def all_locales(self) -> dict[int, str | None]:
		"""List every guild's locale override.

		Returns:
			The locale of every guild with an override, by guild ID.
		"""
		entries = await self._client.request("GET", "/settings/locale", list[GuildLocale])
		return {entry.guild_id: entry.locale for entry in entries}
