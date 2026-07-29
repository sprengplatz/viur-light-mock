"""Overlay mode — run a *real* viur-core against an in-memory datastore.

:func:`install_viur_core_mocks` (see :mod:`viur.light_mock.modules`) replaces the
whole ``viur.core.*`` hierarchy in ``sys.modules`` — the right tool for a package
that has no viur-core installed. An *application* test suite is the opposite
case: real viur-core is installed and the production code is built on the full
framework (prototypes, bones, compute, skeletons). There, faking the framework is
neither possible nor desirable; you only want to stop the process from reaching
outside itself — to the Datastore, the request context, the task queue.

**Replace the client, not the functions.** Earlier versions of this module
monkeypatched ``db.get``/``put``/``delete``/... with hand-written stand-ins. That
approach is why seven contracts had quietly drifted away from viur: a
hand-maintained patch set has to be kept in step with viur by hand, and it was
not. ``allocate_ids`` accepted a Key that production rejects with ``TypeError``
(green test, broken live); ``put``/``delete`` refused the list form production
supports (red test on working code); ``run_in_transaction`` was not intercepted
at all, so every write test opened a real transaction against a real project.

So instead: swap out the *datastore client*. viur's own transport functions then
execute for real — their branching, their return shapes, their access log — and
the only thing that changed is where the data lives. Nothing about the Datastore
contract is restated here, which means nothing about it can drift.
"""
from __future__ import annotations

import contextlib
import itertools
import types

from .fakes import DbState, db_state

#: Members of ``google.cloud.datastore.Client`` that viur's db layer touches.
#: Anything outside this set is not implemented on purpose — see _StoreClient.


class _StoreClient:
    """Stand-in for ``google.cloud.datastore.Client`` backed by a dict.

    Deliberately *not* a general datastore emulator. It implements exactly the
    members ``viur/core/db/{transport,utils,types}.py`` reach for, and mirrors
    their real error behaviour where it is load-bearing (a keyless entity is a
    ``ValueError``, a non-partial key to ``allocate_ids`` is a ``ValueError``) so
    the fake can never be more permissive than production.

    Queries are the exception: they are intercepted a layer higher, at
    ``Query._run_single_filter_query``, so that viur's own filter and sort
    helpers keep doing the work. Reaching :meth:`query` here therefore means the
    query seam has a hole, and it says so loudly rather than returning nothing.
    """

    def __init__(self, state: DbState, project: str) -> None:
        self._state = state
        #: ``Key.__init__`` (db/types.py) reads this locally — no I/O involved.
        self.project = project
        self.current_transaction: _StoreTransaction | None = None
        self._ids = itertools.count(1)

    # -- reads ---------------------------------------------------------------

    def get(self, key, *args, **kwargs):
        # ``DbState.get_result`` pins a fixed answer for the single-key form.
        # Not honoured for get_multi: a pinned scalar cannot sensibly travel
        # through viur's batch branch, which sorts the result.
        if self._state.get_result != "USE_STORE":
            return self._state.get_result
        return self._state.store.get(key)

    def get_multi(self, keys, missing=None, deferred=None, *args, **kwargs):
        # Misses are omitted, not padded — the real client only reports them if
        # the caller passes a ``missing`` list, and viur passes none.
        return [self._state.store[key] for key in keys if key in self._state.store]

    # -- writes --------------------------------------------------------------

    def put(self, entity, *args, **kwargs):
        self._write(entity)

    def put_multi(self, entities, *args, **kwargs):
        for entity in entities:
            self._write(entity)

    def _write(self, entity) -> None:
        if entity.key is None:
            raise ValueError("Entity must have a key")
        if entity.key.is_partial:
            entity.key = self.allocate_ids(entity.key, 1)[0]
        self._state.store[entity.key] = entity
        self._state.put_calls.append(entity)

    def delete(self, key, *args, **kwargs):
        self._forget(key)

    def delete_multi(self, keys, *args, **kwargs):
        for key in keys:
            self._forget(key)

    def _forget(self, key) -> None:
        self._state.delete_calls.append(key)
        self._state.store.pop(key, None)

    # -- keys ----------------------------------------------------------------

    def allocate_ids(self, incomplete_key, num_ids, retry=None, timeout=None):
        if not incomplete_key.is_partial:
            raise ValueError(("Key is already complete.", incomplete_key))
        keys = [
            incomplete_key.completed_key(next(self._ids)) for _ in range(num_ids)
        ]
        self._state.allocate_keys.extend(keys)
        return keys

    # -- transactions --------------------------------------------------------

    @contextlib.contextmanager
    def transaction(self, *args, **kwargs):
        """Scope only — there is no rollback.

        Writes land in the store immediately, so a failing transaction undoes
        nothing, and the Datastore quirk that reads inside a transaction see the
        pre-transaction state is not reproduced. What this *does* give viur is a
        truthful ``current_transaction``, which ``db.utils.is_in_transaction``
        and ``acquire_transaction_success_marker`` both depend on.
        """
        self.current_transaction = _StoreTransaction(next(self._ids))
        try:
            yield self.current_transaction
        finally:
            self.current_transaction = None

    # -- queries: intercepted higher up, must never arrive here --------------

    def query(self, *args, **kwargs):
        raise AssertionError(
            "query reached the in-memory client — the query seam is incomplete. "
            "Queries are meant to be served by the patched "
            "Query._run_single_filter_query, so results here would come from "
            "nowhere."
        )

    def aggregation_query(self, *args, **kwargs):
        raise AssertionError(
            "aggregation_query reached the in-memory client — the count seam is "
            "incomplete."
        )


class _StoreTransaction:
    """Minimal transaction handle. ``db.utils`` only reads ``.id``."""

    def __init__(self, id_: int) -> None:
        self.id = id_


def install_db_overlay(monkeypatch, *, state: DbState = db_state) -> DbState:
    """Point a real ``viur.core.db`` at an in-memory store.

    Returns the :class:`DbState` so a test can pre-seed ``store`` and assert on
    ``put_calls``/``delete_calls``.

    Requires **viur-core 3.8+**: older versions ship the datastore as
    ``viur-datastore`` with a compiled transport that exposes no client to swap.
    """
    import viur.core.db.transport as transport
    import viur.core.db.utils as db_utils

    real_client = getattr(transport, "__client__", None)
    if real_client is None:
        raise RuntimeError(
            "overlay mode needs viur-core 3.8+: viur.core.db.transport has no "
            "__client__ to replace. On viur-core 3.7 the datastore lives in the "
            "compiled viur-datastore package, which exposes no client."
        )

    client = _StoreClient(state, project=real_client.project)

    # Two bindings, not one: db/utils.py does a module-level
    # ``from .transport import __client__``, so it holds its own reference and
    # would keep talking to the real client. db/types.py imports inside the
    # function (circular-import workaround) and needs no patch.
    monkeypatch.setattr(transport, "__client__", client)
    monkeypatch.setattr(db_utils, "__client__", client)
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
