import argparse
import sys
import time
from onchain_alerts.config import load_config
from onchain_alerts.db import CursorStore
from onchain_alerts.watcher import tail_chain, backfill_range


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onchain-alerts",
        description="Tail EVM chain, match watchlist rules, and deliver alerts.",
    )
    parser.add_argument(
        "-c", "--config", default="config.yaml", help="Path to YAML configuration"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Start tailing the blockchain")
    p_run.add_argument("--from-block", type=int, help="Override starting block")
    p_run.add_argument("--dry-run", action="store_true", help="Log matches to stdout without webhooks")

    # backfill
    p_back = sub.add_parser("backfill", help="Process historical block range")
    p_back.add_argument("--from", dest="from_block", type=int, required=True, help="Start block")
    p_back.add_argument("--to", dest="to_block", type=int, required=True, help="End block (inclusive)")
    p_back.add_argument("--batch-size", type=int, default=10, help="Concurrent block batch size")
    p_back.add_argument("--no-cursor", action="store_true", help="Don't update SQLite cursor during backfill")

    # status
    p_stat = sub.add_parser("status", help="Print current stored cursor and matching stats")
    p_stat.add_argument("--reset", action="store_true", help="Reset cursor in database to 0")

    return parser


def run_status(cfg_path: str, reset: bool = False) -> int:
    cfg = load_config(cfg_path)
    store = CursorStore(cfg.db_path)
    
    if reset:
        store.reset_cursor()
        print(f"Reset cursor in {cfg.db_path}")
        return 0

    last = store.get_last_processed_block()
    stats = store.get_alert_counts()
    
    print(f"Database: {cfg.db_path}")
    if last is None:
        print("Last processed block: none (fresh db)")
    else:
        print(f"Last processed block: {last}")
    
    print(f"Total sent alerts: {stats.get('sent', 0)}")
    print(f"Failed deliveries: {stats.get('failed', 0)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # print(f"DEBUG: raw args={sys.argv}")
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        
        if args.command == "status":
            return run_status(args.config, reset=args.reset)
        
        elif args.command == "backfill":
            if args.from_block > args.to_block:
                print("--from cannot be larger than --to", file=sys.stderr)
                return 2
            
            # FIXME: backfill doesn't detect chain reorgs if start block is near the tip
            t0 = time.time()
            count = backfill_range(
                cfg=cfg,
                from_block=args.from_block,
                to_block=args.to_block,
                batch_size=args.batch_size,
                update_cursor=not args.no_cursor,
            )
            elapsed = time.time() - t0
            print(f"Backfill finished: {count} blocks in {elapsed:.1f}s")
            return 0

        elif args.command == "run":
            if args.from_block is not None:
                cfg.start_block = args.from_block
            tail_chain(cfg, dry_run=args.dry_run)
            return 0

    except KeyboardInterrupt:
        print("\nInterrupted by user, shutting down.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
