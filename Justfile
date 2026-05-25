DEV_PORT := "5176"
INTERNAL_DEV_DB := "/tmp/datasette-places-dev-internal.db"

# --- Frontend build & dev ---

frontend *flags:
    npm run build --prefix frontend {{flags}}

frontend-dev *flags:
    npm run dev --prefix frontend -- --port {{DEV_PORT}} {{flags}}

# --- Formatting ---

format-backend *flags:
    uv run --prerelease=allow ruff format {{flags}}

format-backend-check *flags:
    uv run --prerelease=allow ruff format --check {{flags}}

format:
    just format-backend

format-check:
    just format-backend-check

# --- Type / static checks ---

check-backend:
    uv run --prerelease=allow ruff check

check:
    just check-backend

# --- API types ---

types-routes:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp=$(mktemp)
    trap "rm -f $tmp" EXIT
    uv run --prerelease=allow python -c \
        'from datasette_places.router import router; import datasette_places.routes; import json; print(json.dumps(router.openapi_document_json()))' \
        > "$tmp"
    npx --prefix frontend openapi-typescript "$tmp" > frontend/api.d.ts

types:
    just types-routes

# --- Tests ---

test *flags:
    uv run --prerelease=allow pytest {{flags}}

# --- Dev server ---

dev *flags:
  DATASETTE_SECRET=abc123 uv run --prerelease=allow \
        datasette \
            --internal {{INTERNAL_DEV_DB}} \
            -s permissions.datasette-places-list true \
            -s permissions.datasette-places-create true \
            {{flags}}

dev-with-hmr *flags:
    watchexec \
        --stop-signal SIGKILL \
        -e py,html \
        --ignore '*.db' \
        --restart \
        --clear -- \
        just dev \
            -s plugins.datasette-vite.dev_paths.datasette_places "http://localhost:{{DEV_PORT}}/-/static-plugins/datasette_places/" \
            {{flags}}

# Wipe the dev internal DB
clean-dev-db:
    rm -f {{INTERNAL_DEV_DB}}
