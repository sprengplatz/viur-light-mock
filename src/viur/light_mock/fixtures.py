"""
Pytest fixtures for viur-light-mock.

Picked up automatically when ``viur-light-mock`` is installed alongside pytest
(via the ``pytest11`` entry-point defined in ``pyproject.toml``). No
``conftest.py`` boilerplate required in the host package.
"""
from __future__ import annotations

import datetime
import sys
from typing import Any

import pytest

from .fakes import DbState, FakeQuery, db_state as _db_state_singleton


@pytest.fixture(autouse=True)
def _viur_light_mock_reset_state() -> None:
    """Reset the fake datastore singleton before every test.

    Autouse so individual tests never see leakage from a previous run.
    """
    _db_state_singleton.reset()


@pytest.fixture
def db_state() -> DbState:
    """Direct handle on the fake datastore state for assertions.

    Tests typically poke at ``db_state.put_calls``, ``db_state.store``,
    ``db_state.delete_calls`` etc. to verify what the production code did.
    """
    return _db_state_singleton


@pytest.fixture
def freeze_time(monkeypatch: pytest.MonkeyPatch):
    """Pin ``utils.utcNow`` to a controllable value.

    Returns a freezer object with a ``.set(dt)`` method and a ``.now``
    attribute holding the current frozen value::

        def test_age(freeze_time):
            base = freeze_time.now
            freeze_time.set(base + datetime.timedelta(hours=1))
    """
    utils_mod = sys.modules["viur.core.utils"]

    class _TimeFreezer:
        def __init__(self) -> None:
            self.now = utils_mod._now

        def set(self, value: datetime.datetime) -> None:
            self.now = value
            monkeypatch.setattr(utils_mod, "utcNow", lambda: self.now)

    freezer = _TimeFreezer()
    freezer.set(freezer.now)
    return freezer


@pytest.fixture
def make_query(db_state: DbState):
    """Programmable query factory for a given test scenario.

    Call once with the desired result and any subsequent ``db.Query(...)``
    in production code will hand back a :class:`FakeQuery` pre-populated
    with that data::

        make_query(single=existing_entity)            # for ``.getEntry()``
        make_query(many=[entity_a, entity_b])         # for ``.fetch()``/``.iter()``
    """

    def _factory(*, single: Any = None, many: list[Any] | None = None) -> None:
        def _make(kind: str | None = None) -> FakeQuery:
            q = FakeQuery(kind)
            q._result = single
            q._iter_result = list(many or [])
            return q

        db_state.query_factory = _make

    return _factory


@pytest.fixture
def patched_user(monkeypatch: pytest.MonkeyPatch):
    """Set the fake ``current.user`` payload.

    Yields a setter callable so a test can switch users mid-flight if
    needed; resets to ``None`` after the test."""
    current_mod = sys.modules["viur.core.current"]

    def _set(user: dict[str, Any] | None) -> None:
        current_mod.user._value = user

    yield _set
    current_mod.user._value = None
