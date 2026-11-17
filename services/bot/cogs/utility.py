from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Literal

import aiohttp
from core import Bot, Context, command
from discord.ext import commands

logger = logging.getLogger(__name__)

type UnitKind = Literal["distance", "weight", "currency", "crypto"]

# Meters per unit
DISTANCE_UNITS: dict[str, float] = {
	"mm": 0.001,
	"cm": 0.01,
	"m": 1.0,
	"km": 1000.0,
	"in": 0.0254,
	"inch": 0.0254,
	"inches": 0.0254,
	"ft": 0.3048,
	"feet": 0.3048,
	"foot": 0.3048,
	"yd": 0.9144,
	"yard": 0.9144,
	"yards": 0.9144,
	"mi": 1609.344,
	"mile": 1609.344,
	"miles": 1609.344,
	"nmi": 1852.0,
}

# Kilograms per unit, "t" is the metric tonne, "ton" the US short ton
WEIGHT_UNITS: dict[str, float] = {
	"mg": 0.000001,
	"g": 0.001,
	"kg": 1.0,
	"t": 1000.0,
	"oz": 0.028349523125,
	"lb": 0.45359237,
	"lbs": 0.45359237,
	"st": 6.35029318,
	"ton": 907.18474,
}

COINBASE_API = "https://api.coinbase.com/v2"
RATES_TTL = 300.0
CURRENCIES_TTL = 86400.0


class UnknownUnitError(Exception):
	"""Raised when a unit is neither a distance, a weight, nor a known currency."""

	def __init__(self, unit: str) -> None:
		super().__init__(unit)
		self.unit = unit


@dataclass(slots=True)
class Unit:
	"""A parsed unit.

	Attributes:
		kind: What the unit measures.
		symbol: The unit as shown to the user (lowercase for distance and weight, uppercase for money).
		factor: Base units per one of this unit: meters, kilograms, or units per 1 USD for money.
	"""

	kind: UnitKind
	symbol: str
	factor: float

	@property
	def is_money(self) -> bool:
		return self.kind in ("currency", "crypto")


class ExchangeRates:
	"""Fiat and cryptocurrency rates from Coinbase, cached in memory.

	Every rate is quoted against USD, so any two currencies, fiat or crypto, convert through it.
	"""

	def __init__(self) -> None:
		self.session: aiohttp.ClientSession | None = None
		self._rates: dict[str, float] = {}
		self._rates_at: float | None = None
		self._fiat: frozenset[str] = frozenset()
		self._crypto: frozenset[str] = frozenset()
		self._currencies_at: float | None = None
		self._lock = asyncio.Lock()

	async def close(self) -> None:
		if self.session and not self.session.closed:
			await self.session.close()

	async def _get(self, path: str) -> object:
		if self.session is None or self.session.closed:
			self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
		async with self.session.get(f"{COINBASE_API}/{path}") as response:
			response.raise_for_status()
			return (await response.json())["data"]

	async def _refresh(self) -> None:
		now = time.monotonic()
		if self._currencies_at is None or now - self._currencies_at > CURRENCIES_TTL:
			fiat, crypto = await asyncio.gather(self._get("currencies"), self._get("currencies/crypto"))
			assert isinstance(fiat, list) and isinstance(crypto, list)
			self._fiat = frozenset(entry["id"] for entry in fiat)
			self._crypto = frozenset(entry["code"] for entry in crypto)
			self._currencies_at = now
		if self._rates_at is None or now - self._rates_at > RATES_TTL:
			data = await self._get("exchange-rates?currency=USD")
			assert isinstance(data, dict)
			self._rates = {code: float(rate) for code, rate in data["rates"].items() if float(rate) > 0}
			self._rates_at = now

	async def unit(self, code: str) -> Unit:
		"""Look up a currency by its code.

		Args:
			code: A currency code in any case, e.g. ``eur`` or ``BTC``.

		Raises:
			UnknownUnitError: Coinbase has no rate for ``code``.
			aiohttp.ClientError: Coinbase could not be reached.
		"""
		async with self._lock:
			await self._refresh()
		code = code.upper()
		rate = self._rates.get(code)
		if rate is None:
			raise UnknownUnitError(code)
		# Fiat wins on a clash; anything Coinbase rates but does not list as fiat is treated as crypto.
		kind: UnitKind = "currency" if code in self._fiat or code == "USD" else "crypto"
		return Unit(kind, code, rate)


def physical_unit(unit: str) -> Unit | None:
	"""Parse a distance or weight unit.

	Returns:
		The unit, or None if ``unit`` is neither a distance nor a weight.
	"""
	symbol = unit.lower()
	if symbol in DISTANCE_UNITS:
		return Unit("distance", symbol, DISTANCE_UNITS[symbol])
	if symbol in WEIGHT_UNITS:
		return Unit("weight", symbol, WEIGHT_UNITS[symbol])
	return None


def convert_amount(amount: float, source: Unit, target: Unit) -> float:
	"""Convert ``amount`` of ``source`` into ``target``. Both units must measure the same thing."""
	if source.is_money:
		return amount / source.factor * target.factor
	return amount * source.factor / target.factor


class Utility(commands.GroupCog, name="Utility", group_name="utility"):
	def __init__(self, client: Bot) -> None:
		self.client = client
		self.rates = ExchangeRates()

	async def cog_unload(self) -> None:
		await self.rates.close()

	async def _parse(self, unit: str) -> Unit:
		return physical_unit(unit) or await self.rates.unit(unit)

	@command()
	async def convert(
		self, ctx: Context, amount: commands.Range[float, 0, 1_000_000_000_000], unit: str, to: str
	) -> None:
		try:
			source = await self._parse(unit)
			target = await self._parse(to)
		except UnknownUnitError as error:
			await ctx.send("convert.errors.unknown_unit", unit=error.unit)
			return
		except (aiohttp.ClientError, TimeoutError, KeyError, ValueError) as error:
			logger.warning(f"Exchange rate lookup failed: {error!r}")
			await ctx.send("convert.errors.unavailable")
			return

		if source.is_money != target.is_money or (not source.is_money and source.kind != target.kind):
			await ctx.send("convert.errors.incompatible", unit=source.symbol, to=target.symbol)
			return

		kind = "crypto" if "crypto" in (source.kind, target.kind) else source.kind
		await ctx.send(
			f"convert.{kind}",
			amount=amount,
			unit=source.symbol,
			result=convert_amount(amount, source, target),
			to=target.symbol,
		)


async def setup(client: Bot) -> None:
	await client.add_cog(Utility(client))
