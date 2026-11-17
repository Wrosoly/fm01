# Build context: the repository root (the bot depends on shared/schemas).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# The repository layout is mirrored under /fm01, so ../../shared/schemas (schemas, localizations) resolves.
COPY shared/schemas /fm01/shared/schemas
COPY shared/localization /fm01/shared/localization

WORKDIR /fm01/services/bot

COPY services/bot/pyproject.toml services/bot/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/bot/assets/fonts /usr/share/fonts/truetype/open-sans/

COPY services/bot .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--no-dev", "main.py"]
