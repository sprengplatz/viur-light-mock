"""
viur-light-mock — pytest helpers for ViUR-based packages.

Provides a pytest plugin that injects lightweight stand-ins for the
``viur.core.*`` modules into ``sys.modules`` before tests are collected,
so packages that depend on viur-core can run their unit tests without
pulling the full Google App Engine stack.

Public surface:

- [`install_viur_core_mocks`][viur.light_mock.install_viur_core_mocks] —
  manual entry-point if you can't use the pytest plugin.
- [`FakeKey`][viur.light_mock.FakeKey], [`FakeEntity`][viur.light_mock.FakeEntity],
  [`FakeQuery`][viur.light_mock.FakeQuery], [`DbState`][viur.light_mock.DbState] —
  the data types that back the mocks.
- Fixtures (auto-discovered when pytest sees the plugin):
  ``db_state``, ``freeze_time``, ``make_query``, ``patched_user``.
"""
from .fakes import DbState, FakeEntity, FakeKey, FakeQuery, FakeSortOrder
from .modules import install_viur_core_mocks
from .overlay import install_db_overlay, set_request

__all__ = [
    "DbState",
    "FakeEntity",
    "FakeKey",
    "FakeQuery",
    "FakeSortOrder",
    "install_viur_core_mocks",
    "install_db_overlay",
    "set_request",
]

__version__ = "0.1.0"
