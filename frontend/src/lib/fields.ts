// Shared types + helpers for user-defined per-list metadata fields. The list
// detail payload carries a `fields` array (see routes/lists.py); each field
// drives a widget in the place editor and a column in the table view.

export type FieldOption = { value: string; label: string; color?: string };

export type FieldConfig = {
  // text
  maxlength?: number;
  multiline?: boolean;
  // number
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  // url
  icon?: string;
  // select
  options?: FieldOption[];
  multiple?: boolean;
  // icon
  set?: string;
};

export type FieldType =
  | "text"
  | "number"
  | "url"
  | "rating"
  | "select"
  | "color"
  | "icon"
  | "boolean"
  | "date";

export type Field = {
  id: number;
  list_id: number;
  key: string;
  label: string;
  type: FieldType;
  position: number;
  required: boolean;
  unique: boolean;
  config: FieldConfig;
};

// Stored metadata values are scalars (string / number / bool) or, for a
// `multiple` select, an array of option values.
export type MetaValue = string | number | boolean | string[] | null | undefined;

export const FIELD_TYPES: { value: FieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "url", label: "URL" },
  { value: "rating", label: "Rating (stars)" },
  { value: "select", label: "Select (dropdown)" },
  { value: "color", label: "Color" },
  { value: "icon", label: "Icon" },
  { value: "boolean", label: "Yes / No" },
  { value: "date", label: "Date" },
];

// Keys reserved by the backend (real columns + the marker `shape`). Mirrors
// fields.py RESERVED_KEYS so the panel can reject them before the round-trip.
export const RESERVED_KEYS = new Set([
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
]);

export const KEY_RE = /^[a-z][a-z0-9_]{0,62}$/;

/** Fields in display/column order (position, then id as a tiebreaker). */
export function sortedFields(fields: Field[]): Field[] {
  return [...fields].sort((a, b) => a.position - b.position || a.id - b.id);
}

export function ratingMax(field: Field): number {
  const m = Number(field.config?.max);
  return Number.isFinite(m) && m > 0 ? m : 5;
}

export function selectOption(
  field: Field,
  value: MetaValue
): FieldOption | undefined {
  return (field.config?.options ?? []).find((o) => o.value === value);
}

/** Derive a candidate key from a label, e.g. "Star Rating" -> "star_rating". */
export function keyFromLabel(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^([0-9])/, "_$1")
    .slice(0, 63);
}

export function formatDate(value: string): string {
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// --- Rating stars (Bootstrap Icons, with half-star support) ----------------

export type StarState = "full" | "half" | "empty";

const STAR_PATHS: Record<StarState, string> = {
  full: "M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256z",
  half: "M5.354 5.119 7.538.792A.52.52 0 0 1 8 .5c.183 0 .366.097.465.292l2.184 4.327 4.898.696A.54.54 0 0 1 16 6.32a.55.55 0 0 1-.17.445l-3.523 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256a.5.5 0 0 1-.146.05c-.342.06-.668-.254-.6-.642l.83-4.73L.173 6.765a.55.55 0 0 1-.172-.403.6.6 0 0 1 .085-.302.51.51 0 0 1 .37-.245zM8 12.027a.5.5 0 0 1 .232.056l3.686 1.894-.694-3.957a.56.56 0 0 1 .162-.505l2.907-2.77-4.052-.576a.53.53 0 0 1-.393-.288L8.001 2.223 8 2.226z",
  empty: "M2.866 14.85c-.078.444.36.791.746.593l4.39-2.256 4.389 2.256c.386.198.824-.149.746-.592l-.83-4.73 3.522-3.356c.33-.314.16-.888-.282-.95l-4.898-.696L8.465.792a.513.513 0 0 0-.927 0L5.354 5.12l-4.898.696c-.441.062-.612.636-.283.95l3.523 3.356-.83 4.73zm4.905-2.767-3.686 1.894.694-3.957a.56.56 0 0 0-.163-.505L1.71 6.745l4.052-.576a.53.53 0 0 0 .393-.288L8 2.223l1.847 3.658a.53.53 0 0 0 .393.288l4.052.575-2.906 2.77a.56.56 0 0 0-.163.506l.694 3.957-3.686-1.894a.5.5 0 0 0-.461 0z",
};

/** One state per star: full / half / empty, for a value out of `max`. */
export function ratingStates(value: number, max: number): StarState[] {
  const out: StarState[] = [];
  for (let i = 0; i < max; i++) {
    if (value >= i + 1) out.push("full");
    else if (value >= i + 0.5) out.push("half");
    else out.push("empty");
  }
  return out;
}

/** Inline Bootstrap-Icons star SVG (sized in em so it scales with font-size). */
export function starSvg(state: StarState): string {
  return `<svg width="1em" height="1em" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="${STAR_PATHS[state]}"/></svg>`;
}

export function isEmptyValue(value: MetaValue): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  );
}

function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Render a field value as an HTML string for the Leaflet marker popup, which is
 * built as raw HTML and so can't mount the `FieldValue` Svelte component. Mirrors
 * `FieldValue.svelte`; values are escaped (and `url` is scheme-guarded) since the
 * result is injected as innerHTML. Returns "" for an empty value.
 */
export function fieldValueHtml(field: Field, value: MetaValue): string {
  if (isEmptyValue(value)) return "";
  switch (field.type) {
    case "rating": {
      const max = ratingMax(field);
      const stars = ratingStates(Number(value) || 0, max)
        .map((st) => `<span class="ppf-star ${st}">${starSvg(st)}</span>`)
        .join("");
      return `<span class="ppf-stars" title="${escHtml(String(value))} / ${max}">${stars}</span>`;
    }
    case "select": {
      const opts = field.config?.options ?? [];
      const chip = (v: string) => {
        const o = opts.find((x) => x.value === v);
        const style = o?.color
          ? ` style="background:${escHtml(o.color)};color:#fff"`
          : "";
        return `<span class="ppf-chip"${style}>${escHtml(o?.label ?? v)}</span>`;
      };
      if (field.config?.multiple && Array.isArray(value)) {
        return `<span class="ppf-chips">${value.map((v) => chip(String(v))).join("")}</span>`;
      }
      return chip(String(value));
    }
    case "url": {
      const raw = String(value);
      const label = field.config?.icon ? `${escHtml(field.config.icon)} ↗` : "Link ↗";
      // Only emit an anchor for http(s); anything else renders as plain text.
      return /^https?:\/\//i.test(raw)
        ? `<a class="ppf-link" href="${escHtml(raw)}" target="_blank" rel="noopener">${label}</a>`
        : escHtml(raw);
    }
    case "color":
      return `<span class="ppf-color"><span class="ppf-swatch" style="background:${escHtml(String(value))}"></span>${escHtml(String(value))}</span>`;
    case "icon":
      return `<span class="ppf-icon"><i class="bi bi-${escHtml(String(value))}"></i> ${escHtml(String(value))}</span>`;
    case "boolean":
      return value ? "✓" : "—";
    case "date":
      return escHtml(formatDate(String(value)));
    case "number":
      return `${escHtml(String(value))}${field.config?.unit ? ` ${escHtml(field.config.unit)}` : ""}`;
    default:
      return escHtml(String(value));
  }
}
