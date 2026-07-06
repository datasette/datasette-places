// Mint signed `ds_actor` cookies so seeded lists render with full owner/editor
// UI. There is no Node port of itsdangerous, so we shell out to the same
// `itsdangerous.URLSafeSerializer(...).dumps(payload, salt="actor")` datasette
// uses internally, via the project's `uv run python`. Cached per actor id.

import { execFileSync } from "node:child_process";

import { SECRET } from "./config.mjs";

const cache = new Map();

export function signActorCookie(actorId) {
  if (cache.has(actorId)) return cache.get(actorId);
  const value = execFileSync(
    "uv",
    [
      "run",
      "--prerelease=allow",
      "python",
      "-c",
      "import sys, json; from itsdangerous import URLSafeSerializer; " +
        'print(URLSafeSerializer(sys.argv[1]).dumps(json.loads(sys.argv[2]), salt="actor"))',
      SECRET,
      JSON.stringify({ a: { id: actorId } }),
    ],
    { encoding: "utf8" },
  ).trim();
  cache.set(actorId, value);
  return value;
}

// A Playwright cookie object for the given actor, scoped to localhost.
export function actorCookie(actorId) {
  return {
    name: "ds_actor",
    value: signActorCookie(actorId),
    domain: "localhost",
    path: "/",
  };
}
