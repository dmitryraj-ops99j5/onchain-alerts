import pytest
from onchain_alerts.matcher import topic_signature, Matcher, WatchRule


def test_topic_signature_erc20_transfer():
    expected = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    assert topic_signature("Transfer(address,address,uint256)") == expected


def test_topic_signature_approval():
    expected = "0x8c5be1e5eb7d556f1538a003991ffd051b943183943f7630e5a647b9b00e7c03"
    assert topic_signature("Approval(address,address,uint256)") == expected


def test_matcher_simple_log_filter():
    rule = WatchRule(
        name="usdt_transfers",
        address="0xdac17f958d2ee523a2206206994597c13d831ec7",
        event_signature="Transfer(address,address,uint256)",
    )
    matcher = Matcher([rule])

    sample_log = {
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": "0x0000000000000000000000000000000000000000000000000000000005f5e100",
        "transactionHash": "0x123",
        "logIndex": "0x0",
    }

    matched = matcher.match_log(sample_log)
    assert len(matched) == 1
    assert matched[0].name == "usdt_transfers"


def test_matcher_ignores_unmatched_address():
    rule = WatchRule(
        name="usdc_transfers",
        address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    )
    matcher = Matcher([rule])

    sample_log = {
        "address": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "topics": ["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"],
        "data": "0x0",
    }
    assert matcher.match_log(sample_log) == []


def test_matcher_indexed_topic_filtering():
    target_recipient = "0x0000000000000000000000009999999999999999999999999999999999999999"
    rule = WatchRule(
        name="whale_inflow",
        address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        event_signature="Transfer(address,address,uint256)",
        topic2=target_recipient,
    )
    matcher = Matcher([rule])

    mismatch_log = {
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "topics": [
            topic_signature("Transfer(address,address,uint256)"),
            "0x0000000000000000000000001111111111111111111111111111111111111111",
            "0x0000000000000000000000002222222222222222222222222222222222222222",
        ],
        "data": "0x0",
    }
    assert matcher.match_log(mismatch_log) == []

    matching_log = dict(mismatch_log)
    matching_log["topics"] = [
        topic_signature("Transfer(address,address,uint256)"),
        "0x0000000000000000000000001111111111111111111111111111111111111111",
        target_recipient,
    ]
    res = matcher.match_log(matching_log)
    assert len(res) == 1
    assert res[0].name == "whale_inflow"


def test_matcher_native_tx_value_threshold():
    rule = WatchRule(
        name="big_eth_move",
        match_tx=True,
        min_value_wei=10**19,  # 10 ETH
        to_address="0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    )
    matcher = Matcher([rule])

    tx_low = {
        "from": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "to": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "value": hex(5 * 10**18),
        "hash": "0xaaa",
    }
    assert matcher.match_tx(tx_low) == []

    tx_high = {
        "from": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "to": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "value": hex(15 * 10**18),
        "hash": "0xbbb",
    }
    matched = matcher.match_tx(tx_high)
    assert len(matched) == 1
    assert matched[0].name == "big_eth_move"
