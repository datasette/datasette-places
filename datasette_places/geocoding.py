"""Back-compat shim.

Geocoding moved to the :mod:`datasette_places.geocoders` package. This module
re-exports the historical public names so existing imports keep working.
"""

from __future__ import annotations

from .geocoders.base import GeocodingError  # noqa: F401
from .geocoders.opencage import (  # noqa: F401
    DEFAULT_OPENCAGE_API_URL,
    geocode_search,
    reverse_geocode,
)

__all__ = [
    "GeocodingError",
    "DEFAULT_OPENCAGE_API_URL",
    "geocode_search",
    "reverse_geocode",
]
