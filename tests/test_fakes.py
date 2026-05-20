"""Unit tests for the data types in :mod:`viur.light_mock.fakes`."""
from __future__ import annotations

import pytest

from viur.light_mock.fakes import (
    DbState,
    FakeEntity,
    FakeKey,
    FakeQuery,
    FakeSortOrder,
)


# --------------------------------------------------------------------------- #
# FakeKey                                                                     #
# --------------------------------------------------------------------------- #

def test_fake_key_attributes():
    key = FakeKey("order", "abc")
    assert key.kind == "order"
    assert key.id_or_name == "abc"


def test_fake_key_equality_and_hash():
    a = FakeKey("order", "abc")
    b = FakeKey("order", "abc")
    c = FakeKey("order", "xyz")

    assert a == b
    assert a != c
    assert a != "not a key"
    assert hash(a) == hash(b)
    # Usable as a dict key
    d = {a: 1}
    assert d[b] == 1


def test_fake_key_from_legacy_urlsafe_ok():
    key = FakeKey.from_legacy_urlsafe("deadbeef")
    assert key.kind == "entity"
    assert key.id_or_name == "deadbeef"


def test_fake_key_from_legacy_urlsafe_bad_raises():
    with pytest.raises(ValueError):
        FakeKey.from_legacy_urlsafe("BAD")


# --------------------------------------------------------------------------- #
# FakeEntity                                                                  #
# --------------------------------------------------------------------------- #

def test_fake_entity_is_dict():
    entity = FakeEntity(FakeKey("order", "abc"), {"amount": 99})
    entity["customer"] = "k/xyz"
    assert entity["amount"] == 99
    assert entity["customer"] == "k/xyz"
    assert entity.key == FakeKey("order", "abc")


def test_fake_entity_default_exclude_set_is_empty():
    entity = FakeEntity()
    assert entity.exclude_from_indexes == set()
    assert entity.key is None


# --------------------------------------------------------------------------- #
# FakeQuery                                                                   #
# --------------------------------------------------------------------------- #

def test_fake_query_chainable_filter_and_order():
    q = FakeQuery("order_revision")
    assert q.filter("a =", 1) is q
    assert q.order(("x", FakeSortOrder.Descending)) is q
    assert q.filters == [("a =", 1)]
    assert q.orders == [("x", FakeSortOrder.Descending)]


def test_fake_query_get_entry_default_none():
    assert FakeQuery().getEntry() is None


def test_fake_query_fetch_and_iter_return_iter_result():
    q = FakeQuery()
    q._iter_result = ["a", "b"]
    assert q.fetch(100) == ["a", "b"]
    assert list(q.iter()) == ["a", "b"]


def test_fake_query_carries_kind_through_namespaces():
    q = FakeQuery("order_revision")
    assert q.kind == "order_revision"
    assert q.queries.kind == "order_revision"
    assert q.srcSkel.kindName == ""


# --------------------------------------------------------------------------- #
# FakeSortOrder                                                               #
# --------------------------------------------------------------------------- #

def test_fake_sort_order_values():
    assert FakeSortOrder.Ascending == "asc"
    assert FakeSortOrder.Descending == "desc"


# --------------------------------------------------------------------------- #
# DbState                                                                     #
# --------------------------------------------------------------------------- #

def test_db_state_defaults():
    state = DbState()
    assert state.store == {}
    assert state.put_calls == []
    assert state.delete_calls == []
    assert state.get_result == "USE_STORE"
    assert state.allocate_keys == []
    assert callable(state.query_factory)
    assert isinstance(state.query_factory("any"), FakeQuery)


def test_db_state_reset_clears_everything():
    state = DbState()
    state.store[FakeKey("x", 1)] = FakeEntity()
    state.put_calls.append(FakeEntity())
    state.delete_calls.append("k")
    state.get_result = "pinned"
    state.allocate_keys.append(FakeKey("x", 2))
    state.query_factory = lambda kind: "custom"

    state.reset()

    assert state.store == {}
    assert state.put_calls == []
    assert state.delete_calls == []
    assert state.get_result == "USE_STORE"
    assert state.allocate_keys == []
    assert isinstance(state.query_factory("any"), FakeQuery)
