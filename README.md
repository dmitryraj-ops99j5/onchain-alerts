# onchain-alerts

Small daemon that tails an EVM node via raw JSON-RPC (`eth_blockNumber`, `eth_getBlockByNumber`, `eth_getLogs`), scans every block against a local watchlist of wallet addresses and contract topics, and shoots JSON payloads to a webhook endpoint.

Cursor state is stored in SQLite so it can resume after restarts without skipping blocks or spamming duplicate alerts.

## Install

```bash
pip install -e .
```

## Quickstart

1. Copy the example config:
```bash
cp config.example.yaml config.yaml
```

2. Fill in your RPC endpoint and alert rules:
```yaml
rpc_url: "http://127.0.0.1:8545"
poll_interval: 2.0
confirmations: 1
db_path: "state.db"

webhook:
  url: "https://hooks.slack.com/services/..."
  headers:
    Authorization: "Bearer secret-token"

watchlist:
  addresses:
    - "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
  topics:
    - "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
```

3. Start the watcher:
```bash
onchain-alerts --config config.yaml
```

To backfill or replay older blocks, pass `--from-block`:

```bash
onchain-alerts --config config.yaml --from-block 19200000
```

If you want to reset the cursor stored in sqlite, drop the `state.db` file or use `--force-start`.

<!-- refreshed: 2026-09-12 -->
