"""Proof that the overlay inherits viur's CRUD contracts instead of restating them.

``install_db_overlay`` replaces the datastore *client*
(``transport.__client__`` / ``utils.__client__``), so viur's own
``get``/``put``/``delete``/``allocate_ids``/``run_in_transaction`` execute for
real — branching, return shapes, access log and all. Nothing here should be
satisfied by code we wrote; every assertion below is what
``viur/core/db/transport.py`` does, and it passes because that very code runs.

That is the whole point, and it is worth pinning: an earlier version of the
overlay hand-faked these functions, and seven contracts had silently drifted
apart. Two directions of failure, both harmful:

* fake more permissive than production -> green test, broken live
  (``allocate_ids`` used to accept a Key);
* fake narrower than production -> red test on code that works live, so the path
  could not be tested at all (``put``/``delete`` with a list).

If a test in this file starts failing, the client fake has stopped standing in
for the real one faithfully — not that a contract "changed".
"""
import pytest

from viur.light_mock.overlay import install_db_overlay


def test_batch_get_omits_misses_rather_than_padding_with_none(monkeypatch):
    """``get_multi`` returns only what it found, so the result can be shorter
    than the input.

    Consequence, reproduced on purpose: viur's own
    ``if not all(db.get([...])): return []`` guard in ``RelationalBone``
    (relational.py:1145) cannot detect a missing key — the list holds only
    truthy entities. A fake that padded with ``None`` would make that guard
    appear to work, hiding a real viur bug behind green tests.
    """
    import viur.core.db as db
    install_db_overlay(monkeypatch)
    found = db.Entity(db.Key("thing", 1))
    db.put(found)
    missing_key = db.Key("thing", 2)

    result = db.get([found.key, missing_key])

    assert result == [found]


def test_batch_get_keeps_the_input_order(monkeypatch):
    import viur.core.db as db
    install_db_overlay(monkeypatch)
    first = db.Entity(db.Key("thing", 1))
    second = db.Entity(db.Key("thing", 2))
    # Non-empty on purpose. ``get`` sorts with
    # ``keys.index(k.key) if k else -1`` — and ``db.Entity`` is a dict, so an
    # empty entity is falsy and takes the ``-1`` branch. With empty entities
    # every sort key is -1 and this assertion would hold on list stability
    # alone, proving nothing about the ordering.
    first["x"] = 1
    second["x"] = 2
    db.put(first)
    db.put(second)

    assert db.get([second.key, first.key]) == [second, first]


def test_batch_get_with_a_set_breaks_exactly_like_production(monkeypatch):
    """Pins a viur bug rather than papering over it.

    ``get`` branches on ``isinstance(keys, (list, set, tuple))`` but then sorts
    with ``keys.index(...)`` — which a ``set`` does not have. It survives only
    while every hit takes the ``if k else -1`` branch, i.e. while the entities
    are empty and therefore falsy dicts; the first hit with content raises.
    Reproducing that is the honest option: were the fake to accept sets, a test
    would go green on a call that raises in production. Should viur ever fix
    this, this test fails and tells us to drop it.
    """
    import viur.core.db as db
    install_db_overlay(monkeypatch)
    entity = db.Entity(db.Key("thing", 1))
    entity["x"] = 1  # non-empty, so the sort really reaches ``keys.index``
    db.put(entity)

    with pytest.raises(AttributeError):
        db.get({entity.key})


def test_put_accepts_a_list_of_entities(monkeypatch):
    """Real ``put`` routes a list through ``put_multi``."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    first = db.Entity(db.Key("thing", 1))
    second = db.Entity(db.Key("thing", 2))

    db.put([first, second])

    assert state.store[first.key] is first
    assert state.store[second.key] is second


def test_put_rejects_a_keyless_entity(monkeypatch):
    """``Batch.put`` raises ``ValueError("Entity must have a key")``.

    The old hand-faked overlay quietly allocated one instead, so a call that
    raises in production passed in tests.
    """
    import viur.core.db as db
    install_db_overlay(monkeypatch)

    with pytest.raises(ValueError, match="must have a key"):
        db.put(db.Entity())


def test_put_completes_a_partial_key(monkeypatch):
    """A *partial* key is fine — the backend assigns the id on write."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    entity = db.Entity(db.Key("thing"))
    assert entity.key.is_partial

    db.put(entity)

    assert not entity.key.is_partial
    assert entity.key.kind == "thing"
    assert state.store[entity.key] is entity


