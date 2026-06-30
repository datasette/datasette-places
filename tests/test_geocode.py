"""Tests for the geocoding proxy routes + the provider abstraction.

OpenCage HTTP is mocked with ``httpx.MockTransport`` (no network, no extra
deps), exercising the real request-building + response-parsing path through
``OpenCageProvider`` and the ``/api/geocode`` / ``/api/reverse`` routes.
"""

from __future__ import annotations

import httpx
import pytest
from datasette.app import Datasette


def _ds(*, with_key: bool = True, base_url: str | None = None) -> Datasette:
    plugins: dict = {}
    if with_key:
        plugins["opencage_api_key"] = "test-key"
    if base_url:
        plugins["opencage_base_url"] = base_url
    config = {
        "permissions": {
            "datasette-places-list": True,
            "datasette-places-create": True,
        }
    }
    if plugins:
        config["plugins"] = {"datasette-places": plugins}
    return Datasette(memory=True, config=config)


def _install_mock(monkeypatch, handler) -> list[httpx.Request]:
    """Route OpenCage's httpx client through a MockTransport. Returns a list
    that captures each outgoing request for assertions."""
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(_handler)

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport)

    monkeypatch.setattr("datasette_places.geocoders.opencage._make_client", factory)
    return seen


def _result(formatted, lat, lng, *, confidence=9, components=None):
    return {
        "formatted": formatted,
        "geometry": {"lat": lat, "lng": lng},
        "confidence": confidence,
        "components": components or {},
    }


def _ok(results):
    return httpx.Response(200, json={"results": results, "status": {"code": 200}})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_geocode_not_configured_returns_503(monkeypatch):
    ds = _ds(with_key=False)
    await ds.invoke_startup()
    r = await ds.client.get("/-/places/api/geocode?q=anywhere")
    assert r.status_code == 503
    assert "not configured" in r.json()["error"]


@pytest.mark.asyncio
async def test_geocode_requires_query(monkeypatch):
    ds = _ds()
    await ds.invoke_startup()
    r = await ds.client.get("/-/places/api/geocode?q=%20%20")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_geocode_happy_path(monkeypatch):
    ds = _ds()
    await ds.invoke_startup()
    seen = _install_mock(
        monkeypatch,
        lambda req: _ok(
            [
                _result(
                    "1 Main St, Whittier",
                    33.97,
                    -118.03,
                    components={"city": "Whittier"},
                ),
                _result("2 Main St, Whittier", 33.98, -118.04),
            ]
        ),
    )
    r = await ds.client.get("/-/places/api/geocode?q=main+st")
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 2
    first = results[0]
    assert first == {
        "display_name": "1 Main St, Whittier",
        "latitude": 33.97,
        "longitude": -118.03,
        "components": {"city": "Whittier"},
    }
    # The outgoing request carried our key + query, default limit 5.
    params = dict(httpx.QueryParams(seen[0].url.query.decode()))
    assert params["key"] == "test-key"
    assert params["q"] == "main st"
    assert params["limit"] == "5"


@pytest.mark.asyncio
async def test_geocode_upstream_error_maps_message(monkeypatch):
    ds = _ds()
    await ds.invoke_startup()
    _install_mock(
        monkeypatch,
        lambda req: httpx.Response(
            401, json={"status": {"code": 401, "message": "invalid key"}}
        ),
    )
    r = await ds.client.get("/-/places/api/geocode?q=x")
    assert r.status_code == 502
    assert "not authorized" in r.json()["error"]


@pytest.mark.asyncio
async def test_reverse_happy_path(monkeypatch):
    ds = _ds()
    await ds.invoke_startup()
    seen = _install_mock(
        monkeypatch,
        lambda req: _ok([_result("Pier, Whittier", 33.9, -118.0)]),
    )
    r = await ds.client.get("/-/places/api/reverse?lat=33.9&lon=-118.0")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "display_name": "Pier, Whittier",
        "latitude": 33.9,
        "longitude": -118.0,
        "components": {},
    }
    # Reverse sends "lat,lng" as q with limit 1.
    params = dict(httpx.QueryParams(seen[0].url.query.decode()))
    assert params["q"] == "33.9,-118.0"
    assert params["limit"] == "1"


@pytest.mark.asyncio
async def test_reverse_no_results_returns_404(monkeypatch):
    ds = _ds()
    await ds.invoke_startup()
    _install_mock(monkeypatch, lambda req: _ok([]))
    r = await ds.client.get("/-/places/api/reverse?lat=0&lon=0")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_reverse_bad_coords_returns_400(monkeypatch):
    ds = _ds()
    await ds.invoke_startup()
    r = await ds.client.get("/-/places/api/reverse?lat=abc&lon=xyz")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_base_url_override_used(monkeypatch):
    ds = _ds(base_url="https://example.test/geocode")
    await ds.invoke_startup()
    seen = _install_mock(monkeypatch, lambda req: _ok([_result("X", 1.0, 2.0)]))
    r = await ds.client.get("/-/places/api/geocode?q=x")
    assert r.status_code == 200
    assert str(seen[0].url).startswith("https://example.test/geocode")


# ---------------------------------------------------------------------------
# Provider + back-compat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_returns_candidates_with_score(monkeypatch):
    from datasette_places.geocoders import OpenCageProvider

    _install_mock(monkeypatch, lambda req: _ok([_result("X", 1.0, 2.0, confidence=8)]))
    provider = OpenCageProvider("k")
    cands = await provider.geocode("x")
    assert len(cands) == 1
    c = cands[0]
    assert (c.latitude, c.longitude, c.label) == (1.0, 2.0, "X")
    assert c.score == pytest.approx(0.8)  # confidence 8/10


@pytest.mark.asyncio
async def test_legacy_geocoding_module_still_works(monkeypatch):
    from datasette_places.geocoding import geocode_search, reverse_geocode

    _install_mock(monkeypatch, lambda req: _ok([_result("Y", 3.0, 4.0)]))
    rows = await geocode_search("y", "k")
    assert rows == [
        {"display_name": "Y", "latitude": 3.0, "longitude": 4.0, "components": {}}
    ]
    one = await reverse_geocode(3.0, 4.0, "k")
    assert one["display_name"] == "Y"


def test_geocoding_module_reexports_error_class():
    # GeocodingError must be the same class whether imported from the shim or
    # the new package, so isinstance checks in routes keep working.
    from datasette_places.geocoding import GeocodingError as ShimError
    from datasette_places.geocoders.base import GeocodingError as BaseError

    assert ShimError is BaseError
