"""The PostgreSQL connection pool."""

from __future__ import annotations

import json

import asyncpg

__all__ = ("create_pool", "init_connection")


async def init_connection(connection: asyncpg.Connection) -> None:
	"""Set up ``json`` and ``jsonb`` codecs on a new connection.

	Args:
		connection: The new connection.
	"""
	await connection.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
	await connection.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_pool(dsn: str, *, min_size: int = 2, max_size: int = 20) -> asyncpg.Pool:
	"""Open a connection pool with JSON codecs.

	Args:
		dsn: The PostgreSQL DSN.
		min_size: The fewest connections to keep open.
		max_size: The most connections to open.

	Returns:
		The pool.
	"""
	pool = await asyncpg.create_pool(
		dsn, min_size=min_size, max_size=max_size, init=init_connection, max_inactive_connection_lifetime=120
	)
	assert pool is not None
	return pool
