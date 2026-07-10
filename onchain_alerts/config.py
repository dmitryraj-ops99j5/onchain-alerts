import os
from dataclasses import dataclass, field
from typing import Any
import yaml


@dataclass
class WatchRule:
    name: str
    addresses: set[str] = field(default_factory=set)
    topics: list[str] = field(default_factory=list)
    include_txs: bool = True
    include_logs: bool = True
    min_value_wei: int = 0


@dataclass
class AppConfig:
    rpc_url: str
    fallback_rpcs: list[str] = field(default_factory=list)
    db_path: str = "cursor.db"
    poll_interval: float = 2.0
    start_block: int | None = None
    webhook_url: str | None = None
    webhook_headers: dict[str, str] = field(default_factory=dict)
    rules: list[WatchRule] = field(default_factory=list)
    confirmations: int = 0


def _clean_address(addr: str) -> str:
    val = addr.strip().lower()
    if not val.startswith("0x") or len(val) != 42:
        raise ValueError(f"Invalid ethereum address: {addr}")
    return val


def _clean_topic(top: str) -> str:
    val = top.strip().lower()
    if not val.startswith("0x"):
        val = "0x" + val
    # EVM log topics are 32 bytes (66 hex chars with 0x prefix)
    if len(val) == 66:
        return val
    # If someone passed an unpadded 20-byte address as topic
    raw_hex = val[2:]
    if len(raw_hex) < 64:
        return "0x" + raw_hex.rjust(64, "0")
    return val


def load_config(path: str) -> AppConfig:
    """Load and validate alert rules from a YAML file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    rpc_url = raw.get("rpc_url") or os.getenv("RPC_URL")
    if not rpc_url:
        raise ValueError("rpc_url is required in config or RPC_URL env var")

    fallbacks = raw.get("fallback_rpcs", [])
    if isinstance(fallbacks, str):
        fallbacks = [s.strip() for s in fallbacks.split(",") if s.strip()]

    rules: list[WatchRule] = []
    for item in raw.get("watchlist", []):
        name = item.get("name", "unnamed_rule")
        addrs = {_clean_address(a) for a in item.get("addresses", [])}
        raw_topics = item.get("topics", [])
        topics = [_clean_topic(t) for t in raw_topics if isinstance(t, str)]
        
        rules.append(
            WatchRule(
                name=name,
                addresses=addrs,
                topics=topics,
                include_txs=item.get("include_txs", True),
                include_logs=item.get("include_logs", True),
                min_value_wei=int(item.get("min_value_wei", 0)),
            )
        )

    return AppConfig(
        rpc_url=rpc_url,
        fallback_rpcs=fallbacks,
        db_path=raw.get("db_path", "cursor.db"),
        poll_interval=float(raw.get("poll_interval", 2.0)),
        start_block=raw.get("start_block"),
        webhook_url=raw.get("webhook_url") or os.getenv("ALERT_WEBHOOK_URL"),
        webhook_headers=raw.get("webhook_headers", {}),
        rules=rules,
        confirmations=max(0, int(raw.get("confirmations", 0))),
    )
