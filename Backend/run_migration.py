"""Run a .sql migration file against the configured MySQL server.

Usage:
    python -m Backend.run_migration Database/migrations/<file>.sql

Statements are executed one at a time. Errors that only mean "already applied"
(repeated CREATE INDEX / duplicate column) are reported and skipped, so the same
migration can be run twice without failing.
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

import mysql.connector  # noqa: E402  (must be imported after .env is loaded)

IDEMPOTENT_CODES = {"ER_DUP_KEYNAME", "ER_DUP_FIELDNAME"}


def _strip_bom(text):
    return text.lstrip("﻿")


def split_statements(sql):
    sql = re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE)
    return [chunk.strip() for chunk in sql.split(";") if chunk.strip()]


def run(path):
    sql = _strip_bom(Path(path).read_text(encoding="utf-8"))
    connection = mysql.connector.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    cursor = connection.cursor()
    applied = 0
    for statement in split_statements(sql):
        try:
            cursor.execute(statement)
            applied += 1
        except mysql.connector.Error as error:
            if error.errno in (1061, 1060):  # duplicate key / column
                print(f"SKIP (already applied): {statement.splitlines()[0][:70]}")
                continue
            print(f"FAILED: {statement.splitlines()[0][:70]}\n  {error}", file=sys.stderr)
            connection.close()
            return 1
    connection.commit()
    connection.close()
    print(f"Applied {applied} statement(s) from {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1]))
