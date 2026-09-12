"""Run ONLY by an authorized database operator; dry-run is the default.

No startup hook/HTTP route imports this command. Uses the operator runtime's MONGO_URL/DB_NAME.
See /app/PRODUCTION_ADMIN_RECOVERY.md. Never pass database credentials on the command line.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from shared.admin_recovery import recover  # noqa: E402


async def run(args):
    if not os.environ.get("MONGO_URL") or not os.environ.get("DB_NAME"):
        raise ValueError("The operator runtime must supply MONGO_URL and DB_NAME")
    if os.environ["DB_NAME"] != args.expected_db:
        raise ValueError("DB_NAME does not match --expected-db")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    try:
        database = client[os.environ["DB_NAME"]]
        await database.command("ping")
        return await recover(database, **vars(args))
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("phone", "user-id", "expected-db", "operation-id", "operator", "reason"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-report-sha256", default="")
    parser.add_argument("--backup-ref", default="")
    parser.add_argument("--maintenance-confirmed", action="store_true")
    try:
        print(json.dumps(asyncio.run(run(parser.parse_args())), indent=2))
    except HTTPException as exc:
        print(json.dumps({"status": "blocked", **exc.detail}), file=sys.stderr)
        return 1
    except Exception as exc:
        # Never print Mongo connection strings or raw provider/driver exception contents.
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__,
                          "detail": "Recovery stopped. Check private operator configuration/audit state."}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())