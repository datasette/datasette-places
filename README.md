# datasette-places

Experimental plugin for making maps of addresses in Datasette.

Create lists of places, drop them on a map, and share each list with people or
groups.

![A place list on a full-screen map with markers and a floating list panel](docs/screenshots/map.png)

The Places index lists every map you can see, with place counts:

![The Places index listing place lists](docs/screenshots/lists.png)

Click a marker for its details, or share a list with collaborators:

![A marker popup showing a place's address and directions link](docs/screenshots/popup.png)

![The share dialog showing per-person roles](docs/screenshots/share.png)

A place list can also be embedded as a block inside a
[datasette-paper](https://github.com/datasette/datasette-paper) document:

![A Places map embedded in a paper document](docs/screenshots/paper-embed.png)

## Development

### Screenshots

`docs/screenshots/*.png` are generated and committed. To regenerate them:

```bash
just shots              # all shots
just shots map share    # a subset, by name
```

This builds the production frontend, boots a throwaway Datasette (with the
`paper` extra, so the paper-embed shot works) with seeded demo data, and drives
headless Chromium to produce deterministic PNGs. Map tiles are fetched once and
cached under `frontend/scripts/shots/.tile-cache/` (gitignored); after the first
run the shots render offline. It is a manual local task (not run in CI) — re-run
and confirm `git status` shows no diff before committing. See
`frontend/scripts/` for the harness.
