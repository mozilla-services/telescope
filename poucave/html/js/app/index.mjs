import { html, render } from "../htm_preact.mjs";

import App from "./components/App.mjs"

// Initialize the app on page load
window.addEventListener("load", () => {
  // Clear the application container and render the application
  const appContainer = document.getElementById("app");
  appContainer.innerHTML = "";
  render(html`<${App} />`, appContainer);
});
