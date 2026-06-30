"""Provider-agnostic geocoding interface.

A :class:`GeocodeProvider` turns a query into a list of :class:`Candidate`
results. Concrete providers (OpenCage, pluto, third-party) implement
``geocode`` (forward) and optionally ``reverse``. Routes resolve a provider
from a configured geocoder instance and serialize the candidates — they never
talk to a provider's transport directly.

``GeocodingError`` carries a user-safe ``message`` plus the HTTP ``status`` the
API route should return; it lives here (rather than in any one provider) so it
is the shared error contract across providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class GeocodingError(Exception):
    """An upstream geocoding request failed.

    ``message`` is human-readable and safe to show in the UI; ``status`` is the
    HTTP status the API route should return to the client.
    """

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class Candidate:
    """A single geocoding result, normalized across providers.

    ``score`` is normalized to ``0..1`` (higher = better) for cross-provider
    ranking, or ``None`` when the provider exposes no confidence.
    """

    latitude: float
    longitude: float
    label: str
    score: Optional[float] = None
    components: dict = field(default_factory=dict)

    def to_result(self) -> dict:
        """The JSON shape the frontend (AddressSearch / MapView) consumes.

        ``display_name`` is the historical field name for the formatted label,
        kept stable so existing frontend code keeps working.
        """
        return {
            "display_name": self.label,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "components": self.components or {},
        }


class GeocodeProvider(ABC):
    """Forward/reverse geocoding for one configured geocoder.

    Subclasses set ``type`` (the provider-type slug used in instance config and
    the registry) and implement :meth:`geocode`. ``supports_reverse`` advertises
    whether :meth:`reverse` is implemented; the default raises so callers get a
    clean 501 rather than an attribute error.
    """

    type: str = ""
    supports_reverse: bool = True

    @abstractmethod
    async def geocode(self, query: str, *, limit: int = 5) -> list[Candidate]:
        """Forward geocode: free-text query → ranked candidates."""

    async def reverse(self, lat: float, lon: float) -> list[Candidate]:
        """Reverse geocode: lat/lon → candidates (nearest first)."""
        raise GeocodingError("Reverse geocoding is not supported.", status=501)
