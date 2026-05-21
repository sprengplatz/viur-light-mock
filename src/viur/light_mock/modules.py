"""
``viur.core.*`` stand-in installer.

Builds a lightweight module hierarchy that mimics the parts of viur-core that
ViUR packages typically touch (db, utils, errors, current, skeleton, tasks,
render.json.default, plus the common decorators ``exposed``/``force_post``/
``skey``), then injects them into :data:`sys.modules` so production-code
imports like ``from viur.core import db`` resolve to the stand-ins.

This is the entry-point a host package calls — either implicitly via the
pytest plugin (see :mod:`viur.light_mock.plugin`) or explicitly from its own
``conftest.py``.
"""
from __future__ import annotations

import datetime
import json
import sys
import types
from typing import Any

from .fakes import FakeEntity, FakeKey, FakeQuery, FakeSortOrder, db_state


def _make_db_module() -> types.ModuleType:
    mod = types.ModuleType("viur.core.db")
    mod.Key = FakeKey
    mod.Entity = FakeEntity
    mod.Query = lambda kind=None: db_state.query_factory(kind)
    mod.SortOrder = FakeSortOrder
    mod.Get = lambda key: (
        db_state.store.get(key) if db_state.get_result == "USE_STORE"
        else db_state.get_result
    )

    def _put(entity: FakeEntity) -> None:
        if entity.key is None:
            entity.key = FakeKey("auto", len(db_state.store))
        db_state.store[entity.key] = entity
        db_state.put_calls.append(entity)

    def _delete(key: Any) -> None:
        db_state.delete_calls.append(key)
        db_state.store.pop(key, None)

    def _allocate_ids(template: FakeKey) -> FakeKey:
        new_key = FakeKey(template.kind, f"auto-{len(db_state.allocate_keys)}")
        db_state.allocate_keys.append(new_key)
        return new_key

    mod.Put = _put
    mod.Delete = _delete
    mod.AllocateIDs = _allocate_ids
    return mod


