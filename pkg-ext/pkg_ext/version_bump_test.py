from pkg_ext.conftest import TEST_PKG_NAME
from pkg_ext.models import PkgCodeState, PkgExtState, pkg_ctx
from pkg_ext.version_bump import PkgVersion, bump_or_get_version


def test_bump_or_get_version_default(settings):
    ctx = pkg_ctx(
        settings,
        PkgExtState.parse(settings),
        PkgCodeState.model_construct(
            pkg_import_name=TEST_PKG_NAME, import_id_refs={}, files=[]
        ),
    )
    assert bump_or_get_version(ctx) == PkgVersion.default()
