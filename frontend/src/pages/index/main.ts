import { mount } from "svelte";
import PlacesIndex from "../../lib/PlacesIndex.svelte";
import "../../app.css";

mount(PlacesIndex, {
  target: document.getElementById("app-root")!,
  props: {},
});