def _make_utils_module() -> types.ModuleType:
    mod = types.ModuleType("viur.core.utils")
    mod._now = datetime.datetime(2026, 5, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mod.utcNow = lambda: mod._now
    return mod


def _make_errors_module() -> types.ModuleType:
    mod = types.ModuleType("viur.core.errors")

    class _ViurError(Exception):
        pass

    class Unauthorized(_ViurError): ...
    class Forbidden(_ViurError): ...
    class BadRequest(_ViurError): ...
    class NotFound(_ViurError): ...

    mod.Unauthorized = Unauthorized
    mod.Forbidden = Forbidden
    mod.BadRequest = BadRequest
    mod.NotFound = NotFound
    return mod


def _make_current_module() -> types.ModuleType:
    mod = types.ModuleType("viur.core.current")

    class _Slot:
        def __init__(self, value: Any = None) -> None:
            self._value = value

        def get(self) -> Any:
            return self._value

        def set(self, value: Any) -> None:
            self._value = value

    mod.user = _Slot()
    mod.request = _Slot()
    return mod


def _make_skeleton_module() -> types.ModuleType:
    mod = types.ModuleType("viur.core.skeleton")

    class Skeleton:
        database_adapters: list[Any] = []

        def __new__(cls, *args: Any, **kwargs: Any) -> "Skeleton":
            return object.__new__(cls)

        def __init__(self) -> None:
            self.dbEntity: FakeEntity | None = None
            self.errors: list[Any] = []

        def setEntity(self, entity: FakeEntity) -> None:
            self.dbEntity = entity

    class SkeletonInstance:
        """Dict-ish wrapper around ``dbEntity``."""

        def __init__(self, cls: type, kind_name: str = "") -> None:
            self.skeletonCls = cls
            self.kindName = kind_name
            self.dbEntity: FakeEntity | None = None
            self.errors: list[Any] = []
            self._data: dict[str, Any] = {}

        def __setitem__(self, key: str, value: Any) -> None:
            self._data[key] = value

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

        def setEntity(self, entity: FakeEntity) -> None:
            self.dbEntity = entity

    class DatabaseAdapter:
        def prewrite(self, *args: Any, **kwargs: Any) -> None: ...

    mod.Skeleton = Skeleton
    mod.SkeletonInstance = SkeletonInstance
    mod.DatabaseAdapter = DatabaseAdapter
    return mod


def _make_tasks_module() -> types.ModuleType:
    mod = types.ModuleType("viur.core.tasks")

    def PeriodicTask(*args: Any, **kwargs: Any):
        """Decorator that returns the function unchanged but tags it with
        the original arguments so tests can inspect the schedule."""

        def _wrap(fn: Any) -> Any:
            fn._periodic_task = (args, kwargs)
            return fn

        return _wrap

    mod.PeriodicTask = PeriodicTask
    return mod


def _make_render_module() -> tuple[types.ModuleType, types.ModuleType, types.ModuleType]:
    render = types.ModuleType("viur.core.render")
    render_json = types.ModuleType("viur.core.render.json")
    render_json_default = types.ModuleType("viur.core.render.json.default")
    render_json_default.CustomJsonEncoder = json.JSONEncoder

    class DefaultRender:
        """Stand-in for viur.core.render.json.default.DefaultRender.

        Carries the same surface the renderer-patch code needs to wrap
        (``view`` / ``list`` / ``add`` / ``edit`` plus the success
        siblings ``addSuccess`` / ``editSuccess`` / ``deleteSuccess``,
        the ``kind`` attribute and the ``render_structure`` staticmethod).
        Each method returns a tuple identifying the call — tests can
        assert against those to detect whether the original or the
        patched code path executed.

        Deliberately does **not** carry a ``delete`` method: upstream
        viur-core has none, and its prototypes route the delete flow
        through ``deleteSuccess`` directly. Keeping the stand-in
        symmetric with the real renderer prevents downstream packages
        from accidentally patching a method that does not exist in
        production.
        """

        kind = "json"

        @staticmethod
        def render_structure(structure):
            """Pass-through stand-in for viur-core's compat wrapper."""
            return structure

        def view(self, skel, action="view", params=None, **kwargs):
            return ("orig-view", skel, action, params)

        def list(self, skellist, action="list", params=None, **kwargs):
            return ("orig-list", skellist, action, params)

        def add(self, skel, action="add", params=None, **kwargs):
            return ("orig-add", skel, action, params)

        def edit(self, skel, action="edit", params=None, **kwargs):
            return ("orig-edit", skel, action, params)

        def addSuccess(self, skel, action="addSuccess", params=None, **kwargs):
            return ("orig-addSuccess", skel, action, params)

        def editSuccess(self, skel, action="editSuccess", params=None, **kwargs):
            return ("orig-editSuccess", skel, action, params)

        def deleteSuccess(self, skel, action="deleteSuccess", params=None, **kwargs):
            return ("orig-deleteSuccess", skel, action, params)

    render_json_default.DefaultRender = DefaultRender
    return render, render_json, render_json_default


class _ConfStub:
    """Stand-in for viur-core's :class:`Conf` object.

    The real conf runs in **strict mode** in production: only attribute
    access is allowed, and the attribute must exist. This stub mirrors
    that contract — plugins attach their own namespaces via
    ``conf.foo = MyConfig()`` and read them via ``conf.foo.bar``.
    """

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"_ConfStub({vars(self)!r})"


def _make_conf_object() -> "_ConfStub":
    """A fresh, empty conf stand-in. Plugins set their own attributes."""
    return _ConfStub()


def _make_bones_base_module() -> types.ModuleType:
    """Stand-in for ``viur.core.bones.base`` — carries the two types the
    error helpers in downstream packages re-export
    (``ReadFromClientError`` + ``ReadFromClientErrorSeverity``)."""
    from dataclasses import dataclass, field as _field
    from enum import IntEnum

    mod = types.ModuleType("viur.core.bones.base")

    class ReadFromClientErrorSeverity(IntEnum):
        NotSet = 0
        InvalidatesOther = 1
        Empty = 2
        Invalid = 3

    @dataclass
    class ReadFromClientError:
        severity: ReadFromClientErrorSeverity
        errorMessage: str | None = None
        fieldPath: list = _field(default_factory=list)
        invalidatedFields: list | None = None

    mod.ReadFromClientErrorSeverity = ReadFromClientErrorSeverity
    mod.ReadFromClientError = ReadFromClientError
    return mod


def _identity_decorator(fn: Any) -> Any:
    return fn


def install_viur_core_mocks() -> dict[str, types.ModuleType]:
    """Install the fake ``viur.core.*`` modules into :data:`sys.modules`.

    Safe to call multiple times — re-running overwrites prior installations
    with fresh module objects, so any earlier monkeypatching gets reset.

    The real ``viur`` namespace package is left untouched so namespace
    siblings (``viur.revision``, ``viur.shop``, …) remain importable.

    :returns: A dict of the installed modules, keyed by their unqualified
        name (``"db"``, ``"utils"``, …) — useful when a host conftest needs
        to extend the stand-ins.
    """
    viur_core = types.ModuleType("viur.core")
    viur_core_bones = types.ModuleType("viur.core.bones")
    db_mod = _make_db_module()
    utils_mod = _make_utils_module()
    errors_mod = _make_errors_module()
    current_mod = _make_current_module()
    skeleton_mod = _make_skeleton_module()
    tasks_mod = _make_tasks_module()
    render_mod, render_json_mod, render_json_default_mod = _make_render_module()
    bones_base_mod = _make_bones_base_module()
    conf_obj = _make_conf_object()

    viur_core.db = db_mod
    viur_core.utils = utils_mod
    viur_core.errors = errors_mod
    viur_core.current = current_mod
    viur_core.skeleton = skeleton_mod
    viur_core.tasks = tasks_mod
    viur_core.render = render_mod
    viur_core.bones = viur_core_bones
    viur_core_bones.base = bones_base_mod
    viur_core.conf = conf_obj
    viur_core.exposed = _identity_decorator
    viur_core.force_post = _identity_decorator
    viur_core.skey = _identity_decorator

    sys.modules["viur.core"] = viur_core
    sys.modules["viur.core.db"] = db_mod
    sys.modules["viur.core.utils"] = utils_mod
    sys.modules["viur.core.errors"] = errors_mod
    sys.modules["viur.core.current"] = current_mod
    sys.modules["viur.core.skeleton"] = skeleton_mod
    sys.modules["viur.core.tasks"] = tasks_mod
    sys.modules["viur.core.render"] = render_mod
    sys.modules["viur.core.render.json"] = render_json_mod
    sys.modules["viur.core.render.json.default"] = render_json_default_mod
    sys.modules["viur.core.bones"] = viur_core_bones
    sys.modules["viur.core.bones.base"] = bones_base_mod

    return {
        "viur.core": viur_core,
        "db": db_mod,
        "utils": utils_mod,
        "errors": errors_mod,
        "current": current_mod,
        "skeleton": skeleton_mod,
        "tasks": tasks_mod,
        "render": render_mod,
        "render_json": render_json_mod,
        "render_json_default": render_json_default_mod,
        "bones_base": bones_base_mod,
        "conf": conf_obj,
    }
