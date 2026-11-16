"""The shop's charge-then-grant flow. The Ledger itself lives in the API and is tested there."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import asyncpg
import discord
import pytest
from cogs.economy import InsufficientFunds, Shop

from api import Balance, Wallet

GUILD = 1
ALICE = 10


class FakeLedger:
	"""The API client's economy operations, in memory, with the Ledger's cash rule."""

	def __init__(self) -> None:
		self.balances: dict[int, Balance] = {}

	async def balance(self, guild_id: int, user_id: int) -> Balance:
		return self.balances.get(user_id, Balance())

	async def add_money(self, guild_id: int, user_id: int, amount: int, wallet: Wallet = "cash") -> Balance:
		bal = await self.balance(guild_id, user_id)
		self.balances[user_id] = bal.model_copy(update={wallet: bal[wallet] + amount})
		return self.balances[user_id]

	async def remove_money(self, guild_id: int, user_id: int, amount: int, wallet: Wallet = "cash") -> Balance:
		bal = await self.balance(guild_id, user_id)
		if wallet == "cash" and bal.cash < amount:
			raise InsufficientFunds
		self.balances[user_id] = bal.model_copy(update={wallet: bal[wallet] - amount})
		return self.balances[user_id]


def _buy_ctx(add_roles: AsyncMock) -> MagicMock:
	ctx = MagicMock()
	ctx.guild.id = GUILD
	ctx.guild.get_role.return_value = MagicMock(spec=discord.Role, id=5, name="VIP")
	ctx.author = MagicMock(spec=discord.Member, id=ALICE)
	ctx.author.add_roles = add_roles
	ctx.send = AsyncMock()
	return ctx


def _shop(db: asyncpg.Pool, ledger: FakeLedger) -> Shop:
	bot = MagicMock()
	bot.db = db
	bot.api.economy = ledger
	return Shop(bot)


async def _add_vip(db: asyncpg.Pool) -> None:
	await db.execute(
		"INSERT INTO shop (item_name, item_description, item_price, role, guild_id, creator_id) "
		"VALUES ('VIP', 'd', 100, 5, $1, 1)",
		GUILD,
	)


@pytest.mark.db
async def test_buy_charges_then_grants(db):
	await _add_vip(db)
	ledger = FakeLedger()
	await ledger.add_money(GUILD, ALICE, 150)
	ctx = _buy_ctx(AsyncMock())
	shop = _shop(db, ledger)

	await shop.buy.callback(shop, ctx, "vip")

	ctx.author.add_roles.assert_awaited_once()
	assert await ledger.balance(GUILD, ALICE) == Balance(cash=50)
	assert ctx.send.call_args.args[0] == "shop.buy.success"


@pytest.mark.db
async def test_buy_without_enough_cash_grants_nothing(db):
	await _add_vip(db)
	ctx = _buy_ctx(AsyncMock())
	shop = _shop(db, FakeLedger())

	await shop.buy.callback(shop, ctx, "vip")

	ctx.author.add_roles.assert_not_awaited()
	assert ctx.send.call_args.args[0] == "shop.buy.errors.balance"


@pytest.mark.db
async def test_buy_refunds_when_the_role_cannot_be_given(db):
	"""Regression: the role used to be granted before charging, so a failed charge meant a free role."""
	await _add_vip(db)
	ledger = FakeLedger()
	await ledger.add_money(GUILD, ALICE, 150)
	ctx = _buy_ctx(AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "missing permissions")))
	shop = _shop(db, ledger)

	await shop.buy.callback(shop, ctx, "vip")

	assert await ledger.balance(GUILD, ALICE) == Balance(cash=150)
	assert ctx.send.call_args.args[0] == "shop.buy.errors.role_failed"
