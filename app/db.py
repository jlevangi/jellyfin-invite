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

REDEMPTIONS_SCHEMA = """create table if not exists invite_redemptions(
    id integer primary key,
    invite_code text not null,
    redeemed_at text not null,
    email text not null,
    subject text,
    foreign key(invite_code) references invite_codes(code))"""

RESERVATIONS_SCHEMA = """create table if not exists invite_reservations(
    id text primary key,
    invite_code text not null,
    created_at text not null,
    foreign key(invite_code) references invite_codes(code))"""

MIGRATIONS = (
    "alter table invite_codes add column used_by_subject text",
    "alter table invite_codes add column max_uses integer not null default 1",
)


def now():
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys=on")
    con.execute(SCHEMA)
    for sql in MIGRATIONS:
        try:
            con.execute(sql)
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error):
                raise
    con.execute(REDEMPTIONS_SCHEMA)
    con.execute(RESERVATIONS_SCHEMA)
    con.execute(
        """insert into invite_redemptions(invite_code,redeemed_at,email,subject)
           select code,used_at,used_by_email,used_by_subject from invite_codes
           where used_at is not null and used_by_email is not null
             and not exists(select 1 from invite_redemptions where invite_code=invite_codes.code)"""
    )
    con.commit()
    return con


def rows(cur):
    return [dict(r) for r in cur.fetchall()]
