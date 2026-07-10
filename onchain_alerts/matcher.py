from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from eth_hash.auto import keccak


def topic_hash(signature: str) -> str:
    """Compute 0x-prefixed keccak256 hash for an event signature."""
    clean = signature.replace(" ", "")
    digest = keccak(clean.encode("utf-8"))
    return "0x" + digest.hex()


def _normalize_addr(addr: str | None) -> str | None:
    if not addr:
        return None
    return addr.lower()


def _decode_uint256(hex_str: str) -> int:
    if not hex_str or hex_str == "0x":
        return 0
    return int(hex_str, 16)


# Quick helper for extracting indexed address topics (padded 32 bytes to 20 bytes hex)
def _topic_to_address(topic: str) -> str:
    clean = topic.lower().replace("0x", "").rjust(64, "0")
    return "0x" + clean[24:]


@dataclass
class MatchResult:
    rule_id: str
    rule_name: str
    tx_hash: str
    block_number: int
    matched_type: str  # 'log' | 'transaction'
    details: dict[str, Any]


class EventMatcher:
    def __init__(self, rules: list[dict[str, Any]]):
        self.rules = rules
        self._prepared_rules = []
        for r in rules:
            prep = dict(r)
            if "events" in r:
                prep["_topics"] = [topic_hash(sig) for sig in r["events"]]
            if "addresses" in r:
                prep["_addresses"] = {
                    _normalize_addr(a) for a in r["addresses"]
                }
            if "from" in r:
                prep["_from"] = {_normalize_addr(a) for a in r["from"]}
            if "to" in r:
                prep["_to"] = {_normalize_addr(a) for a in r["to"]}
            self._prepared_rules.append(prep)

    def match_log(self, log: dict[str, Any], block_number: int) -> list[MatchResult]:
        results = []
        log_addr = _normalize_addr(log.get("address"))
        topics = log.get("topics", [])
        tx_hash = log.get("transactionHash", "")

        if not topics:
            return results

        topic0 = topics[0].lower() if topics else None

        for rule in self._prepared_rules:
            rtype = rule.get("type", "log")
            if rtype not in ("event", "log"):
                continue

            # Target contract
            target_addrs = rule.get("_addresses")
            if target_addrs and log_addr not in target_addrs:
                continue

            # Target signature
            target_topics = rule.get("_topics")
            if target_topics and topic0 not in [t.lower() for t in target_topics]:
                continue

            # Optional topic[1] / topic[2] sender/receiver check (e.g. ERC20 Transfer)
            filter_sender = rule.get("filter_sender")
            if filter_sender and len(topics) > 1:
                indexed_sender = _topic_to_address(topics[1])
                if indexed_sender != filter_sender.lower():
                    continue

            filter_receiver = rule.get("filter_receiver")
            if filter_receiver and len(topics) > 2:
                indexed_rcv = _topic_to_address(topics[2])
                if indexed_rcv != filter_receiver.lower():
                    continue

            # Value check on unindexed data
            data = log.get("data", "0x")
            parsed_value = None
            if len(data) >= 66:  # at least 32 bytes hex payload
                parsed_value = _decode_uint256(data[:66])

            min_val = rule.get("min_value_raw")
            if min_val is not None:
                if parsed_value is None or parsed_value < int(min_val):
                    continue

            # print(f"[debug match] matched {rule.get('name')} for log {log.get('logIndex')}")

            results.append(
                MatchResult(
                    rule_id=rule.get("id", rule.get("name", "unknown")),
                    rule_name=rule.get("name", "unnamed"),
                    tx_hash=tx_hash,
                    block_number=block_number,
                    matched_type="log",
                    details={
                        "address": log_addr,
                        "topics": topics,
                        "data": data,
                        "value_raw": parsed_value,
                        "log_index": int(log.get("logIndex", "0x0"), 16),
                    },
                )
            )
        return results

    def match_transaction(self, tx: dict[str, Any], block_number: int) -> list[MatchResult]:
        results = []
        tx_from = _normalize_addr(tx.get("from"))
        tx_to = _normalize_addr(tx.get("to"))
        tx_hash = tx.get("hash", "")
        raw_value = int(tx.get("value", "0x0"), 16)

        for rule in self._prepared_rules:
            rtype = rule.get("type")
            if rtype not in ("tx", "transaction"):
                continue

            # from / to whitelist
            allowed_from = rule.get("_from")
            if allowed_from and tx_from not in allowed_from:
                continue

            allowed_to = rule.get("_to")
            if allowed_to and tx_to not in allowed_to:
                continue

            # ETH value filter
            min_eth = rule.get("min_eth_value")
            if min_eth is not None:
                wei_threshold = int(Decimal(str(min_eth)) * Decimal(10**18))
                if raw_value < wei_threshold:
                    continue

            results.append(
                MatchResult(
                    rule_id=rule.get("id", rule.get("name", "unknown")),
                    rule_name=rule.get("name", "unnamed"),
                    tx_hash=tx_hash,
                    block_number=block_number,
                    matched_type="transaction",
                    details={
                        "from": tx_from,
                        "to": tx_to,
                        "value_wei": raw_value,
                        "gas": int(tx.get("gas", "0x0"), 16),
                        "gas_price": int(tx.get("gasPrice", "0x0"), 16) if "gasPrice" in tx else None,
                    },
                )
            )
        return results
