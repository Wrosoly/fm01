"""Wire models shared by the fm01 bot, API and dashboard.

TypeScript types are generated from the API's OpenAPI schema into ``shared/schemas/ts/``. Never edit those by hand.
"""

from api.dashboard import DashboardUser, ManagedGuild, SessionExchange, SessionGrant
from api.economy import (
	AddMoneyRequest,
	Amount,
	Balance,
	LeaderboardEntry,
	MoveRequest,
	RemoveMoneyRequest,
	TransferRequest,
	Wallet,
)
from api.errors import ErrorBody, ErrorCode
from api.events import EVENTS_CHANNEL, INVALIDATE_SETTING, InvalidateSetting
from api.settings import (
	LOCALE_SETTING,
	PREFIX_SETTING,
	GuildLocale,
	GuildPrefix,
	LocaleCode,
	LocaleOverride,
	Prefix,
	PrefixText,
)
from api.snowflake import Snowflake

__all__ = (
	"EVENTS_CHANNEL",
	"INVALIDATE_SETTING",
	"LOCALE_SETTING",
	"PREFIX_SETTING",
	"AddMoneyRequest",
	"Amount",
	"Balance",
	"DashboardUser",
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
	"RemoveMoneyRequest",
	"SessionExchange",
	"SessionGrant",
	"Snowflake",
	"TransferRequest",
	"Wallet",
)
