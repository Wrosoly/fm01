"""Wire models shared by the fm01 bot, API and dashboard.

TypeScript types are generated from the API's OpenAPI schema into ``shared/schemas/ts/``. Never edit those by hand.
"""

from fm01_schemas.dashboard import DashboardUser, ManagedGuild, SessionExchange, SessionGrant
from fm01_schemas.economy import (
	Amount,
	Balance,
	CreditRequest,
	DebitRequest,
	LeaderboardEntry,
	MoveRequest,
	TransferRequest,
	Wallet,
)
from fm01_schemas.errors import ErrorBody, ErrorCode
from fm01_schemas.events import EVENTS_CHANNEL, INVALIDATE_SETTING, InvalidateSetting
from fm01_schemas.settings import (
	LOCALE_SETTING,
	PREFIX_SETTING,
	GuildLocale,
	GuildPrefix,
	LocaleCode,
	LocaleOverride,
	Prefix,
	PrefixText,
)
from fm01_schemas.snowflake import Snowflake

__all__ = (
	"EVENTS_CHANNEL",
	"INVALIDATE_SETTING",
	"LOCALE_SETTING",
	"PREFIX_SETTING",
	"Amount",
	"Balance",
	"CreditRequest",
	"DashboardUser",
	"DebitRequest",
	"ErrorBody",
	"ErrorCode",
	"GuildLocale",
	"GuildPrefix",
	"InvalidateSetting",
	"LeaderboardEntry",
	"LocaleCode",
	"LocaleOverride",
	"ManagedGuild",
	"MoveRequest",
	"Prefix",
	"PrefixText",
	"SessionExchange",
	"SessionGrant",
	"Snowflake",
	"TransferRequest",
	"Wallet",
)
