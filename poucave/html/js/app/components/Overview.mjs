import { Component, html } from "../../htm_preact.mjs";
import FocusedCheck from "../contexts/FocusedCheck.mjs";

import SystemDiagram from "./SystemDiagram.mjs";
import TimeAgo from "./TimeAgo.mjs";

export default class Overview extends Component {
  constructor() {
    super();
    this.failing = new Set();
  }

  componentDidUpdate() {
    const { results } = this.props;
    // Keep track of checks that are failing.
    Object.values(results)
      .filter((r) => !r.isLoading)
      .forEach(({ project, name, success }) => {
        if (success) {
          this.failing.delete(`${project}.${name}`);
        } else {
          this.failing.add(`${project}.${name}`);
        }
      });
  }

  render({ checks, results }) {
    // Show the loading checks that were previously failing.
    // Do not list the errors if a response could not be obtained.
    const failing = Object.values(results).filter(
      (r) =>
        (r.isLoading && this.failing.has(`${r.project}.${r.name}`)) ||
        (!r.isLoading && !r.isIncomplete && !r.success)
    );

    const isHealthy = failing.length == 0;

    const iconClass = isHealthy
      ? "fa-check-circle text-green"
      : "fa-times-circle text-red";

    return html`
      <div class="mt-4 mb-5 overview">
        <${FocusedCheck.Consumer}>
          ${(focusedCheckContext) => html`
            <${SystemDiagram}
              checks="${checks}"
              results="${results}"
              focusedCheckContext="${focusedCheckContext}"
            />
          `}
        </${FocusedCheck.Consumer}>

        <div class="card">
          <div class="card-body text-center">
            <i class="fa fa-4x ${iconClass}"></i>
            <p>
              <strong
                >The system
                ${
                  isHealthy ? " is currently healthy" : " has failing checks"
                }.</strong
              >
              <br />
              <span class="text-gray-medium">
                Last updated <${TimeAgo} date="${new Date()}" />.
              </span>
            </p>
            <div class="error-list">${this.renderErrorList(failing)}</div>
          </div>
        </div>
      </div>
    `;
  }

  renderErrorList(failing) {
    if (failing.length == 0) {
      return "";
    }

    let columns = [];

    // Spread items over 3 columns.
    const chunk = Math.ceil(failing.length / 3);
    for (let i = 0; i < failing.length; i += chunk) {
      const slice = failing.slice(i, i + chunk);

      columns.push(html`
        <ul class="text-red">
          <${FocusedCheck.Consumer}>
            ${(focusedCheckContext) =>
              slice.map(
                (r) =>
                  html`<li>
                    <a
                      class="${r.isLoading ? "text-gray-medium" : "text-red"}"
                      href="#"
                      onClick=${(e) => {
                        e.preventDefault();
                        focusedCheckContext.setValue(r.project, r.name);
                      }}
                    >
                      ${r.project} / ${r.name}
                    </a>
                  </li>`
              )}
          </${FocusedCheck.Consumer}>
        </ul>
      `);
    }

    return columns;
  }
}
