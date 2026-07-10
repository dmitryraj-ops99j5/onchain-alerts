import pytest
import time
from onchain_alerts.db import Database


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_state.db"
    database = Database(str(db_path))
    database.init_schema()
    return database


def test_cursor_initial_and_update(db):
    assert db.get_cursor(chain_id=1) is None

    db.set_cursor(chain_id=1, block_number=19000000)
    assert db.get_cursor(chain_id=1) == 19000000

    db.set_cursor(chain_id=1, block_number=19000005)
    assert db.get_cursor(chain_id=1) == 19000005

    # distinct chains stay independent
    assert db.get_cursor(chain_id=137) is None
    db.set_cursor(chain_id=137, block_number=5000)
    assert db.get_cursor(chain_id=137) == 5000
    assert db.get_cursor(chain_id=1) == 19000005


def test_cursor_rewind_on_reorg(db):
    db.set_cursor(chain_id=1, block_number=100)
    # simulate reorg rollback
    db.set_cursor(chain_id=1, block_number=97)
    assert db.get_cursor(chain_id=1) == 97


def test_seen_tx_deduplication(db):
    tx_hash = "0xabc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abc"
    
    assert not db.is_tx_seen(tx_hash)
    db.mark_tx_seen(tx_hash, block_number=100)
    assert db.is_tx_seen(tx_hash)

    # marking again shouldn't fail (insert or ignore)
    db.mark_tx_seen(tx_hash, block_number=100)
    assert db.is_tx_seen(tx_hash)


def test_prune_old_seen_txs(db):
    for i in range(10):
        db.mark_tx_seen(f"0x{i:064x}", block_number=100 + i)

    # keep only txs within 5 blocks of height 110 (i.e. >= 105)
    # print("debugging prune cutoff:", 110 - 5)
    deleted = db.prune_seen_txs(before_block=105)
    assert deleted == 5

    assert not db.is_tx_seen(f"0x{0:064x}")
    assert not db.is_tx_seen(f"0x{4:064x}")
    assert db.is_tx_seen(f"0x{5:064x}")
    assert db.is_tx_seen(f"0x{9:064x}")
