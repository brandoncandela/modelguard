"""Command line entry points.

    python -m app.cli seed            rebuild the database with synthetic data
    python -m app.cli migrate         apply migrations only
    python -m app.cli counts          print row counts per table
    python -m app.cli wait-db         wait for the database (used by the container entrypoint)
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_engine


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="modelguard")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed_p = sub.add_parser("seed", help="drop and rebuild the database with synthetic data")
    seed_p.add_argument("--if-empty", action="store_true", help="only seed when the database has no users yet")
    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("counts", help="row counts per table")
    sub.add_parser("wait-db", help="wait up to 60 seconds for the database to accept connections")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    engine = get_engine()

    if args.cmd == "wait-db":
        from sqlalchemy import text

        for _attempt in range(60):
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                print("Database is ready.")
                return 0
            except Exception:  # noqa: BLE001
                time.sleep(1)
        print("Database did not become ready in 60 seconds.", file=sys.stderr)
        return 1
    if args.cmd == "seed" and args.if_empty:
        from sqlalchemy import inspect, text

        if "users" in inspect(engine).get_table_names():
            with engine.connect() as conn:
                if conn.execute(text("SELECT COUNT(*) FROM users")).scalar():
                    from app.seed.run import upgrade_schema

                    upgrade_schema(engine)
                    print("Database already seeded; migrations applied.")
                    return 0
    if args.cmd == "seed":
        from app.seed.run import seed_database

        t0 = time.time()
        result = seed_database(engine, settings, progress=lambda s: print(f"  {s}", flush=True))
        print(f"Seed complete in {time.time() - t0:.1f}s. Data anchor {result['anchor']}, "
              f"periods {result['periods'][0]} to {result['periods'][-1]}.")
        if result["generated_password"]:
            print("MODELGUARD_DEMO_PASSWORD was not set, so a random password was generated for every demo user:")
            print(f"  {result['generated_password']}")
            print("Set MODELGUARD_DEMO_PASSWORD in .env to choose your own.")
        return 0
    if args.cmd == "migrate":
        from app.seed.run import upgrade_schema

        upgrade_schema(engine)
        print("Migrations applied.")
        return 0
    if args.cmd == "counts":
        from app.seed.run import table_counts

        print(json.dumps(table_counts(engine), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
