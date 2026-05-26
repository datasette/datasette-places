"""Shared pytest fixtures for datasette-places."""

from __future__ import annotations

import pytest_asyncio
from datasette.app import Datasette


DEFAULT_ACTOR_ID = "test-user"


def make_datasette(*, granted: bool = True) -> Datasette:
    config = (
        {
            "permissions": {
                "datasette-places-list": True,
                "datasette-places-create": True,
            }
        }
        if granted
        else {}
    )
    return Datasette(memory=True, config=config)


def _bind_default_actor(ds: Datasette, actor_id: str) -> None:
    """Monkey-patch ds.client.get/post to inject an actor cookie."""
    cookie = ds.sign({"a": {"id": actor_id}}, "actor")
    orig_get = ds.client.get
    orig_post = ds.client.post

    def _merge(kwargs):
        cookies = dict(kwargs.get("cookies") or {})
        cookies.setdefault("ds_actor", cookie)
        kwargs["cookies"] = cookies
        return kwargs

    async def _get(path, **kw):
        return await orig_get(path, **_merge(kw))

    async def _post(path, **kw):
        return await orig_post(path, **_merge(kw))

    ds.client.get = _get  # type: ignore[method-assign]
    ds.client.post = _post  # type: ignore[method-assign]


@pytest_asyncio.fixture
async def ds():
    """Datasette with default actor cookie bound."""
    instance = make_datasette()
    await instance.invoke_startup()
    _bind_default_actor(instance, DEFAULT_ACTOR_ID)
    return instance


@pytest_asyncio.fixture
async def ds_auth(ds):
    """Return datasette — actor cookie already bound by ds fixture."""
    return ds
