import { html } from "../../htm_preact.mjs";

import Dashboard from "./Dashboard.mjs";

const App = ({ pageTitle }) => {
  return html`
    <div class="auto-theme-dark">
      <div class="page overflow-auto pb-6">
        <div class="flex-fill">
          <div class="header py-3">
            <div class="container">
              <h3 id="page-title" class="my-0">
                <i class="fa fa-tachometer-alt mr-2"></i>
                ${pageTitle}
              </h3>
            </div>
          </div>
          <div class="my-3">
            <div class="container">
              <${Dashboard} />
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
};

export default App;
