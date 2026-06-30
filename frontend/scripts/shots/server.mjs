// Boot / tear down the throwaway datasette the screenshots run against.
//
// datasette is launched as a grandchild of `uv run`, so teardown kills the
// whole process group (a plain child.kill would orphan datasette holding the
// port). Refuses to start over an already-listening server rather than produce
// garbage shots against whatever is there.

import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";

import {
  PORT,
  PLACES,
  SECRET,
  INTERNAL_DB,
  DATA_DIR,
  DATA_DB,
  PLUGINS_DIR,
  sleep,
} from "./config.mjs";

// Is something already answering on our port? (status < 500 = "alive").
async function reachable() {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 500);
  try {
    const resp = await fetch(PLACES, { signal: ctrl.signal });
    return resp.status < 500;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

// Fresh, empty-but-valid mutable data.db so datasette opens it read-write.
function setupDataDb() {
  rmSync(DATA_DIR, { recursive: true, force: true });
  mkdirSync(DATA_DIR, { recursive: true });
  execFileSync("uv", [
    "run",
    "--prerelease=allow",
    "python",
    "-c",
    "import sqlite3, sys; sqlite3.connect(sys.argv[1]).close()",
    DATA_DB,
  ]);
}

export async function startServer() {
  if (await reachable()) {
    throw new Error(
      `Something is already serving on ${PORT}. Stop it first (the harness ` +
        `won't screenshot an unknown server).`,
    );
  }

  rmSync(INTERNAL_DB, { force: true });
  setupDataDb();

  const child = spawn(
    "uv",
    [
      "run",
      "--prerelease=allow",
      // `--extra paper` pulls in datasette-paper so the paper-embed shot can
      // create a doc that embeds a Places map. It owns the paper_embed_provider
      // spec, so places' hookimpl (paper.py) only fires when it's present.
      "--extra",
      "paper",
      "datasette",
      "--internal",
      INTERNAL_DB,
      DATA_DB,
      "--secret",
      SECRET,
      "--plugins-dir",
      PLUGINS_DIR,
      // Global gates so alice can reach the index + create lists. Per-list
      // view/edit/manage resolve through acl grants seeded by seed.mjs.
      "-s",
      "permissions.datasette-places-list",
      "true",
      "-s",
      "permissions.datasette-places-create",
      "true",
      // Paper: let alice create docs and view any doc (per-doc edit/manage
      // still derive from the owner grant the create endpoint seeds).
      "-s",
      "permissions.datasette-paper-create",
      "true",
      "-s",
      "permissions.paper-view",
      "true",
      "-p",
      String(PORT),
    ],
    {
      stdio: ["ignore", "pipe", "pipe"],
      detached: true, // own process group, so we can kill the whole tree
      // PYTHONHASHSEED=0 → any hash-derived ordering/colours stay stable.
      env: { ...process.env, PYTHONHASHSEED: "0" },
    },
  );

  let logs = "";
  child.stdout.on("data", (d) => (logs += d));
  child.stderr.on("data", (d) => (logs += d));

  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`datasette exited early (code ${child.exitCode}):\n${logs}`);
    }
    if (await reachable()) return child;
    await sleep(250);
  }
  throw new Error(`datasette did not become ready in 30s:\n${logs}`);
}

export function stopServer(child) {
  if (!child) return;
  try {
    process.kill(-child.pid, "SIGKILL"); // negative pid = process group
  } catch {
    try {
      child.kill("SIGKILL");
    } catch {
      /* already gone */
    }
  }
}
