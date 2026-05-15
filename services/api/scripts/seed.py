#!/usr/bin/env python3
"""
Seed script — imports the sample Cherokee Crossroads scenario via the Admin
API and publishes it so learners can access it immediately.

Usage
-----
From the repo root (host machine, stack running):

    python services/api/scripts/seed.py

From inside the running api container:

    docker compose exec api python scripts/seed.py

Optional flags:

    --api-url   Base URL of the API  (default: http://localhost:8000)
    --admin-key Admin API key         (default: changeme)
    --file      Path to a custom scenario JSON file (default: bundled Cherokee fixture)

The script is idempotent: if the slug is already taken (HTTP 409) it prints
a notice and exits successfully.

Exit codes
----------
0  Success (imported or already present)
1  Unexpected error (bad API key, API unreachable, invalid JSON, …)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = pathlib.Path(__file__).parent
_DEFAULT_FIXTURE = _SCRIPTS_DIR / "cherokee_fixture.json"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _post(url: str, payload: dict, admin_key: str) -> tuple[int, dict | str]:
    """POST JSON to *url* and return (status_code, parsed_body)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Admin-Key": admin_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        try:
            body = json.loads(body_bytes)
        except Exception:
            body = body_bytes.decode(errors="replace")
        return exc.code, body


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a sample scenario into the Branching Scenarios API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the running API",
    )
    parser.add_argument(
        "--admin-key",
        default="changeme",
        help="Value of the X-Admin-Key header",
    )
    parser.add_argument(
        "--file",
        type=pathlib.Path,
        default=_DEFAULT_FIXTURE,
        help="Path to a scenario fixture JSON file",
    )
    args = parser.parse_args()

    # ── Load fixture ─────────────────────────────────────────────────────────
    fixture_path: pathlib.Path = args.file
    if not fixture_path.exists():
        print(f"✗  Fixture file not found: {fixture_path}", file=sys.stderr)
        sys.exit(1)

    with fixture_path.open() as fh:
        fixture = json.load(fh)

    slug = fixture["slug"]
    payload = {
        "slug": slug,
        "title": fixture["title"],
        "description": fixture.get("description", ""),
        "status": "published",
        "scenario_json": fixture["scenario_json"],
    }

    # ── Import scenario ───────────────────────────────────────────────────────
    import_url = f"{args.api_url}/api/v1/admin/scenarios/import"
    print(f"→  Seeding scenario '{slug}' …")

    status, body = _post(import_url, payload, args.admin_key)

    if status == 201:
        version = body.get("version_number", "?")
        web_url = args.api_url.replace(":8000", ":3000")
        print(f"✓  Imported as version {version}.")
        print(f"   Scenario page : {web_url}/{slug}")
        print(f"   API docs      : {args.api_url}/docs")
        return

    if status == 409:
        web_url = args.api_url.replace(":8000", ":3000")
        print(f"ℹ  Slug '{slug}' already exists — skipping import.")
        print(f"   Scenario page : {web_url}/{slug}")
        return

    # Any other status is an error
    detail = body.get("detail", body) if isinstance(body, dict) else body
    print(f"✗  Unexpected response HTTP {status}: {detail}", file=sys.stderr)

    if status == 403:
        print(
            "   Hint: check --admin-key matches ADMIN_API_KEY in the API.",
            file=sys.stderr,
        )
    elif status == 400:
        print(
            "   Hint: the scenario JSON failed validation — see 'errors' above.",
            file=sys.stderr,
        )

    sys.exit(1)


if __name__ == "__main__":
    main()
