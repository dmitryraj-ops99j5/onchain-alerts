import time
import signal
import logging
from typing import Optional
from onchain_alerts.config import WatcherConfig
from onchain_alerts.rpc import RpcClient
from onchain_alerts.matcher import Matcher
from onchain_alerts.notifier import Notifier
from onchain_alerts.db import Database

logger = logging.getLogger(__name__)


class BlockWatcher:
    def __init__(self, config: WatcherConfig, db: Database, rpc: RpcClient, matcher: Matcher, notifier: Notifier):
        self.config = config
        self.db = db
        self.rpc = rpc
        self.matcher = matcher
        self.notifier = notifier
        self.running = False
        self._last_parent_hash: Optional[str] = None

    def _init_signals(self):
        def _handler(signum, _frame):
            sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            logger.info("received %s, shutting down watcher cleanly...", sig_name)
            self.running = False

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def _get_start_block(self, latest: int) -> int:
        saved = self.db.get_cursor()
        if saved is not None:
            return saved + 1
        if self.config.start_block is not None:
            logger.info("starting from configured block %d", self.config.start_block)
            return self.config.start_block
        
        start = max(0, latest - self.config.confirmations)
        logger.info("no cursor found, starting at head - %d: block %d", self.config.confirmations, start)
        return start

    def process_block(self, block_number: int):
        # Fetch block with full tx objects
        block = self.rpc.get_block(block_number, full_txs=True)
        if not block:
            logger.warning("block %d returned null (reorg or not propagated yet)", block_number)
            return False

        block_hash = block.get("hash")
        parent_hash = block.get("parentHash")

        # Simple shallow reorg check against in-memory previous hash
        if self._last_parent_hash and parent_hash != self._last_parent_hash:
            logger.warning(
                "possible shallow reorg at block %d: expected parent %s, got %s",
                block_number, self._last_parent_hash, parent_hash
            )
            # FIXME: implement rollback of cursor when reorg depth > confirmations

        txs = block.get("transactions", [])
        tx_matches = self.matcher.match_transactions(txs, block_number)
        for match in tx_matches:
            self.notifier.send_tx_alert(match)

        # Fetch logs in block range if address or topic filters are present
        if self.matcher.has_log_filters():
            logs = self.rpc.get_logs(block_number, block_number)
            # print(f"debug: {len(logs)} logs in block {block_number}")
            log_matches = self.matcher.match_logs(logs)
            for match in log_matches:
                self.notifier.send_log_alert(match)

        self._last_parent_hash = block_hash
        self.db.set_cursor(block_number)
        return True

    def run(self):
        self._init_signals()
        self.running = True
        logger.info("starting watcher on %s", self.rpc.rpc_url)
        
        # Resolve starting point once on boot
        latest = self.rpc.get_block_number()
        current = self._get_start_block(latest)

        while self.running:
            try:
                latest = self.rpc.get_block_number()
                safe_head = latest - self.config.confirmations

                if current > safe_head:
                    # Caught up, wait for next block
                    time.sleep(self.config.poll_interval)
                    continue

                while self.running and current <= safe_head:
                    success = self.process_block(current)
                    if not success:
                        # retry same block on next loop
                        break
                    current += 1

            except Exception as e:
                logger.error("error in watcher loop: %s", e, exc_info=True)
                time.sleep(self.config.poll_interval)

        logger.info("watcher stopped. last processed block: %d", current - 1)

    def stop(self):
        self.running = False
