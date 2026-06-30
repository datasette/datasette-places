// Seed deterministic demo data over HTTP, after the server is confirmed up.
//
// Done via the real places API (not direct DB writes) so it exercises the
// genuine create path — creating a list auto-grants its creator the acl
// Manager role, exactly as in production. Places carry explicit lat/lng, so no
// geocoding network call happens. A final acl grant shares the primary list
// with `bob` so the share dialog shows a real collaborator.

import { signActorCookie } from "./cookie.mjs";
import { BASE, PLACES, OWNER, COLLABORATOR } from "./config.mjs";

async function api(path, { actor, method = "POST", body } = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Cookie: `ds_actor=${signActorCookie(actor)}`,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`${method} ${path} → ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

async function createList(name, places) {
  const { id } = await api(`/-/places/api/lists`, {
    actor: OWNER,
    body: { name },
  });
  for (const p of places) {
    await api(`/-/places/api/lists/${id}/places`, { actor: OWNER, body: p });
  }
  return id;
}

// A walkable downtown-Portland coffee crawl — markers cluster nicely at city
// zoom.
const COFFEE = [
  { name: "Heart Coffee Roasters", latitude: 45.5226, longitude: -122.6587, color: "#b5651d", address: "2211 E Burnside St, Portland, OR" },
  { name: "Coava Coffee", latitude: 45.5152, longitude: -122.6566, color: "#6f4e37", address: "1300 SE Grand Ave, Portland, OR" },
  { name: "Stumptown HQ", latitude: 45.5121, longitude: -122.6543, color: "#3b2f2f", address: "100 SE Salmon St, Portland, OR" },
  { name: "Never Coffee", latitude: 45.5108, longitude: -122.6186, color: "#d27d2d", address: "4243 SE Belmont St, Portland, OR" },
  { name: "Good Coffee", latitude: 45.5189, longitude: -122.6411, color: "#a0522d", address: "4747 SE Division St, Portland, OR" },
  { name: "Either/Or", latitude: 45.4742, longitude: -122.6312, color: "#8b5a2b", address: "8235 SE 13th Ave, Portland, OR" },
];

const HIKES = [
  { name: "Forest Park – Wildwood", latitude: 45.5466, longitude: -122.7547, color: "#2e7d32" },
  { name: "Mount Tabor", latitude: 45.5113, longitude: -122.5949, color: "#388e3c" },
  { name: "Powell Butte", latitude: 45.4882, longitude: -122.4977, color: "#43a047" },
];

// Create a paper document that embeds a Places map. Block embeds are a fenced
// ```paper-embed code block whose body is {config, mode, ref}; paper renders
// the block via the provider that owns the ref's prefix (places, here),
// mounting our <datasette-places-map>. content_type defaults to markdown.
async function createPaperDoc(listId) {
  const block = JSON.stringify({
    config: {},
    mode: "block",
    ref: `/-/places/list/${listId}`,
  });
  const content = "# Portland Coffee Tour\n\nMy favourite roasters, on a map:\n\n```paper-embed\n" + block + "\n```\n";
  const { id } = await api(`/-/paper/api/docs`, {
    actor: OWNER,
    body: { name: "Portland Coffee Tour", content },
  });
  return id;
}

export async function seed() {
  const primaryList = await createList("Portland Coffee Tour", COFFEE);
  const secondaryList = await createList("Weekend Hikes", HIKES);

  // Share the primary list with bob (Editor) for the share-dialog shot.
  await api(`/-/acl/api/resource/places-list/${primaryList}/grant`, {
    actor: OWNER,
    body: { actor_id: COLLABORATOR, role: "Editor" },
  });

  // A paper doc embedding the primary list, for the paper-embed shot.
  const paperDoc = await createPaperDoc(primaryList);

  return { primaryList, secondaryList, paperDoc };
}
