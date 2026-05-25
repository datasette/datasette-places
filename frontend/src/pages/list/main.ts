import { mount } from "svelte";
import PlacesApp from "../../lib/PlacesApp.svelte";
import "../../app.css";
import "leaflet/dist/leaflet.css";
import { loadPageData } from "../../lib/pageData";

const pageData = loadPageData<{ list_id: number }>();

mount(PlacesApp, {
  target: document.getElementById("app-root")!,
  props: { listId: pageData.list_id },
});
