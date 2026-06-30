"""Geocoder provider registry.

A *provider type* (``opencage``, ``pluto``, …) is code that builds a
:class:`GeocodeProvider` from a geocoder instance's non-secret config plus
secrets resolved from plugin config. Provider types are contributed through the
``register_places_geocoder_providers`` hook (datasette-places registers its own
built-ins through it); this module collects them and resolves a stored instance
into a live provider.
"""

from __future__ import annotations

import json

from datasette.plugins import pm
from datasette.utils import await_me_maybe

from .base import Candidate, GeocodeProvider, GeocodingError
from .opencage import DEFAULT_OPENCAGE_API_URL, OpenCageProvider

__all__ = [
    "Candidate",
    "GeocodeProvider",
    "GeocodingError",
    "OpenCageProvider",
    "DEFAULT_OPENCAGE_API_URL",
    "provider_factories",
    "resolve_provider",
    "opencage_from_config",
    "default_provider",
]


async def provider_factories(datasette) -> dict:
    """Collect ``{provider_type: factory}`` from every plugin via the hook."""
    factories: dict = {}
    for result in pm.hook.register_places_geocoder_providers(datasette=datasette):
        result = await await_me_maybe(result)
        if result:
            factories.update(result)
    return factories


async def resolve_provider(datasette, geocoder) -> GeocodeProvider | None:
    """Build a live provider from a stored geocoder instance (a ``Geocoder`` row).

    Returns ``None`` when the provider type is unknown or the factory cannot
    build (e.g. an unresolved API key). The caller maps ``None`` to a "geocoder
    unavailable" response.
    """
    factories = await provider_factories(datasette)
    factory = factories.get(geocoder.provider_type)
    if factory is None:
        return None
    try:
        config = json.loads(geocoder.config_json or "{}")
    except (TypeError, ValueError):
        config = {}
    return await await_me_maybe(factory(datasette, config))


def opencage_from_config(datasette) -> OpenCageProvider | None:
    """Build an :class:`OpenCageProvider` straight from plugin config, or ``None``.

    The legacy single-key path: reads ``plugins.datasette-places.opencage_api_key``
    (required) and ``opencage_base_url`` (optional).
    """
    config = datasette.plugin_config("datasette-places") or {}
    api_key = config.get("opencage_api_key")
    if not api_key:
        return None
    base_url = config.get("opencage_base_url") or DEFAULT_OPENCAGE_API_URL
    return OpenCageProvider(api_key, base_url)


def default_provider(datasette) -> GeocodeProvider | None:
    """The geocoder used when a request names no instance and the list has no
    default — the config-driven OpenCage provider (legacy behavior)."""
    return opencage_from_config(datasette)
