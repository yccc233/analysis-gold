import sqlite3
from datetime import datetime, timezone

from gold.config import DEFAULT_DB_PATH


def init_db(path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gold_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc INTEGER NOT NULL,
            ts_local TEXT NOT NULL,
            price_cny_g REAL NOT NULL,
            price_usd_oz REAL NOT NULL,
            usd_cny REAL NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gold_prices_ts_utc ON gold_prices(ts_utc);")
    conn.commit()
    return conn


def insert_price(
    conn: sqlite3.Connection,
    ts_utc: int,
    ts_local: str,
    price_cny_g: float,
    price_usd_oz: float,
    usd_cny: float,
) -> None:
    conn.execute(
        """
        INSERT INTO gold_prices (ts_utc, ts_local, price_cny_g, price_usd_oz, usd_cny)
        VALUES (?, ?, ?, ?, ?);
        """,
        (ts_utc, ts_local, price_cny_g, price_usd_oz, usd_cny),
    )
    conn.commit()


def get_latest_price(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        """
        SELECT ts_utc, ts_local, price_cny_g, price_usd_oz, usd_cny
        FROM gold_prices ORDER BY ts_utc DESC LIMIT 1;
        """
    ).fetchone()
    if not row:
        return None
    return {
        "ts_utc": int(row[0]),
        "ts_local": row[1],
        "price_cny_g": float(row[2]),
        "price_usd_oz": float(row[3]),
        "usd_cny": float(row[4]),
    }


def get_history(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    cutoff = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    rows = conn.execute(
        """
        SELECT ts_utc, ts_local, price_cny_g, price_usd_oz, usd_cny
        FROM gold_prices
        WHERE ts_utc >= ?
        ORDER BY ts_utc ASC;
        """,
        (cutoff,),
    ).fetchall()
    return [
        {
            "ts_utc": int(r[0]),
            "ts_local": r[1],
            "price_cny_g": float(r[2]),
            "price_usd_oz": float(r[3]),
            "usd_cny": float(r[4]),
        }
        for r in rows
    ]
