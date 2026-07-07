"""
Pytest entry-point for viur-light-mock.

Registered via ``[project.entry-points.pytest11]`` so pytest discovers and
loads this module before any test files are imported. Two responsibilities:

1. Install the fake ``viur.core.*`` modules into :data:`sys.modules` at
   plugin-load time (so production-code imports succeed during collection) —
   but *only* when no real viur-core is installed. An application test suite
   that runs against a real viur-core (using overlay mode, see
   :mod:`viur.light_mock.overlay`) must keep the genuine modules, or the fakes
   would clobber the very framework the overlay is meant to patch.
2. Re-export the fixtures from :mod:`viur.light_mock.fixtures` so pytest finds
   them when scanning this plugin module.
"""
from __future__ import annotations

import importlib.util

from .modules import install_viur_core_mocks


def _real_viur_core_present() -> bool:
    """Whether a genuine, on-disk viur-core can be imported.

    Uses :func:`importlib.util.find_spec` — *can it be imported?* — rather than
    "is it already in ``sys.modules``?", because pytest loads this plugin before
    the host package's ``conftest.py`` imports viur.core; at plugin-load time the
    real framework has typically not been imported yet.

    A namespace-package spec (``origin is None``) means only the ``viur``
    namespace exists, not a real ``viur.core`` — that is the case in this
    package's own test run, where our fakes live in ``sys.modules`` with no
    ``__spec__`` (``find_spec`` raises ``ValueError``, handled below).
    """
    try:
        spec = importlib.util.find_spec("viur.core")
    except (ImportError, ValueError):
        return False
    return spec is not None and spec.origin is not None


def _install_mocks_unless_real_core() -> bool:
    """Install the fakes unless a real viur-core is importable.

    Returns ``True`` if the stand-ins were installed, ``False`` if a real
    viur-core was detected and left untouched (overlay mode).
    """
    if _real_viur_core_present():
        return False
    install_viur_core_mocks()
    return True


# Install on plugin import. pytest loads this module via the ``pytest11``
# entry-point before any test file is collected, so this side-effect lands
# in ``sys.modules`` early enough for production imports inside the host
# package to resolve to the stand-ins.
_install_mocks_unless_real_core()

# Re-export fixtures so pytest discovers them on this plugin module.
from .fixtures import (  # noqa: E402, F401  - import after side-effect on purpose
    _viur_light_mock_reset_state,
    db_state,
    freeze_time,
    make_query,
    patched_user,
)


def pytest_configure(config) -> None:  # noqa: ARG001
    """Re-install the mocks at ``pytest_configure`` time.

    This is a belt-and-braces guard: even if something between plugin
    import and test collection trampled on ``sys.modules`` (an unusual
    ``conftest.py`` swapping things around, say), the mocks get a fresh
    re-installation here — again only when no real viur-core is present.
    """
    _install_mocks_unless_real_core()
