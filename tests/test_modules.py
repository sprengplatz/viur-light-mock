"""Unit tests for :mod:`viur.light_mock.modules`.

Covers ``install_viur_core_mocks`` end-to-end plus the behaviour of every
fake module surface (db CRUD, utils.utcNow, errors hierarchy, current slots,
skeleton bases, tasks decorator, render encoder, identity decorators).
"""
from __future__ import annotations

import datetime
import json
import sys
from typing import Any

import pytest

from viur.light_mock.fakes import FakeKey, FakeQuery, db_state
from viur.light_mock.modules import (
    _identity_decorator,
    _make_render_module,
    install_viur_core_mocks,
)


# --------------------------------------------------------------------------- #
# install_viur_core_mocks                                                     #
# --------------------------------------------------------------------------- #

def test_install_registers_all_modules_in_sys_modules():
    install_viur_core_mocks()

    for name in (
        "viur.core",
        "viur.core.db",
        "viur.core.utils",
        "viur.core.errors",
        "viur.core.current",
        "viur.core.skeleton",
        "viur.core.tasks",
        "viur.core.render",
        "viur.core.render.json",
        "viur.core.render.json.default",
    ):
        assert name in sys.modules, name


def test_install_returns_mapping_with_all_modules():
    result = install_viur_core_mocks()
    assert set(result) == {
        "viur.core",
        "db", "utils", "errors", "current", "skeleton", "tasks",
        "render", "render_json", "render_json_default",
        "bones_base", "conf",
    }


def test_install_is_idempotent_and_resets_modules():
    first = install_viur_core_mocks()
    second = install_viur_core_mocks()
    assert first["db"] is not second["db"]
    assert sys.modules["viur.core.db"] is second["db"]


def test_install_attaches_submodules_to_viur_core():
    install_viur_core_mocks()
    viur_core = sys.modules["viur.core"]
    assert viur_core.db is sys.modules["viur.core.db"]
    assert viur_core.utils is sys.modules["viur.core.utils"]
    assert viur_core.errors is sys.modules["viur.core.errors"]
    assert viur_core.current is sys.modules["viur.core.current"]
    assert viur_core.skeleton is sys.modules["viur.core.skeleton"]
    assert viur_core.tasks is sys.modules["viur.core.tasks"]
    assert viur_core.render is sys.modules["viur.core.render"]
    assert viur_core.conf is not None


# --------------------------------------------------------------------------- #
# DefaultRender stand-in                                                      #
# --------------------------------------------------------------------------- #

def test_default_render_class_is_present():
    install_viur_core_mocks()
    from viur.core.render.json.default import DefaultRender
    assert DefaultRender.kind == "json"


def test_default_render_methods_return_origin_tuples():
    install_viur_core_mocks()
    from viur.core.render.json.default import DefaultRender
    r = DefaultRender()
    assert r.view("skel-x")[0] == "orig-view"
    assert r.list(["a", "b"])[0] == "orig-list"
    assert r.add("skel-x")[0] == "orig-add"
    assert r.edit("skel-x")[0] == "orig-edit"
    assert r.delete("skel-x")[0] == "orig-delete"


def test_default_render_structure_is_pass_through_staticmethod():
    install_viur_core_mocks()
    from viur.core.render.json.default import DefaultRender
    structure = {"name": {"type": "string"}}
    assert DefaultRender.render_structure(structure) is structure


# --------------------------------------------------------------------------- #
# conf stand-in                                                               #
# --------------------------------------------------------------------------- #

def test_conf_supports_attribute_access():
    """Mirrors viur-core's strict-mode conf — attribute access only."""
    install_viur_core_mocks()
    from viur.core import conf

    # Plugins attach their own namespace…
    class _Namespace:
        envelope = False

    conf.actions = _Namespace()
    assert conf.actions.envelope is False
    conf.actions.envelope = True
    assert conf.actions.envelope is True


# --------------------------------------------------------------------------- #
# bones.base stand-in                                                         #
# --------------------------------------------------------------------------- #

def test_bones_base_severity_enum():
    install_viur_core_mocks()
    from viur.core.bones.base import ReadFromClientErrorSeverity as Severity
    assert Severity.NotSet == 0
    assert Severity.InvalidatesOther == 1
    assert Severity.Empty == 2
    assert Severity.Invalid == 3


def test_bones_base_read_from_client_error_dataclass():
    install_viur_core_mocks()
    from viur.core.bones.base import (
        ReadFromClientError,
        ReadFromClientErrorSeverity,
    )
    err = ReadFromClientError(
        severity=ReadFromClientErrorSeverity.Empty,
        errorMessage="Required",
        fieldPath=["amount"],
        invalidatedFields=["total"],
    )
    assert err.severity == ReadFromClientErrorSeverity.Empty
    assert err.errorMessage == "Required"
    assert err.fieldPath == ["amount"]
    assert err.invalidatedFields == ["total"]


def test_bones_base_module_is_attached_to_viur_core():
    install_viur_core_mocks()
    import viur.core.bones.base as bones_base
    from viur.core import bones
    assert bones.base is bones_base


# --------------------------------------------------------------------------- #
# db module                                                                   #
# --------------------------------------------------------------------------- #

def test_db_put_assigns_key_when_missing(db_state):
    from viur.core import db
    entity = db.Entity()   # no key
    db.Put(entity)
    assert entity.key is not None
    assert entity.key.kind == "auto"
    assert entity in db_state.put_calls
    assert db_state.store[entity.key] is entity


def test_db_put_preserves_existing_key(db_state):
    from viur.core import db
    key = db.Key("order", "abc")
    entity = db.Entity(key)
    db.Put(entity)
    assert entity.key is key
    assert db_state.store[key] is entity


