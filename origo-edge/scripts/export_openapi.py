"""Emit the OpenAPI document without starting a server or touching the database.
"""

from __future__ import annotations

import sys

import orjson

from origo_edge.main import create_app
from origo_edge.settings import Settings


def main() -> int:
    # Minimal settings: create_app must not require live infrastructure, which is what
    # makes `make contracts` cheap enough to run on every push.
    settings = Settings(
        database_url="postgresql://unused:unused@localhost/unused",  # noqa: S106
        env="local", auth_disabled=True,
    )
    schema = create_app(settings).openapi()
    sys.stdout.write(orjson.dumps(schema, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode())
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())