"""Fake CRM tool layer (Tier 3 #9).

Three SQLite-backed tools the ReAct agent can call:

  * `get_balance(msisdn)`         — credit + data balance for a phone
  * `list_open_tickets(account_id)` — open tickets for an account
  * `escalate_to_human(...)`      — file a new escalation ticket

The DB is seeded on first import (5 fake customers, 4 tickets) so the
demo is deterministic without any external service. A real deployment
would swap these tools for HTTP calls into the CRM/OSS.

This module is the *only* place that touches SQLite, so the rest of the
codebase stays stateless.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from langchain_core.tools import tool

from src.config import settings

logger = logging.getLogger(__name__)


# ----------------------------------------------------------- Schema ----

_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    msisdn      TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    plan        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS balances (
    msisdn          TEXT PRIMARY KEY,
    credit_egp      REAL NOT NULL,
    data_balance_gb REAL NOT NULL,
    last_recharge   TEXT NOT NULL,
    FOREIGN KEY(msisdn) REFERENCES customers(msisdn)
);
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL,
    status      TEXT NOT NULL CHECK(status IN ('open','closed','escalated')),
    priority    TEXT NOT NULL,
    summary     TEXT NOT NULL,
    opened_at   TEXT NOT NULL
);
"""

_SEED_CUSTOMERS = [
    ("01012345678", "1001", "Ahmed Hassan",      "Postpaid Gold 200"),
    ("01098765432", "1002", "Mona Said",         "Prepaid Flex"),
    ("01155667788", "1003", "Yara Mahmoud",      "FTTH Home 100"),
    ("01234567890", "1004", "Khaled Ibrahim",    "Postpaid Silver 80"),
    ("01512345678", "1005", "Salma Abdelrahman", "Prepaid Daily Saver"),
]
_SEED_BALANCES = [
    ("01012345678", 47.25,  18.4, "2026-05-02"),
    ("01098765432", 12.00,   2.1, "2026-05-05"),
    ("01155667788",  0.00,  85.0, "2026-04-28"),
    ("01234567890", 95.75,  45.0, "2026-05-01"),
    ("01512345678",  3.50,   0.0, "2026-05-08"),
]
_SEED_TICKETS = [
    ("TKT-2001", "1001", "open",       "P3", "Speed test fails on 2.4GHz",        "2026-05-06 09:14"),
    ("TKT-2002", "1003", "escalated",  "P2", "FTTH down for 2 days in Maadi",     "2026-05-05 22:07"),
    ("TKT-2003", "1002", "open",       "P4", "Refund query — late activation",    "2026-05-07 11:32"),
    ("TKT-2004", "1004", "closed",     "P3", "Roaming charges Europe",            "2026-04-30 18:55"),
]


def _seeded() -> bool:
    db = Path(settings.crm_db_path)
    if not db.exists():
        return False
    with sqlite3.connect(db) as conn:
        try:
            n = conn.execute("SELECT count(*) FROM customers").fetchone()[0]
            return n > 0
        except sqlite3.OperationalError:
            return False


def _ensure_db() -> None:
    db_path = Path(settings.crm_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        if not _seeded():
            conn.executemany(
                "INSERT OR IGNORE INTO customers VALUES (?,?,?,?)",
                _SEED_CUSTOMERS,
            )
            conn.executemany(
                "INSERT OR IGNORE INTO balances VALUES (?,?,?,?)",
                _SEED_BALANCES,
            )
            conn.executemany(
                "INSERT OR IGNORE INTO tickets VALUES (?,?,?,?,?,?)",
                _SEED_TICKETS,
            )
            conn.commit()
            logger.info("CRM DB seeded at %s", db_path)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    _ensure_db()
    c = sqlite3.connect(settings.crm_db_path)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


# ----------------------------------------------------------- Tools ----


def _normalize_msisdn(raw: str) -> str:
    """Strip +20 / 0020 prefixes so '01XX...' lookups always hit."""
    s = (raw or "").strip().replace(" ", "").replace("-", "")
    if s.startswith("+20"):
        s = "0" + s[3:]
    elif s.startswith("0020"):
        s = "0" + s[4:]
    return s


@tool
def get_balance(msisdn: str) -> dict:
    """Look up a NileTel customer's current credit and data balance.

    Args:
        msisdn: The Egyptian mobile number to look up, e.g. "01012345678".
                Variations like "+20 1012345678" are accepted.

    Returns:
        A dict with keys: msisdn, name, plan, credit_egp, data_balance_gb,
        last_recharge. Returns an `error` key when the number isn't found.
    """
    n = _normalize_msisdn(msisdn)
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT c.msisdn, c.name, c.plan, b.credit_egp, b.data_balance_gb,
                   b.last_recharge
            FROM customers c JOIN balances b USING(msisdn)
            WHERE c.msisdn = ?
            """,
            (n,),
        ).fetchone()
    if row is None:
        return {"error": f"No customer found for {msisdn}"}
    return dict(row)


@tool
def list_open_tickets(account_id: str) -> list[dict]:
    """List open or escalated tickets for a NileTel account.

    Args:
        account_id: The internal account number, e.g. "1001".

    Returns:
        A list of ticket dicts (ticket_id, status, priority, summary,
        opened_at). Empty list if the account has no open work.
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT ticket_id, status, priority, summary, opened_at
            FROM tickets
            WHERE account_id = ? AND status IN ('open', 'escalated')
            ORDER BY opened_at DESC
            """,
            (str(account_id),),
        ).fetchall()
    return [dict(r) for r in rows]


@tool
def escalate_to_human(
    account_id: str, reason: str, priority: str = "P3"
) -> dict:
    """File a new escalation ticket for a human agent.

    Args:
        account_id: The NileTel account number, e.g. "1001".
        reason: One sentence describing why escalation is needed.
        priority: P1 (critical) | P2 (high) | P3 (normal) | P4 (low).
                  Defaults to P3.

    Returns:
        The new ticket as a dict with ticket_id and confirmation details.
    """
    ticket_id = f"TKT-ESC-{int(time.time())}"
    opened_at = time.strftime("%Y-%m-%d %H:%M")
    with _conn() as conn:
        conn.execute(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?)",
            (
                ticket_id,
                str(account_id),
                "escalated",
                priority,
                reason[:200],
                opened_at,
            ),
        )
        conn.commit()
    return {
        "ticket_id": ticket_id,
        "status": "escalated",
        "priority": priority,
        "summary": reason[:200],
        "opened_at": opened_at,
    }


TOOLS = [get_balance, list_open_tickets, escalate_to_human]
