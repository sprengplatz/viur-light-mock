"""Tests for the pytest plugin entry-point in :mod:`viur.light_mock.plugin`."""
from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace

import viur.light_mock.plugin as plugin


def test_plugin_installed_mocks_on_import():
    """Importing the plugin module installs the fakes — the fixtures we use
    everywhere else only work because of this side-effect."""
    assert "viur.core.db" in sys.modules
    assert "viur.core.utils" in sys.modules


def test_plugin_reexports_fixtures():
    """Pytest discovers fixtures by attribute lookup on the plugin module."""
    for name in ("db_state", "freeze_time", "make_query", "patched_user",
                 "_viur_light_mock_reset_state"):
        attr = getattr(plugin, name)
        # pytest wraps decorated fixture functions; the public marker varies
        # by pytest version, but the repr always contains "fixture".
        assert "fixture" in repr(attr).lower(), name


def test_pytest_configure_reinstalls_mocks():
    """Trampling sys.modules before pytest_configure → hook restores them."""
    sys.modules["viur.core.db"] = None        # type: ignore[assignment]
    plugin.pytest_configure(SimpleNamespace())
    assert sys.modules["viur.core.db"] is not None
    # And the freshly installed module exposes the expected surface.
    from viur.core import db
    assert callable(db.Put)


def test_real_viur_core_present_true_for_on_disk_spec(monkeypatch):
    """A spec with a real ``origin`` (an on-disk package) counts as present."""
    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name: SimpleNamespace(origin="/somewhere/viur/core/__init__.py"),
    )
    assert plugin._real_viur_core_present() is True


def test_real_viur_core_present_false_for_namespace_spec(monkeypatch):
    """A namespace-package spec (``origin is None``) is only the ``viur``
    namespace, not a real viur.core."""
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: SimpleNamespace(origin=None),
    )
    assert plugin._real_viur_core_present() is False


def test_real_viur_core_present_false_when_find_spec_raises(monkeypatch):
    """``find_spec`` raises ValueError for our own fakes (no ``__spec__``)."""
    def _boom(name):
        raise ValueError("no __spec__")

    monkeypatch.setattr(importlib.util, "find_spec", _boom)
    assert plugin._real_viur_core_present() is False


def test_install_mocks_skipped_when_real_core_present(monkeypatch):
    """Overlay mode: a real viur-core is left untouched, fakes not installed."""
    calls = []
    monkeypatch.setattr(plugin, "_real_viur_core_present", lambda: True)
    monkeypatch.setattr(plugin, "install_viur_core_mocks", lambda: calls.append(1))

    assert plugin._install_mocks_unless_real_core() is False
    assert calls == []


def test_install_mocks_runs_when_no_real_core(monkeypatch):
    """Package mode: no real viur-core → fakes are installed."""
    calls = []
    monkeypatch.setattr(plugin, "_real_viur_core_present", lambda: False)
    monkeypatch.setattr(plugin, "install_viur_core_mocks", lambda: calls.append(1))

    assert plugin._install_mocks_unless_real_core() is True
    assert calls == [1]
