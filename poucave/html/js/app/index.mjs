import { html, render } from "../htm_preact.mjs";

import App from "./components/App.mjs";
import { ROOT_URL } from "./constants.mjs";

// Initialize the app on page load
window.addEventListener("load", async () => {
  // Clear the application container and render the application
  const appContainer = document.getElementById("app");
  appContainer.innerHTML = "";

  // Fetch instance metadata.
  const resp = await fetch(new URL("/", ROOT_URL));
  const { service } = await resp.json();
  const title = capitalize(service);
  document.title = title;

  render(html`<${App} pageTitle=${title} />`, appContainer);
});


function capitalize(str) {
  return str.replace(/[\W_]+/g, " ")
    .split(" ")
    .map(word => {
      return word[0].toUpperCase() + word.substring(1);
    })
    .join(" ");
}
