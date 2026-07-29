"""Guards on the premise of this whole test root: viur-core is REAL here.

If these fail, every other test in ``tests_overlay/`` is worthless — it would be
asserting against the stand-ins from :mod:`viur.light_mock.modules`, which have
no ``Query`` class at all. That is exactly how a missing seam went unnoticed
before: the fake ``db`` module only carries ``Get``/``Put``/``Delete``, so no
test could reach the code path that needed the patch.
"""


def test_viur_core_db_is_the_real_package_not_our_stand_in():
    import viur.core.db as db

    assert db.__file__.endswith("viur/core/db/__init__.py")
    assert "light_mock" not in db.__file__


def test_query_class_exposes_the_seams_the_overlay_patches():
    """The overlay hangs off these three. A viur rename must fail loudly here,
    not silently downstream."""
    import viur.core.db as db

    assert hasattr(db.Query, "_run_single_filter_query")
    assert hasattr(db.Query, "_resort_result")
    assert hasattr(db.Query, "_merge_multi_query_results")


def test_query_module_exposes_the_filter_matcher_we_reuse():
    import viur.core.db.query as query

    assert callable(query._entryMatchesQuery)


def test_datastore_client_was_built_without_real_credentials():
    """Belt and braces: the client exists (viur needs it for ``Key.__init__``)
    but carries anonymous credentials, so it cannot authenticate anywhere."""
    from google.auth.credentials import AnonymousCredentials
    import viur.core.db.transport as transport

    assert isinstance(transport.__client__._credentials, AnonymousCredentials)
