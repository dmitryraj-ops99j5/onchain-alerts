from __future__ import annotations

import html
import logging
import time
from typing import Any
import httpx
from onchain_alerts.matcher import MatchResult

logger = logging.getLogger(__name__)


def _format_tg_message(match: MatchResult, chain_id: int | None = None) -> str:
    lines = [
        f"<b>🔔 Alert: {html.escape(match.rule_name)}</b>",
        f"<b>Block:</b> <code>{match.block_number}</code>",
        f"<b>Tx:</b> <code>{match.tx_hash}</code>",
    ]

    if match.matched_type == "transaction":
        f_addr = match.details.get("from", "n/a")
        t_addr = match.details.get("to", "n/a")
        val_wei = match.details.get("value_wei", 0)
        val_eth = val_wei / (10**18)
        lines.append(f"<b>From:</b> <code>{f_addr}</code>")
        lines.append(f"<b>To:</b> <code>{t_addr}</code>")
        if val_eth > 0:
            lines.append(f"<b>Value:</b> {val_eth:.4f} ETH")
    else:
        contract = match.details.get("address", "n/a")
        lines.append(f"<b>Contract:</b> <code>{contract}</code>")
        if "value_raw" in match.details and match.details["value_raw"] is not None:
            lines.append(f"<b>Raw Val:</b> <code>{match.details['value_raw']}</code>")

    return "\n".join(lines)


class Notifier:
    def __init__(
        self,
        webhook_urls: list[str] | None = None,
        telegram_bot_token: str | None = None,
        telegram_chat_id: str | None = None,
        chain_id: int | None = None,
    ):
        self.webhook_urls = webhook_urls or []
        self.tg_token = telegram_bot_token
        self.tg_chat_id = telegram_chat_id
        self.chain_id = chain_id
        self.client = httpx.Client(timeout=10.0)

    def close(self):
        self.client.close()

    def _post_with_retry(self, url: str, **kwargs: Any) -> bool:
        # quick two-attempt retry for flakey endpoints or tg rate limits
        for attempt in range(2):
            try:
                res = self.client.post(url, **kwargs)
                if res.status_code == 429:
                    retry_after = int(res.headers.get("Retry-After", 2))
                    time.sleep(retry_after)
                    continue
                res.raise_for_status()
                return True
            except httpx.HTTPError as err:
                if attempt == 1:
                    logger.warning("failed delivering alert to %s: %s", url, err)
                time.sleep(0.5)
        return False

    def send(self, match: MatchResult) -> None:
        payload = {
            "rule": match.rule_name,
            "rule_id": match.rule_id,
            "block_number": match.block_number,
            "tx_hash": match.tx_hash,
            "type": match.matched_type,
            "details": match.details,
        }

        # 1. Custom HTTP Webhooks
        for url in self.webhook_urls:
            self._post_with_retry(url, json=payload)

        # 2. Telegram Bot API
        if self.tg_token and self.tg_chat_id:
            tg_url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            text = _format_tg_message(match, self.chain_id)
            tg_data = {
                "chat_id": self.tg_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            self._post_with_retry(tg_url, json=tg_data)
