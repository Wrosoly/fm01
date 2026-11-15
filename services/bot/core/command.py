import logging
from dataclasses import dataclass

from discord.ext import commands

from core import slash_localization
from core.locale import resolve_locale

logger = logging.getLogger(__name__)

__all__ = ("Command", "format_aliases")


def format_aliases(command: commands.Command) -> str | None:
	"""Join ``command``'s aliases and full aliases (top-level names for a subcommand) for display.

	Args:
		command: The command to describe.

	Returns:
		A comma-separated list, or None when the command has no aliases of either kind.
	"""
	aliases = list(dict.fromkeys([*command.aliases, *getattr(command, "all_full_aliases", [])]))
	return ", ".join(aliases) if aliases else None


@dataclass
class Command:
	name: str
	description: str
	usage: str
	prefix: str
	aliases: str | None

	@classmethod
	def from_ctx(cls, ctx: commands.Context):
		"""Describe the command being invoked in ``ctx``, localized for it."""
		return cls.from_command(ctx.command, ctx) if ctx.command else None

	@classmethod
	def from_command(cls, command: commands.Command, ctx: commands.Context):
		"""Describe ``command`` (name, localized description and usage) in the locale that applies to ``ctx``."""
		l10n = slash_localization.slash_command_localization
		if not l10n:
			return None
		locale = resolve_locale(ctx, getattr(getattr(ctx, "bot", None), "locale_cache", None))
		usage_attr = getattr(command, "usage", None) if command.clean_params else None
		desc_attr = getattr(command, "description", None)
		usage = slash_localization.lookup(usage_attr, locale) if usage_attr else None
		description = l10n(desc_attr, locale) if desc_attr else None
		usage_text = (
			f"{ctx.clean_prefix}{usage}"
			if usage and usage != usage_attr
			else f"{ctx.clean_prefix}{command.qualified_name}"
		)
		return cls(
			name=command.qualified_name,
			description=description if isinstance(description, str) and description else "-",
			usage=usage_text,
			prefix=ctx.clean_prefix,
			aliases=format_aliases(command),
		)
