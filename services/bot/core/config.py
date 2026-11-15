import logging
from dataclasses import dataclass
from typing import Self

import yaml

__all__ = ("Config",)

logger = logging.getLogger(__name__)


@dataclass
class Config:
	debug: bool
	owner_ids: list[int]
	modules: list[str]
	log_channel_id: int
	allowed_contexts: dict[str, bool]
	allowed_installs: dict[str, bool]
	allowed_mentions: dict[str, bool]
	emojis: dict[str, str]

	@classmethod
	def from_file(cls, file: str | None = None) -> Self:
		candidates = [file] if file else ["config.yaml", "config.yml"]
		for candidate in candidates:
			try:
				with open(candidate, "r", encoding="utf-8") as f:
					data = yaml.safe_load(f) or {}
					return cls(**_drop_moved_keys(data))
			except FileNotFoundError:
				continue
		logger.warning("No config.yml file found, defaults are applied")
		with open("config.yml.example", "r", encoding="utf-8") as f:
			data = yaml.safe_load(f) or {}
			return cls(**_drop_moved_keys(data))


# Keys that used to live in config.yml and are now read from the environment (.env), mapped to their variable.
MOVED_TO_ENV = {
	"twitch_client_id": "TWITCH_CLIENT_ID",
	"twitch_client_secret": "TWITCH_CLIENT_SECRET",
	"rsshub_url": "RSSHUB_URL",
}


def _drop_moved_keys(data: dict) -> dict:
	"""Removes keys that moved to environment variables, so old config files still load."""
	for key, env_var in MOVED_TO_ENV.items():
		if key in data:
			value = data.pop(key)
			if value is not None:
				logger.warning(f"config.yml `{key}` is ignored; set {env_var} in .env instead")
	return data
