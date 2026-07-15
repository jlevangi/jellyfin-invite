import datetime as dt
import sqlite3

SCHEMA = """create table if not exists invite_codes(
    code text primary key,
    note text,
    created_at text not null,
    expires_at text not null,
    used_at text,
    used_by_email text,
    revoked_at text)"""

MIGRATIONS = (
    "alter table invite_codes add column used_by_subject text",
)


def now():
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute(SCHEMA)
    for sql in MIGRATIONS:
        try:
            con.execute(sql)
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error):
                raise
    return con


def rows(cur):
    return [dict(r) for r in cur.fetchall()]
