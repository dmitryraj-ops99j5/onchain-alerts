import pytest
from onchain_alerts.rpc import (
    hex_to_int,
    int_to_hex,
    build_batch_request,
    parse_block,
    parse_batch_response,
    chunk_requests,
    RpcError,
)


def test_hex_conversion_helpers():
    assert hex_to_int("0x0") == 0
    assert hex_to_int("0x10") == 16
    assert hex_to_int("0x0100") == 256
    assert hex_to_int(None) is None
    assert int_to_hex(0) == "0x0"
    assert int_to_hex(4096) == "0x1000"


def test_build_batch_request_structure():
    calls = [
        ("eth_getBlockByNumber", ["0x10", True]),
        ("eth_getBlockByNumber", ["0x11", True]),
    ]
    payload = build_batch_request(calls)
    
    assert len(payload) == 2
    assert payload[0]["method"] == "eth_getBlockByNumber"
    assert payload[0]["params"] == ["0x10", True]
    assert payload[0]["id"] == 0
    assert payload[1]["id"] == 1
    assert all(req["jsonrpc"] == "2.0" for req in payload)


def test_chunk_requests():
    items = list(range(10))
    chunks = list(chunk_requests(items, chunk_size=3))
    assert chunks == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

    assert list(chunk_requests([], chunk_size=5)) == []


def test_parse_batch_response_reorders_by_id():
    # nodes sometimes return batch items out of order
    raw_batch = [
        {"id": 1, "result": {"number": "0x2", "hash": "0x222", "transactions": []}},
        {"id": 0, "result": {"number": "0x1", "hash": "0x111", "transactions": []}},
    ]
    results = parse_batch_response(raw_batch, expected_count=2)
    assert len(results) == 2
    assert results[0]["hash"] == "0x111"
    assert results[1]["hash"] == "0x222"


def test_parse_batch_response_raises_on_rpc_error():
    raw_batch = [
        {"id": 0, "error": {"code": -32000, "message": "execution timeout"}},
    ]
    with pytest.raises(RpcError) as exc:
        parse_batch_response(raw_batch, expected_count=1)
    assert "execution timeout" in str(exc.value)


def test_parse_block_with_transactions():
    raw = {
        "number": "0x10d",
        "hash": "0xabc123",
        "parentHash": "0xabc122",
        "timestamp": "0x651000",
        "transactions": [
            {
                "hash": "0x999",
                "from": "0xaaa0000000000000000000000000000000000001",
                "to": "0xbbb0000000000000000000000000000000000002",
                "value": "0xde0b6b3a7640000",
                "input": "0x",
                "transactionIndex": "0x0",
            }
        ]
    }
    block = parse_block(raw)
    assert block.number == 269
    assert block.hash == "0xabc123"
    assert block.timestamp == 6623232
    assert len(block.transactions) == 1
    
    tx = block.transactions[0]
    assert tx.hash == "0x999"
    assert tx.from_address == "0xaaa000000000000000000000000000000000001"
    assert tx.to_address == "0xbbb0000000000000000000000000000000000002"
    assert tx.value == 1000000000000000000


def test_parse_block_empty_or_null():
    assert parse_block(None) is None
