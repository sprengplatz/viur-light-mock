"""Tests for overlay mode — a real viur-core wired to an in-memory datastore.

``install_db_overlay`` swaps the *datastore client*, so everything asserted here
is produced by viur's own ``db`` functions running for real. See
``test_seam_contracts.py`` for the contract-parity proof, and ``conftest.py`` for
why this lives in its own test root.

``viur.core.db`` is imported *inside* each test rather than at module level, so
each test states plainly which viur it expects — the package's other test root
installs the stand-ins into ``sys.modules`` and never restores them.
"""
import pytest

from viur.light_mock.overlay import install_db_overlay, set_request


def test_db_overlay_routes_put_then_get_through_in_memory_store(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)

    key = db.Key("thing", 1)
    entity = db.Entity(key)
    entity["x"] = 42

    db.put(entity)

    assert db.get(key) is entity
    assert entity in state.put_calls


def test_db_overlay_delete_removes_entity_and_records_call(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    key = db.Key("thing", 2)
    db.put(db.Entity(key))

    db.delete(key)

    assert db.get(key) is None
    assert key in state.delete_calls


def test_db_overlay_get_returns_pinned_result_when_sentinel_overridden(monkeypatch):
    """``DbState.get_result`` pins the single-key form only. A pinned scalar
    cannot travel through viur's batch branch, which sorts the result."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    pinned = db.Entity(db.Key("thing", 99))
    state.get_result = pinned

    # even for a key that was never stored, get hands back the pinned result
    assert db.get(db.Key("thing", 1)) is pinned


def test_db_overlay_allocate_ids_returns_a_list_of_recorded_keys(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)

    keys = db.allocate_ids("thing")

    assert isinstance(keys, list) and len(keys) == 1
    assert keys[0] in state.allocate_keys


def test_db_overlay_runs_transactions_inline_and_returns_result(monkeypatch):
    import viur.core.db as db
    install_db_overlay(monkeypatch)
    seen = []

    def txn(a, b):
        seen.append((a, b))
        return a + b

    # RunInTransaction is deprecated in viur-core 3.8+. The real wrapper runs now
    # that the overlay no longer replaces the function, so the warning is part of
    # the contract rather than noise.
    with pytest.warns(DeprecationWarning):
        result = db.RunInTransaction(txn, 2, 3)

    assert result == 5
    assert seen == [(2, 3)]


def test_set_request_makes_current_request_get_return_the_namespace(monkeypatch):
    import viur.core.current as current
    req = set_request(monkeypatch, kwargs={"parententry": "abc"})

    assert current.request.get() is req
    assert current.request.get().kwargs["parententry"] == "abc"
