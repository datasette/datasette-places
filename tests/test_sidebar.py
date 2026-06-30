import pytest

# datasette-sidebar is an optional integration; skip if it isn't installed in
# the places venv.
pytest.importorskip("datasette_sidebar")

from datasette_places import datasette_sidebar_apps


def test_sidebar_app_registered():
    apps = datasette_sidebar_apps(datasette=None)
    assert len(apps) == 1
    app = apps[0]
    assert app.label == "Places"
    assert app.resolve_href() == "/-/places/"
    assert app.color == "#276890"
    assert "<svg" in app.icon
    assert app.description
