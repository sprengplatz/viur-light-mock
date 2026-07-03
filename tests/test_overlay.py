"""Tests for overlay mode — patch a *real* viur-core's external seams onto db_state.

Unlike ``install_viur_core_mocks`` (which replaces viur.core wholesale for
packages that have no viur-core installed), the overlay only redirects the
Datastore/request/task seams an application's real viur-core reaches through,
so the full framework keeps running while I/O stays in-memory.

Note: ``viur.core.db`` / ``viur.core.current`` are imported *inside* each test,
not at module level. Other tests in this suite re-run ``install_viur_core_mocks``
and swap the fake module objects in ``sys.modules``; a module-level binding would
go stale and point at a different object than the one ``install_db_overlay``
patches.
"""
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
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    pinned = db.Entity(db.Key("thing", 99))
    state.get_result = pinned

    # even for a key that was never stored, get hands back the pinned result
    assert db.get(db.Key("thing", 1)) is pinned


def test_db_overlay_get_batch_returns_list_aligned_to_input_keys(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    found = db.Entity(db.Key("thing", 1))
    db.put(found)
    missing_key = db.Key("thing", 2)

    result = db.get([found.key, missing_key])

    assert result == [found, None]


def test_db_overlay_allocate_ids_returns_a_list_of_recorded_keys(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)

    keys = db.allocate_ids("thing")

    assert isinstance(keys, list) and len(keys) == 1
    assert keys[0] in state.allocate_keys


def test_db_overlay_put_allocates_key_for_keyless_entity(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)

    entity = db.Entity()  # keyless — mirrors a freshly cloned skeleton
    db.put(entity)

    assert entity.key is not None
    assert state.store[entity.key] is entity


def test_db_overlay_runs_transactions_inline_and_returns_result(monkeypatch):
    import viur.core.db as db
    install_db_overlay(monkeypatch)
    seen = []

    def txn(a, b):
        seen.append((a, b))
        return a + b

    result = db.RunInTransaction(txn, 2, 3)

    assert result == 5
    assert seen == [(2, 3)]


def test_set_request_makes_current_request_get_return_the_namespace(monkeypatch):
    import viur.core.current as current
    req = set_request(monkeypatch, kwargs={"parententry": "abc"})

    assert current.request.get() is req
    assert current.request.get().kwargs["parententry"] == "abc"
