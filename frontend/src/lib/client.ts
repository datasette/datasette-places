import createClient from "openapi-fetch";

export const client = createClient({
  baseUrl: "/",
  headers: { "Content-Type": "application/json" },
});
