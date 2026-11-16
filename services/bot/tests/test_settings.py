"""GuildSettings: caching and cross-instance invalidation, with a shared in-process event bus.

Database-backed settings run against real PostgreSQL. Remote settings run against `FakeApi`, which behaves like the
Internal API: it persists writes and announces them itself, echoing the writer's origin.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import pytest
from cogs.mod.cases import retention_setting
from core.clustering import LocalEventBus
from core.settings import EVENTS_CHANNEL, GuildSetting, GuildSettings, Prefix

pytestmark = pytest.mark.db

GUILD = 42


class FakeApi:
	"""Remote setting storage shared by every instance, announcing each write on the bus like the API does."""

	def __init__(self, bus: LocalEventBus) -> None:
		self.bus = bus
		self.values: dict[str, dict[int, Any]] = {"prefix": {}, "locale": {}}
		self.defaults: dict[str, Any] = {"prefix": ("?!", True), "locale": None}
		self.loads = 0

	async def write(self, key: str, guild_id: int, value: Any, origin: str | None) -> None:
		self.values[key][guild_id] = value
		await self.bus.publish(
			EVENTS_CHANNEL, {"type": "INVALIDATE_SETTING", "key": key, "guild_id": str(guild_id), "origin": origin}
		)

	def remote(self, settings: GuildSettings, key: str) -> GuildSetting[Any]:
		async def load(guild_id: int) -> Any:
			self.loads += 1
			return self.values[key].get(guild_id, self.defaults[key])

		async def save(guild_id: int, value: Any) -> None:
			await self.write(key, guild_id, value, settings.origin)

		async def load_all() -> dict[int, Any]:
			return dict(self.values[key])

		return settings.add_remote(key, load, save, load_all=load_all)


class Instance:
	"""One bot process: its own caches, sharing the database, the API and the event bus with the others."""

	def __init__(self, db: asyncpg.Pool, bus: LocalEventBus, api: FakeApi) -> None:
		self.settings = GuildSettings(lambda: db, bus)
		self.prefix: GuildSetting[Prefix] = api.remote(self.settings, "prefix")
		self.locale: GuildSetting[str | None] = api.remote(self.settings, "locale")
		self.retention = retention_setting(self.settings)


async def settle() -> None:
	"""Let LocalEventBus deliver (it dispatches in tasks) and the handlers finish their queries."""
	for _ in range(20):
		await asyncio.sleep(0.01)


@pytest.fixture
def bus() -> LocalEventBus:
	return LocalEventBus()


@pytest.fixture
def api(bus: LocalEventBus) -> FakeApi:
	return FakeApi(bus)


@pytest.fixture
async def instances(db: asyncpg.Pool, bus: LocalEventBus, api: FakeApi) -> tuple[Instance, Instance]:
	a, b = Instance(db, bus, api), Instance(db, bus, api)
	for instance in (a, b):

		async def handler(event: dict, settings: GuildSettings = instance.settings) -> None:
			await settings.handle_event(event)

		await bus.subscribe(EVENTS_CHANNEL, handler)
	return a, b


async def test_loading_a_new_guild_creates_its_row_with_database_defaults(db, instances):
	a, _ = instances

	assert await a.retention.get(GUILD) == "keep"
	assert await db.fetchval("SELECT count(*) FROM mod_config WHERE guild_id = $1", GUILD) == 1


async def test_set_persists_and_updates_the_writer_immediately(db, instances):
	a, _ = instances

	await a.retention.set(GUILD, "delete")

	assert a.retention.cache[GUILD] == "delete"
	assert await db.fetchval("SELECT case_retention FROM mod_config WHERE guild_id = $1", GUILD) == "delete"


async def test_remote_set_updates_the_writer_and_leaves_announcing_to_the_api(instances, api, bus):
	a, _ = instances
	published: list[dict] = []

	async def record(event: dict) -> None:
		published.append(event)

	await bus.subscribe(EVENTS_CHANNEL, record)

	await a.prefix.set(GUILD, ("!", False))
	await settle()

	assert a.prefix.cache[GUILD] == ("!", False)
	assert api.values["prefix"][GUILD] == ("!", False)
	assert len(published) == 1  # the API's announcement only; the bot didn't announce again


async def test_preloaded_remote_setting_is_reloaded_on_other_instances(instances):
	a, b = instances
	await a.settings.preload()
	await b.settings.preload()
	assert GUILD not in b.locale.cache

	await a.locale.set(GUILD, "hu")
	await settle()
	assert b.locale.cache[GUILD] == "hu"  # synchronous readers see it without a get()

	await a.locale.set(GUILD, None)
	await settle()
	assert b.locale.cache[GUILD] is None


async def test_dashboard_change_reaches_every_instance(instances, api):
	a, b = instances
	await a.settings.preload()
	await b.settings.preload()

	await api.write("prefix", GUILD, ("$", True), origin=None)
	await settle()

	assert a.prefix.cache[GUILD] == ("$", True)
	assert b.prefix.cache[GUILD] == ("$", True)


async def test_writer_skips_the_echo_of_its_own_remote_write(instances, api):
	a, b = instances
	await b.settings.preload()
	await a.prefix.set(GUILD, ("!", True))
	api.values["prefix"][GUILD] = ("?", True)  # changed behind everyone's back before the echo arrives
	await settle()

	# Had the writer handled the API's echo of its own write, it would have reloaded and seen "?".
	assert a.prefix.cache[GUILD] == ("!", True)
	assert b.prefix.cache[GUILD] == ("?", True)


async def test_lazy_setting_is_dropped_on_other_instances_and_reloaded_on_next_get(instances):
	a, b = instances
	assert await b.retention.get(GUILD) == "keep"

	await a.retention.set(GUILD, "delete")
	await settle()

	assert GUILD not in b.retention.cache
	assert await b.retention.get(GUILD) == "delete"


async def test_writer_ignores_its_own_invalidation(db, instances):
	a, _ = instances
	await a.retention.set(GUILD, "delete")
	await db.execute("UPDATE mod_config SET case_retention = 'keep' WHERE guild_id = $1", GUILD)
	await settle()

	# Had the writer handled its own event, it would have dropped the value and re-read "keep".
	assert a.retention.cache[GUILD] == "delete"


async def test_preload_reads_every_guild(instances, api):
	a, _ = instances
	api.values["prefix"] = {1: ("!", True), 2: ("$", False)}

	await a.settings.preload()

	assert a.prefix.cache == {1: ("!", True), 2: ("$", False)}


async def test_forget_guild_drops_every_setting(instances):
	a, _ = instances
	await a.prefix.get(GUILD)
	await a.retention.get(GUILD)

	a.settings.forget_guild(GUILD)

	assert GUILD not in a.prefix.cache
	assert GUILD not in a.retention.cache


async def test_registering_a_key_twice_returns_the_same_setting(instances):
	a, _ = instances
	assert retention_setting(a.settings) is a.retention


async def test_targeted_write_reported_with_changed_reaches_other_instances(db, instances):
	a, b = instances

	async def load(pool: asyncpg.Pool, guild_id: int) -> bool:
		return bool(await pool.fetchval("SELECT stack_roles FROM level_config WHERE guild_id = $1", guild_id))

	stack_a = a.settings.add("test.stack", load)
	stack_b = b.settings.add("test.stack", load)
	assert await stack_b.get(GUILD) is False

	await db.execute("INSERT INTO level_config (guild_id, stack_roles) VALUES ($1, true)", GUILD)
	await stack_a.changed(GUILD)
	await settle()

	assert await stack_a.get(GUILD) is True
	assert await stack_b.get(GUILD) is True
	with pytest.raises(TypeError):
		await stack_a.set(GUILD, False)
