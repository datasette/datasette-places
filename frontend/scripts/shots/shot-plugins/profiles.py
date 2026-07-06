"""Dev-only Datasette plugin for the screenshot harness (loaded via --plugins-dir).

Maps the demo actor ids used by seed.mjs to friendly display names so the UI —
the share dialog in particular — renders "Alice Ada" instead of a bare id. Not
shipped with the plugin; only the screenshot run loads it.
"""

from datasette import hookimpl

# datasette-acl-share's dialog reads the `display_name` field of the
# actors_from_ids record (not `name`), so emit that.
_NAMES = {
    "alice": {"id": "alice", "display_name": "Alice Ada", "username": "alice"},
    "bob": {"id": "bob", "display_name": "Bob Stone", "username": "bob"},
}


@hookimpl
def actors_from_ids(datasette, actor_ids):
    return {aid: _NAMES.get(aid, {"id": aid}) for aid in actor_ids}
