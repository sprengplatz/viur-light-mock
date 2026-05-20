"""
Pytest entry-point for viur-light-mock.

Registered via ``[project.entry-points.pytest11]`` so pytest discovers and
loads this module before any test files are imported. Two responsibilities:

1. Install the fake ``viur.core.*`` modules into :data:`sys.modules` at
   plugin-load time (so production-code imports succeed during collection).
2. Re-export the fixtures from :mod:`viur.light_mock.fixtures` so pytest finds
   them when scanning this plugin module.
"""
from __future__ import annotations

from .modules import install_viur_core_mocks

# Install on plugin import. pytest loads this module via the ``pytest11``
# entry-point before any test file is collected, so this side-effect lands
# in ``sys.modules`` early enough for production imports inside the host
# package to resolve to the stand-ins.
install_viur_core_mocks()

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
    re-installation here.
    """
    install_viur_core_mocks()
