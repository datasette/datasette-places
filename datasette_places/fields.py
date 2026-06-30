"""User-defined per-list metadata fields: key rules + type registry + validation.

This module is the single source of truth for:

* the **key whitelist** and **reserved keys** — a field ``key`` is both a JSON
  path segment in ``_datasette_places_place.metadata_json`` and a column name in
  the per-list expanded view (``db.rebuild_list_artifacts``). That view/index DDL
  is string-interpolated and CANNOT be parameterized, so an unvalidated key is a
  SQL-injection vector. Every code path that accepts a key calls
  :func:`validate_key` before the key reaches SQL.
* the **field types** and their value validators, used by the place routes to
  reject bad ``metadata`` values before they are written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlparse

# A field key must be a safe SQL identifier / JSON path segment.
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# Keys that collide with real place columns or the live marker attribute
# (``metadata.shape``). User fields may not use these.
RESERVED_KEYS = frozenset(
    {
        "id",
        "list_id",
        "name",
        "address",
        "latitude",
        "longitude",
        "notes",
        "color",
        "metadata_json",
        "created_by",
        "created_at",
        "updated_at",
        "shape",
    }
)

# Base columns the expanded view always selects (fixed literal list — never
# built from user input).
BASE_VIEW_COLUMNS = (
    "id",
    "name",
    "address",
    "latitude",
    "longitude",
    "color",
    "notes",
)


class FieldError(ValueError):
    """Raised for an invalid field definition (bad key, unknown type, …)."""


def validate_key(key: Any) -> str:
    """Return *key* if it is a legal, non-reserved field key, else raise."""
    if not isinstance(key, str) or not KEY_RE.match(key):
        raise FieldError(
            "key must match ^[a-z][a-z0-9_]{0,62}$ (lowercase letter, then "
            "letters/digits/underscores)"
        )
    if key in RESERVED_KEYS:
        raise FieldError(f"key '{key}' is reserved")
    return key


# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldType:
    name: str
    # validate(value, config) -> normalized value, or raise ValueError.
    validate: Callable[[Any, dict], Any]


def _v_text(value: Any, config: dict) -> Any:
    if not isinstance(value, str):
        raise ValueError("expected a string")
    maxlen = config.get("maxlength")
    if isinstance(maxlen, int) and len(value) > maxlen:
        raise ValueError(f"must be at most {maxlen} characters")
    return value


def _as_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a number")
    return float(value)


def _v_number(value: Any, config: dict) -> Any:
    n = _as_number(value)
    lo, hi = config.get("min"), config.get("max")
    if isinstance(lo, (int, float)) and n < lo:
        raise ValueError(f"must be ≥ {lo}")
    if isinstance(hi, (int, float)) and n > hi:
        raise ValueError(f"must be ≤ {hi}")
    return value


def _v_rating(value: Any, config: dict) -> Any:
    n = _as_number(value)
    hi = config.get("max", 5)
    if n < 0 or n > hi:
        raise ValueError(f"rating must be between 0 and {hi}")
    return value


def _v_url(value: Any, config: dict) -> Any:
    if not isinstance(value, str):
        raise ValueError("expected a URL string")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be an http(s) URL")
    return value


def _v_select(value: Any, config: dict) -> Any:
    options = config.get("options") or []
    allowed = {o.get("value") for o in options if isinstance(o, dict)}
    if config.get("multiple"):
        if not isinstance(value, list):
            raise ValueError("expected a list of option values")
        for v in value:
            if v not in allowed:
                raise ValueError(f"'{v}' is not an allowed option")
        return value
    if value not in allowed:
        raise ValueError(f"'{value}' is not an allowed option")
    return value


_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _v_color(value: Any, config: dict) -> Any:
    if not isinstance(value, str) or not _HEX_RE.match(value):
        raise ValueError("expected a hex color like #3b82f6")
    return value


def _v_icon(value: Any, config: dict) -> Any:
    if not isinstance(value, str) or not value:
        raise ValueError("expected an icon name")
    return value


def _v_boolean(value: Any, config: dict) -> Any:
    if not isinstance(value, bool):
        raise ValueError("expected true or false")
    return value


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _v_date(value: Any, config: dict) -> Any:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError("expected an ISO date (YYYY-MM-DD)")
    return value


FIELD_TYPES: dict[str, FieldType] = {
    ft.name: ft
    for ft in (
        FieldType("text", _v_text),
        FieldType("number", _v_number),
        FieldType("url", _v_url),
        FieldType("rating", _v_rating),
        FieldType("select", _v_select),
        FieldType("color", _v_color),
        FieldType("icon", _v_icon),
        FieldType("boolean", _v_boolean),
        FieldType("date", _v_date),
    )
}

KNOWN_TYPES = frozenset(FIELD_TYPES)


def validate_type(type_: Any) -> str:
    if type_ not in FIELD_TYPES:
        raise FieldError(
            f"unknown field type '{type_}' (expected one of {', '.join(sorted(KNOWN_TYPES))})"
        )
    return type_


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_metadata(
    values: Optional[dict], fields: list
) -> tuple[dict, dict[str, str]]:
    """Validate a place's ``metadata`` dict against a list's field defs.

    *fields* is a list of ``ListField`` (or any object exposing
    ``key``/``type``/``required``/``config_json``). Returns ``(clean, errors)``:
    declared keys are validated/normalized; ``required`` declared keys must be
    present; reserved keys (e.g. the marker ``shape``) and any **undeclared**
    keys pass through untouched (metadata stays free-form for back-compat — only
    declared fields are enforced, and only declared keys surface in the expanded
    view). ``errors`` maps field key → message; a non-empty ``errors`` is a 400.
    """
    import json as _json

    values = values or {}
    errors: dict[str, str] = {}
    clean: dict[str, Any] = dict(values)  # start from a pass-through copy

    for f in fields:
        present = f.key in values and not _is_empty(values.get(f.key))
        if not present:
            if getattr(f, "required", 0):
                errors[f.key] = "this field is required"
            continue
        try:
            config = _json.loads(f.config_json) if f.config_json else {}
        except (TypeError, ValueError):
            config = {}
        ftype = FIELD_TYPES.get(f.type)
        if ftype is None:
            errors[f.key] = f"unknown field type '{f.type}'"
            continue
        try:
            clean[f.key] = ftype.validate(values[f.key], config)
        except ValueError as exc:
            errors[f.key] = str(exc)

    return clean, errors
