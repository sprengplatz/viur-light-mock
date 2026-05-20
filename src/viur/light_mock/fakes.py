"""
Lightweight stand-ins for ``viur.core.db`` types.

These are the values that production code holds at runtime — every test
asserts against them via the :data:`db_state` singleton or the matching
fixture.
"""
from __future__ import annotations

import types
from typing import Any


class FakeKey:
    """Stand-in for ``viur.core.db.Key``.

    Just enough surface for the code paths exercised by ViUR-on-test:
    ``kind``/``id_or_name`` attributes, equality + hash so it can be used as
    a dict key, and a ``from_legacy_urlsafe`` classmethod that raises on the
    sentinel string ``"BAD"`` so tests can drive error paths.
    """

    def __init__(self, kind: str, id_or_name: Any = None):
        self.kind = kind
        self.id_or_name = id_or_name

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"FakeKey(kind={self.kind!r}, id={self.id_or_name!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FakeKey)
            and self.kind == other.kind
            and self.id_or_name == other.id_or_name
        )

    def __hash__(self) -> int:
        return hash((self.kind, self.id_or_name))

    @classmethod
    def from_legacy_urlsafe(cls, raw: str) -> "FakeKey":
        if raw == "BAD":
            raise ValueError("invalid key")
        return cls("entity", raw)


class FakeEntity(dict):
    """Dict subclass with a ``.key`` attr — mirrors ``db.Entity``."""

    def __init__(self, key: Any = None, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.key = key
        self.exclude_from_indexes: set[str] = set()


class FakeQuery:
    """Chainable, no-op query that records its calls for inspection."""

    def __init__(self, kind: str | None = None):
        self.kind = kind
        self.filters: list[tuple[str, Any]] = []
        self.orders: list[Any] = []
        self._result: Any = None
        self._iter_result: list[Any] = []
        # Mirror the real ``db.Query`` surface used by viur-core list code.
        self.queries = types.SimpleNamespace(kind=kind)
        self.srcSkel = types.SimpleNamespace(kindName="")

    def filter(self, expr: str, value: Any = None) -> "FakeQuery":
        self.filters.append((expr, value))
        return self

    def order(self, order: Any) -> "FakeQuery":
        self.orders.append(order)
        return self

    def getEntry(self) -> Any:
        return self._result

    def fetch(self, limit: int) -> list[Any]:
        return self._iter_result

    def iter(self) -> Any:
        return iter(self._iter_result)


class FakeSortOrder:
    Ascending = "asc"
    Descending = "desc"


class DbState:
    """In-memory datastore the fake ``db`` module reads from and writes to.

    Tests inspect ``put_calls`` / ``delete_calls`` / ``store`` to assert what
    the production code did, and reset the singleton between tests via the
    autouse fixture in :mod:`viur.light_mock.fixtures`.
    """

    def __init__(self) -> None:
        self.store: dict[Any, FakeEntity] = {}
        self.put_calls: list[FakeEntity] = []
        self.delete_calls: list[Any] = []
        # Sentinel: when ``"USE_STORE"`` (the default), ``db.Get`` looks the
        # key up in ``store``. Tests can pin a fixed return by assigning
        # any other value.
        self.get_result: Any = "USE_STORE"
        self.allocate_keys: list[FakeKey] = []
        self.query_factory = lambda kind: FakeQuery(kind)

    def reset(self) -> None:
        self.store.clear()
        self.put_calls.clear()
        self.delete_calls.clear()
        self.get_result = "USE_STORE"
        self.allocate_keys.clear()
        self.query_factory = lambda kind: FakeQuery(kind)


#: Process-wide singleton. The fake ``viur.core.db`` module talks to *this*
#: instance, and the ``db_state`` fixture returns it for assertions.
db_state = DbState()