def test_db_get_falls_back_to_store(db_state):
    from viur.core import db
    key = db.Key("order", "abc")
    entity = db.Entity(key)
    db_state.store[key] = entity
    assert db.Get(key) is entity


def test_db_get_returns_pinned_result_when_get_result_set(db_state):
    from viur.core import db
    db_state.get_result = "PINNED"
    assert db.Get(db.Key("order", "abc")) == "PINNED"


def test_db_delete_pops_and_records(db_state):
    from viur.core import db
    key = db.Key("order", "abc")
    db_state.store[key] = db.Entity(key)
    db.Delete(key)
    assert key in db_state.delete_calls
    assert key not in db_state.store


def test_db_delete_tolerates_missing_key(db_state):
    from viur.core import db
    key = db.Key("missing", "x")
    db.Delete(key)   # no exception
    assert key in db_state.delete_calls


def test_db_allocate_ids_returns_unique_keys(db_state):
    from viur.core import db
    template = db.Key("order_revision", None)
    a = db.AllocateIDs(template)
    b = db.AllocateIDs(template)
    assert a != b
    assert a.kind == b.kind == "order_revision"
    assert {a, b} == set(db_state.allocate_keys)


def test_db_query_uses_query_factory(db_state):
    from viur.core import db
    q = db.Query("order_revision")
    assert isinstance(q, FakeQuery)
    assert q.kind == "order_revision"


def test_db_query_factory_replaceable(db_state):
    from viur.core import db
    called: list[Any] = []

    def custom_factory(kind):
        called.append(kind)
        return "sentinel"

    db_state.query_factory = custom_factory
    assert db.Query("k") == "sentinel"
    assert called == ["k"]


# --------------------------------------------------------------------------- #
# utils module                                                                #
# --------------------------------------------------------------------------- #

def test_utils_utcnow_returns_frozen_default():
    install_viur_core_mocks()   # fresh install, fresh ``_now``
    from viur.core import utils
    now = utils.utcNow()
    assert isinstance(now, datetime.datetime)
    assert now.tzinfo is not None
    # The stand-in starts at 2026-05-20 12:00 UTC unless monkeypatched.
    assert now == datetime.datetime(2026, 5, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)


# --------------------------------------------------------------------------- #
# errors module                                                               #
# --------------------------------------------------------------------------- #

def test_errors_are_exception_subclasses():
    from viur.core import errors
    for name in ("Unauthorized", "Forbidden", "BadRequest", "NotFound"):
        cls = getattr(errors, name)
        assert issubclass(cls, Exception)


def test_errors_can_be_raised_and_caught():
    from viur.core import errors
    with pytest.raises(errors.Forbidden):
        raise errors.Forbidden("nope")


# --------------------------------------------------------------------------- #
# current module                                                              #
# --------------------------------------------------------------------------- #

def test_current_slots_get_set():
    install_viur_core_mocks()
    from viur.core import current
    assert current.user.get() is None
    current.user.set({"name": "alice"})
    assert current.user.get() == {"name": "alice"}

    assert current.request.get() is None
    current.request.set("REQ")
    assert current.request.get() == "REQ"


# --------------------------------------------------------------------------- #
# skeleton module                                                             #
# --------------------------------------------------------------------------- #

def test_skeleton_can_be_instantiated_and_set_entity():
    from viur.core import db
    from viur.core.skeleton import Skeleton

    skel = Skeleton()
    skel.__init__()
    entity = db.Entity(db.Key("k", "v"))
    skel.setEntity(entity)
    assert skel.dbEntity is entity
    assert skel.errors == []


def test_skeleton_instance_dict_like_and_set_entity():
    from viur.core import db
    from viur.core.skeleton import SkeletonInstance

    si = SkeletonInstance(cls=type("X", (), {}), kind_name="k")
    si["amount"] = 99
    assert si["amount"] == 99

    e = db.Entity(db.Key("k", "v"))
    si.setEntity(e)
    assert si.dbEntity is e
    assert si.kindName == "k"
    assert si.errors == []


def test_database_adapter_prewrite_is_no_op():
    from viur.core.skeleton import DatabaseAdapter
    DatabaseAdapter().prewrite("anything")   # does not raise, returns None


# --------------------------------------------------------------------------- #
# tasks module                                                                #
# --------------------------------------------------------------------------- #

def test_periodic_task_returns_function_unchanged_with_tag():
    from viur.core.tasks import PeriodicTask

    @PeriodicTask(datetime.timedelta(days=1), cronName="default")
    def my_job():
        return "ran"

    assert my_job() == "ran"
    args, kwargs = my_job._periodic_task
    assert args == (datetime.timedelta(days=1),)
    assert kwargs == {"cronName": "default"}


# --------------------------------------------------------------------------- #
# render module                                                               #
# --------------------------------------------------------------------------- #

def test_render_module_exposes_custom_json_encoder():
    from viur.core.render.json.default import CustomJsonEncoder
    assert CustomJsonEncoder is json.JSONEncoder


def test_make_render_module_returns_three_modules():
    render, render_json, render_json_default = _make_render_module()
    assert render.__name__ == "viur.core.render"
    assert render_json.__name__ == "viur.core.render.json"
    assert render_json_default.__name__ == "viur.core.render.json.default"


# --------------------------------------------------------------------------- #
# Identity decorators                                                         #
# --------------------------------------------------------------------------- #

def test_identity_decorator_returns_function_unchanged():
    def fn():
        return 42
    assert _identity_decorator(fn) is fn


def test_viur_core_exposes_identity_decorators():
    from viur.core import exposed, force_post, skey
    assert exposed is force_post is skey
