"""Plugin hooks defined by datasette-places.

``register_places_geocoder_providers`` lets any plugin contribute geocoder
*provider types* (the code that builds a
:class:`~datasette_places.geocoders.base.GeocodeProvider` from a stored geocoder
instance). datasette-places registers its own built-ins (``opencage``,
``pluto``) through this same hook; third parties add more.
"""

from pluggy import HookspecMarker

hookspec = HookspecMarker("datasette")


@hookspec
def register_places_geocoder_providers(datasette):
    """Return a mapping of ``provider_type`` → factory.

    A factory is ``callable(datasette, config: dict) -> GeocodeProvider | None``
    where ``config`` is the geocoder instance's parsed ``config_json`` (non-secret;
    secrets are resolved by the factory from plugin config by reference). Return a
    plain dict, or a (optionally awaitable) callable returning one.
    """
