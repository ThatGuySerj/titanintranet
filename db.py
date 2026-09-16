"""One connection to the shared Titan database.

The ticket site's db.py owns the ticket schema and is a thousand lines. This
site needs three tables and creates them itself, so all that is wanted here is
a connection - and keeping it small is the point of the site being separate.
"""
import os

import psycopg
from psycopg.rows import dict_row


def connect():
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. The intranet shares the ticket site's "
            "Postgres; copy the setting across from that app.")
    return psycopg.connect(url, row_factory=dict_row, autocommit=False)
