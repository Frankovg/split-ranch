"""Write the API's OpenAPI document to packages/api-client/openapi.json.

Run from apps/api: `uv run python scripts/export_openapi.py` (or `pnpm api:openapi` from the
repo root, which also regenerates the TypeScript types). Needs no database or network: the
engine connects lazily and the schema is built from the routes only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from split_ranch.core.settings import Settings
from split_ranch.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPO_ROOT / "packages" / "api-client" / "openapi.json"


def build_schema() -> dict[str, object]:
    # Ignore any local .env: the schema must not depend on secrets or on the environment.
    settings = Settings(_env_file=None, sentry_dsn=None, log_json=False, log_level="WARNING")
    return create_app(settings).openapi()


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"
    output.write_text(text, encoding="utf-8", newline="\n")
    print(f"OpenAPI schema written to {output}")


if __name__ == "__main__":
    main()
