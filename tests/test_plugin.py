"""Tests for the pytest plugin entry-point in :mod:`viur.light_mock.plugin`."""
from __future__ import annotations

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
