from __future__ import annotations

from pathlib import Path

import pytest
from meshplay_client.subscriptions import list_subscriptions, subscribe, unsubscribe

_FAKE_PUBKEY_A = "a" * 64
_FAKE_PUBKEY_B = "b" * 64
_FAKE_PUBKEY_C = "c" * 64


@pytest.fixture(autouse=True)
def isolated_subs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect subscriptions I/O to a temp directory for each test."""
    import meshplay_client.subscriptions as subs

    monkeypatch.setattr(subs, "_subs_path", lambda: tmp_path / "subscriptions.json")


class TestListSubscriptions:
    def test_empty_initially(self) -> None:
        assert list_subscriptions() == []

    def test_returns_all_after_subscribe(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        subscribe(_FAKE_PUBKEY_B)
        result = list_subscriptions()
        assert _FAKE_PUBKEY_A in result
        assert _FAKE_PUBKEY_B in result
        assert len(result) == 2


class TestSubscribe:
    def test_subscribe_adds_entry(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        assert _FAKE_PUBKEY_A in list_subscriptions()

    def test_subscribe_is_idempotent(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        subscribe(_FAKE_PUBKEY_A)
        result = list_subscriptions()
        assert result.count(_FAKE_PUBKEY_A) == 1

    def test_subscribe_multiple(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        subscribe(_FAKE_PUBKEY_B)
        subscribe(_FAKE_PUBKEY_C)
        assert len(list_subscriptions()) == 3

    def test_persisted_across_calls(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        # fresh call to list_subscriptions re-reads from disk
        assert _FAKE_PUBKEY_A in list_subscriptions()


class TestUnsubscribe:
    def test_unsubscribe_removes_entry(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        subscribe(_FAKE_PUBKEY_B)
        unsubscribe(_FAKE_PUBKEY_A)
        result = list_subscriptions()
        assert _FAKE_PUBKEY_A not in result
        assert _FAKE_PUBKEY_B in result

    def test_unsubscribe_noop_if_absent(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        unsubscribe(_FAKE_PUBKEY_B)  # never subscribed
        assert list_subscriptions() == [_FAKE_PUBKEY_A]

    def test_unsubscribe_from_empty_is_noop(self) -> None:
        unsubscribe(_FAKE_PUBKEY_A)
        assert list_subscriptions() == []


class TestRoundTrip:
    def test_subscribe_then_unsubscribe_leaves_empty(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        unsubscribe(_FAKE_PUBKEY_A)
        assert list_subscriptions() == []

    def test_order_preserved(self) -> None:
        subscribe(_FAKE_PUBKEY_A)
        subscribe(_FAKE_PUBKEY_B)
        subscribe(_FAKE_PUBKEY_C)
        assert list_subscriptions() == [_FAKE_PUBKEY_A, _FAKE_PUBKEY_B, _FAKE_PUBKEY_C]
