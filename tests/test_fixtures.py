"""Unit tests for the pytest fixtures defined in :mod:`viur.light_mock.fixtures`.

These tests run *under* the plugin itself, so the fixtures must be
auto-discovered without any explicit ``conftest.py`` wiring.
"""
from __future__ import annotations

import datetime

from viur.light_mock.fakes import DbState, FakeKey


# --------------------------------------------------------------------------- #
# autouse reset                                                               #
# --------------------------------------------------------------------------- #

def test_autouse_resets_state_between_runs_first(db_state: DbState):
    """Leak some state into db_state — the next test must NOT see it."""
    db_state.put_calls.append("LEAK")
    db_state.store[FakeKey("x", 1)] = "marker"


def test_autouse_resets_state_between_runs_second(db_state: DbState):
    """Verify the autouse reset wiped what the previous test added."""
    assert "LEAK" not in db_state.put_calls
    assert db_state.store == {}


# --------------------------------------------------------------------------- #
# db_state                                                                    #
# --------------------------------------------------------------------------- #

def test_db_state_is_singleton(db_state: DbState):
    from viur.light_mock.fakes import db_state as module_singleton
    assert db_state is module_singleton


# --------------------------------------------------------------------------- #
# freeze_time                                                                 #
# --------------------------------------------------------------------------- #

def test_freeze_time_default_now(freeze_time):
    from viur.core import utils
    assert utils.utcNow() == freeze_time.now


def test_freeze_time_set_moves_now(freeze_time):
    from viur.core import utils
    target = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
    freeze_time.set(target)
    assert utils.utcNow() == target
    assert freeze_time.now == target


def test_freeze_time_does_not_leak_to_next_test(freeze_time):
    """Fixture re-installation gives a fresh default each test."""
    from viur.core import utils
    # If the previous test had moved the clock to 2030, fixture init in this
    # test must reset it back to the module default.
    assert utils.utcNow().year == 2026


# --------------------------------------------------------------------------- #
# make_query                                                                  #
# --------------------------------------------------------------------------- #

def test_make_query_single_result(make_query):
    from viur.core import db
    make_query(single="single-result")
    q = db.Query("k")
    assert q.getEntry() == "single-result"


def test_make_query_many_results(make_query):
    from viur.core import db
    make_query(many=["a", "b", "c"])
    q = db.Query("k")
    assert q.fetch(100) == ["a", "b", "c"]
    assert list(q.iter()) == ["a", "b", "c"]


def test_make_query_defaults_to_empty(make_query):
    from viur.core import db
    make_query()
    q = db.Query("k")
    assert q.getEntry() is None
    assert q.fetch(10) == []


# --------------------------------------------------------------------------- #
# patched_user                                                                #
# --------------------------------------------------------------------------- #

def test_patched_user_sets_and_resets(patched_user):
    from viur.core import current
    patched_user({"name": "alice", "access": ["root"]})
    assert current.user.get() == {"name": "alice", "access": ["root"]}


def test_patched_user_was_reset_after_previous_test():
    from viur.core import current
    assert current.user.get() is None


def test_patched_user_accepts_none(patched_user):
    from viur.core import current
    patched_user({"name": "alice"})
    assert current.user.get() == {"name": "alice"}
    patched_user(None)
    assert current.user.get() is None