def test_delete_accepts_a_list_of_keys(monkeypatch):
    """Real ``delete`` routes a list through ``delete_multi``."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    first = db.Entity(db.Key("thing", 1))
    second = db.Entity(db.Key("thing", 2))
    db.put(first)
    db.put(second)

    db.delete([first.key, second.key])

    assert state.store == {}


def test_allocate_ids_rejects_a_key_because_it_demands_a_string(monkeypatch):
    """``allocate_ids`` guards with ``if type(kind_name) is not str``.

    The fake must not be laxer here — that would turn a call which raises in
    production into a green test.
    """
    import viur.core.db as db
    install_db_overlay(monkeypatch)

    with pytest.raises(TypeError):
        db.allocate_ids(db.Key("thing"))


def test_allocate_ids_returns_a_list_of_the_requested_length(monkeypatch):
    import viur.core.db as db
    install_db_overlay(monkeypatch)

    keys = db.allocate_ids("thing", 2)

    assert isinstance(keys, list) and len(keys) == 2
    assert all(k.kind == "thing" and not k.is_partial for k in keys)


def test_deprecated_AllocateIDs_takes_a_key_and_returns_a_single_key(monkeypatch):
    """``AllocateIDs`` reads ``.kind`` off a Key and returns ``[...][0]`` — the
    two spellings are *not* interchangeable, which the old hand-faked overlay
    got wrong by pointing both at one function."""
    import viur.core.db as db
    install_db_overlay(monkeypatch)

    # Deprecated in 3.8+, and the real wrapper runs now, so the warning belongs
    # to the contract.
    with pytest.warns(DeprecationWarning):
        result = db.AllocateIDs(db.Key("thing"))

    assert not isinstance(result, list)
    assert result.kind == "thing"


def test_run_in_transaction_runs_inline_under_both_spellings(monkeypatch):
    """Regression guard. Only ``RunInTransaction`` used to be intercepted, while
    ``Skeleton.write`` calls the lowercase name — so every write test opened a
    real transaction against a real project. Under the client fake there is no
    name pair left to half-patch, and this pins that."""
    import viur.core.db as db
    install_db_overlay(monkeypatch)
    calls = []

    assert db.run_in_transaction(lambda a: calls.append(a) or a, 1) == 1
    with pytest.warns(DeprecationWarning):
        assert db.RunInTransaction(lambda a: calls.append(a) or a, 2) == 2
    assert calls == [1, 2]


def test_is_in_transaction_sees_the_fake_client(monkeypatch):
    """``db.utils`` holds its own ``__client__`` binding from a module-level
    from-import, so patching only ``transport.__client__`` would leave this
    reading the real client."""
    import viur.core.db as db
    install_db_overlay(monkeypatch)
    seen = []

    db.run_in_transaction(lambda: seen.append(db.is_in_transaction()))

    assert seen == [True]
    assert db.is_in_transaction() is False


def test_allocate_ids_refuses_a_complete_key_like_the_real_client(monkeypatch):
    """``Client.allocate_ids`` guards with ``if not incomplete_key.is_partial``.

    viur only ever passes a partial key, so this is reachable by direct client
    use — kept because dropping the guard would make the fake laxer than the
    thing it stands in for.
    """
    import viur.core.db as db
    import viur.core.db.transport as transport
    install_db_overlay(monkeypatch)

    with pytest.raises(ValueError, match="already complete"):
        transport.__client__.allocate_ids(db.Key("thing", 1), 1)


def test_query_execution_never_reaches_the_client(monkeypatch):
    """The fake client has no query support on purpose: everything query-shaped
    must be intercepted higher up. If this stops raising, the query seam has a
    hole and results would be coming from somewhere unintended."""
    import viur.core.db.transport as transport
    install_db_overlay(monkeypatch)

    with pytest.raises(AssertionError, match="query"):
        transport.__client__.query(kind="thing")


def test_aggregation_query_never_reaches_the_client(monkeypatch):
    """Same guard for the ``count`` path, which goes through
    ``client.aggregation_query`` in real viur."""
    import viur.core.db.transport as transport
    install_db_overlay(monkeypatch)

    with pytest.raises(AssertionError, match="aggregation_query"):
        transport.__client__.aggregation_query(None)


def test_install_refuses_a_viur_core_without_a_swappable_client(monkeypatch):
    """viur-core 3.7 ships the datastore as the compiled ``viur-datastore``,
    which exposes no client — there the overlay cannot work at all, and saying so
    beats patching nothing and looking like it worked."""
    import viur.core.db.transport as transport
    monkeypatch.delattr(transport, "__client__")

    with pytest.raises(RuntimeError, match="viur-core 3.8"):
        install_db_overlay(monkeypatch)
