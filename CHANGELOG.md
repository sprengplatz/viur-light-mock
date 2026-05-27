# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- PyPI distribution name is now **`spltz-viur-light-mock`** (the
  experimental `spltz-` prefix marks the package pre-1.0). The
  Python import path stays `viur.light_mock` — namespace package,
  no rename in user code. Consumers should update their
  `pyproject.toml`:

      test = ["pytest", "pytest-cov", "spltz-viur-light-mock>=0.1"]

## [0.1.0] - 2026-05-20

### Added

- Initial release, extracted from the `viur-revision` test harness.
- Pytest plugin (`pytest11` entry-point `viur_light_mock`) that auto-loads
  before test collection.
- `install_viur_core_mocks()` for explicit setup outside of pytest.
- Fake modules: `viur.core.db`, `viur.core.utils`, `viur.core.errors`,
  `viur.core.current`, `viur.core.skeleton`, `viur.core.tasks`,
  `viur.core.render.json.default`.
- Identity decorators for `viur.core.exposed`, `viur.core.force_post`,
  `viur.core.skey`.
- Data types: `FakeKey`, `FakeEntity`, `FakeQuery`, `FakeSortOrder`, `DbState`.
- Pytest fixtures: `db_state`, `freeze_time`, `make_query`, `patched_user`,
  plus an autouse state reset.

[Unreleased]: https://github.com/sprengplatz/viur-light-mock/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sprengplatz/viur-light-mock/releases/tag/v0.1.0
