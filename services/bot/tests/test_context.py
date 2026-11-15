from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.context import Context
from discord.ext import commands


def _ctx(module: str) -> Context:
	ctx = Context.__new__(Context)
	ctx.command = MagicMock(spec=commands.Command, module=module)
	ctx.bot = MagicMock()
	ctx.bot.custom_response.get_message = AsyncMock(return_value="localized")
	return ctx


@pytest.fixture
def base_send(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
	send = AsyncMock()
	monkeypatch.setattr(commands.Context, "send", send)
	return send


@pytest.mark.asyncio
async def test_own_commands_localize_positional_key(base_send: AsyncMock):
	ctx = _ctx("cogs.basic")

	await ctx.send("basic.ping")

	ctx.bot.custom_response.get_message.assert_awaited_once()
	assert base_send.call_args.kwargs["content"] == "localized"


@pytest.mark.asyncio
async def test_third_party_commands_send_positional_text_raw(base_send: AsyncMock):
	ctx = _ctx("jishaku.features.python")

	await ctx.send("[{'id': 4}]")

	ctx.bot.custom_response.get_message.assert_not_called()
	assert base_send.call_args.kwargs["content"] == "[{'id': 4}]"
