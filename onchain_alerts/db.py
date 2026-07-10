import sqlite3
from pathlib import Path
from typing import Optional, Tuple
import time


class StateDB:
    """Local SQLite storage for syncing cursor position and deduplicating dispatches."""

    def __init__(self, db_path: str | Path = "alerts_state.db"):
        self.db_path = str(db_path)
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._get_conn() as conn:
            # WAL mode is critical here because watcher thread and notifier both touch this
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cursors (
                    chain_id INTEGER PRIMARY KEY,
                    last_block INTEGER NOT NULL,
                    last_hash TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_alerts (
                    alert_key TEXT PRIMARY KEY,
                    chain_id INTEGER NOT NULL,
                    tx_hash TEXT NOT NULL,
                    log_index INTEGER NOT NULL DEFAULT -1,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_created ON sent_alerts(created_at);"
            )

    def get_cursor(self, chain_id: int) -> Optional[Tuple[int, str]]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT last_block, last_hash FROM cursors WHERE chain_id = ?",
                (chain_id,),
            ).fetchone()
            if row:
                return row["last_block"], row["last_hash"]
            return None

    def set_cursor(self, chain_id: int, block_number: int, block_hash: str):
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO cursors (chain_id, last_block, last_hash, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chain_id) DO UPDATE SET
                    last_block = excluded.last_block,
                    last_hash = excluded.last_hash,
                    updated_at = excluded.updated_at
                """,
                (chain_id, block_number, block_hash.lower(), now),
            )

    def is_alert_sent(self, chain_id: int, tx_hash: str, log_index: Optional[int] = None) -> bool:
        idx = -1 if log_index is None else log_index
        key = f"{chain_id}:{tx_hash.lower()}:{idx}"
        # print(f"checking dedup key: {key}")
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM sent_alerts WHERE alert_key = ? LIMIT 1",
                (key,),
            ).fetchone()
            return row is not None

    def mark_alert_sent(self, chain_id: int, tx_hash: str, log_index: Optional[int] = None) -> bool:
        idx = -1 if log_index is None else log_index
        key = f"{chain_id}:{tx_hash.lower()}:{idx}"
        with self._get_conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO sent_alerts (alert_key, chain_id, tx_hash, log_index, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, chain_id, tx_hash.lower(), idx, time.time()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def prune_old_alerts(self, max_age_seconds: int = 86400 * 7) -> int:
        # FIXME: schedule this periodically in CLI loop instead of calling manually
        cutoff = time.time() - max_age_seconds
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM sent_alerts WHERE created_at < ?", (cutoff,))
            return cur.rowcount
