"""Overlay mode — patch the external seams of a *real* viur-core.

:func:`install_viur_core_mocks` (see :mod:`viur.light_mock.modules`) replaces
the whole ``viur.core.*`` hierarchy in ``sys.modules`` — the right tool for a
package that has no viur-core installed. An *application* test suite is the
opposite case: real viur-core is installed and the production code is built on
the full framework (prototypes, bones, compute, skeletons). There, faking the
framework is neither possible nor desirable; you only want to intercept the
parts that reach outside the process — the Datastore, the request context and
the deferred-task queue.

The overlay helpers monkeypatch only those seams onto the in-memory
:data:`~viur.light_mock.fakes.db_state`, leaving bone serialization, compute
bones and tree logic running for real. Every patch goes through a pytest
``monkeypatch`` so it is undone after the test.
"""
from __future__ import annotations

import types

from .fakes import DbState, db_state


def install_db_overlay(monkeypatch, *, state: DbState = db_state) -> DbState:
    """Redirect ``viur.core.db`` reads/writes onto an in-memory store.

    Returns the :class:`DbState` so the test can pre-seed ``store`` and assert
    on ``put_calls``.
    """
    import viur.core.db as db

    def _get(key):
        if state.get_result != "USE_STORE":
            return state.get_result
        # Real db.Get accepts a single key or a sequence of keys (batch get) and
        # returns a list aligned to the input (None for misses). Relation
        # serialization (RefSkel denormalization) relies on the batch form.
        if isinstance(key, (list, tuple)):
            return [state.store.get(k) for k in key]
        return state.store.get(key)

    def _put(entity):
        if getattr(entity, "key", None) is None:
            entity.key = _allocate("entity")[0]
        state.store[entity.key] = entity
        state.put_calls.append(entity)
        return entity

    def _delete(key):
        state.delete_calls.append(key)
        state.store.pop(key, None)

    def _allocate(kind, count=1):
        kind_name = kind if isinstance(kind, str) else getattr(kind, "kind", str(kind))
        keys = [db.Key(kind_name, f"auto{len(state.allocate_keys) + i}") for i in range(count)]
        state.allocate_keys.extend(keys)
        return keys

    def _txn(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    # viur-core reaches the datastore through both the lowercase primitives
    # (Skeleton.read/write call db.get/put/...) and the capitalized aliases
    # (db.Get/Put used by app code, _resolve_org_keys, Compute bones). Patch both.
    seams = {
        "get": _get, "Get": _get,
        "put": _put, "Put": _put,
        "delete": _delete, "Delete": _delete,
        "allocate_ids": _allocate, "AllocateIDs": _allocate,
        "RunInTransaction": _txn,
    }
    for name, fn in seams.items():
        monkeypatch.setattr(db, name, fn, raising=False)
    return state


def set_request(monkeypatch, **attrs) -> types.SimpleNamespace:
    """Make ``current.request.get()`` return a throwaway namespace.

    ``current.request`` is a real ``ContextVar`` in viur-core, whose instance
    attributes can't be monkeypatched. Replacing the *module attribute* with a
    stand-in that has ``.get()`` works for both the real ContextVar and the
    fake slot, and is undone after the test::

        set_request(monkeypatch, kwargs={"parententry": "..."})
    """
    import viur.core.current as current

    req = types.SimpleNamespace(**attrs)
    monkeypatch.setattr(current, "request", types.SimpleNamespace(get=lambda: req))
    return req
