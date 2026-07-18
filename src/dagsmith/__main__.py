"""DagSmith CLI: ``python -m dagsmith db upgrade|downgrade|current``."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dagsmith")
    subparsers = parser.add_subparsers(dest="command", required=True)

    db = subparsers.add_parser("db", help="Manage DagSmith tables in the Airflow metadata DB")
    db.add_argument("action", choices=["upgrade", "downgrade", "current"])
    db.add_argument(
        "revision",
        nargs="?",
        default=None,
        help="Target revision (default: head for upgrade, -1 for downgrade)",
    )
    db.add_argument(
        "--sql-conn",
        default=None,
        help="Database URL override (default: Airflow's sql_alchemy_conn)",
    )

    args = parser.parse_args(argv)

    from dagsmith.core.migrate import run_migrations

    revision = args.revision or ("head" if args.action == "upgrade" else "-1")
    run_migrations(args.action, revision, url=args.sql_conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
