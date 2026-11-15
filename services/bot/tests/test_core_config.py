from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from core.config import Config

EXAMPLE = Path(__file__).resolve().parent.parent / "config.yml.example"


def test_config_ignores_keys_moved_to_env(tmp_path: Path, caplog: pytest.LogCaptureFixture):
	data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
	data |= {"twitch_client_id": "abc", "twitch_client_secret": None, "rsshub_url": "http://x"}
	path = tmp_path / "config.yml"
	path.write_text(yaml.safe_dump(data), encoding="utf-8")

	with caplog.at_level(logging.WARNING, logger="core.config"):
		config = Config.from_file(str(path))

	assert not hasattr(config, "twitch_client_id")
	assert "TWITCH_CLIENT_ID" in caplog.text
	assert "RSSHUB_URL" in caplog.text
	assert "TWITCH_CLIENT_SECRET" not in caplog.text  # unset values are dropped silently
