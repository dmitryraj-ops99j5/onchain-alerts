import time
import logging
import httpx
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RpcError(Exception):
    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class RpcClient:
    """Barebones JSON-RPC client with retry on 429 and server errors."""

    def __init__(self, rpc_url: str, timeout: float = 12.0, max_retries: int = 4):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._req_id = 0
        self._client = httpx.Client(timeout=timeout)

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def call(self, method: str, params: Optional[list] = None) -> Any:
        if params is None:
            params = []

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        delay = 0.5
        for attempt in range(1, self.max_retries + 1):
            try:
                res = self._client.post(self.rpc_url, json=payload)
                if res.status_code == 429:
                    logger.warning("rpc rate limit (429), backoff %.1fs [attempt %d/%d]", delay, attempt, self.max_retries)
                    time.sleep(delay)
                    delay *= 2
                    continue

                res.raise_for_status()
                data = res.json()

                if "error" in data:
                    err = data["error"]
                    code = err.get("code")
                    msg = err.get("message", "Unknown RPC error")
                    # Infura / Alchemy rate limits often return 200 with code -32005
                    if code == -32005 or "rate limit" in msg.lower():
                        logger.warning("node rate limit error (%s), backoff %.1fs", msg, delay)
                        time.sleep(delay)
                        delay *= 2
                        continue
                    raise RpcError(msg, code, err.get("data"))

                return data.get("result")
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt == self.max_retries:
                    raise
                logger.warning("rpc transport error (%s), retrying in %.1fs", exc, delay)
                time.sleep(delay)
                delay *= 2

        raise RpcError("Max retries exceeded")

    def get_block_number(self) -> int:
        hex_val = self.call("eth_blockNumber")
        return int(hex_val, 16)

    def get_block(self, block_num: int, full_txs: bool = True) -> Optional[dict]:
        hex_num = hex(block_num)
        return self.call("eth_getBlockByNumber", [hex_num, full_txs])

    def get_logs(self, from_block: int, to_block: int, addresses: Optional[list[str]] = None, topics: Optional[list] = None) -> list[dict]:
        filter_params: dict[str, Any] = {
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }
        if addresses:
            filter_params["address"] = addresses if len(addresses) > 1 else addresses[0]
        if topics:
            filter_params["topics"] = topics

        try:
            logs = self.call("eth_getLogs", [filter_params])
            return logs or []
        except RpcError as err:
            # Some providers reject ranges returning > 10k logs or > 2k blocks
            msg = str(err).lower()
            if ("query returned more than" in msg or "log response size exceeded" in msg or "response too large" in msg) and from_block < to_block:
                mid = (from_block + to_block) // 2
                logger.info("log query too large, splitting [%d..%d] into [%d..%d] and [%d..%d]", from_block, to_block, from_block, mid, mid + 1, to_block)
                left = self.get_logs(from_block, mid, addresses, topics)
                right = self.get_logs(mid + 1, to_block, addresses, topics)
                return left + right
            raise

    def close(self):
        self._client.close()
