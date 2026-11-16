"""The error body every API failure returns."""

from enum import StrEnum

from pydantic import BaseModel

__all__ = ("ErrorBody", "ErrorCode")


class ErrorCode(StrEnum):
	"""Why a request failed. Clients branch on this, never on the message."""

	INVALID_REQUEST = "invalid_request"
	UNAUTHORIZED = "unauthorized"
	"""No credentials, or credentials that are wrong or expired."""
	FORBIDDEN = "forbidden"
	"""Valid credentials that don't allow this, e.g. a signed-in user who isn't a guild manager."""
	NOT_FOUND = "not_found"
	INSUFFICIENT_FUNDS = "insufficient_funds"
	"""The wallet doesn't hold enough money for the Ledger operation."""
	SAME_ACCOUNT = "same_account"
	"""A Ledger transfer from a member to themselves."""
	DISCORD_UNAVAILABLE = "discord_unavailable"
	"""Discord's API failed or rate limited a request the API made on the caller's behalf."""


class ErrorBody(BaseModel):
	"""What the API returns when a request fails."""

	code: ErrorCode
	message: str
	"""A human-readable detail, for logs. Not localized and not stable."""
