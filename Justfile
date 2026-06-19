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

# `just dev` loads datasette-acl + datasette-acl-share + datasette-debug-gotham
# (the latter pulls in datasette-user-profiles, lighting up People-search in the
# share dialog). Use the gotham user-switcher to "log in" as a demo actor —
# Clark / Lois / Jimmy (daily-planet) and Bruce / Alfred / Selina
# (gotham-gazette) — then create a list (creator gets the Manager grant) and
# open the share dialog to grant other actors / the gotham groups / the
# authenticated + everyone public audiences. `--root` keeps an admin escape
# hatch. The two dynamic-groups map each newsroom to an acl group so
# group-based sharing is testable too.
dev *flags:
  DATASETTE_SECRET=abc123 uv run --prerelease=allow \
        datasette \
            --root \
            --internal {{INTERNAL_DEV_DB}} \
            -s permissions.datasette-places-list true \
            -s permissions.datasette-places-create true \
            -s plugins.datasette-acl.dynamic-groups.daily-planet.newsroom daily-planet \
            -s plugins.datasette-acl.dynamic-groups.gotham-gazette.newsroom gotham-gazette \
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
