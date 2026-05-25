"""Shared helpers for datasette-places route handlers."""

from __future__ import annotations

import json

from .db import PlacesDB


async def read_json_body(request) -> dict:
    """Parse the request body as JSON and return a dict."""
    return json.loads(await request.post_body())


def actor_id(request) -> str | None:
    """Return the actor id from the request, or None."""
    return str(request.actor.get("id")) if request.actor else None


def places_db(datasette) -> PlacesDB:
    """Return a PlacesDB wrapping Datasette's internal database."""
    return PlacesDB(datasette.get_internal_database())
