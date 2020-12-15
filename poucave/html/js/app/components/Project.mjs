import { Component, html } from "../../htm_preact.mjs";
import FocusedCheck from "../contexts/FocusedCheck.mjs";
import Check from "./Check.mjs";

export default class Project extends Component {
  renderStatus() {
    const { checks } = this.props;

    const isLoading = checks.some(c => c.result.isLoading);
    const isHealthy = checks.every(c => c.result.success);

    let color = "bg-gray";
    let status = "loading";
    if (!isLoading) {
      color = isHealthy ? "bg-green" : "bg-red";
      status = isHealthy ? "Healthy" : "Unhealthy";
    }

    return html`
      <span class="badge ${color}">${status}</span>
    `;
  }

  renderChecks() {
    const { checks, fetchCheckResult } = this.props;

    return checks.map(c => (html`
      <${FocusedCheck.Consumer}>
        ${
      focusedCheckContext => (html`
            <${Check}
              data="${c.data}"
              result="${c.result}"
              fetchCheckResult="${fetchCheckResult}"
              focusedCheckContext="${focusedCheckContext}"
            />
          `)
    }
      </>
    `))
  }

  render({ name }) {
    return html`
      <section class="project mt-3 pt-4">
        <div class="float-right mt-1 lh-1">
          ${this.renderStatus()}
        </div>
        <h3 class="mb-4">
          <i class="fa fa-layer-group mr-2"></i>
          <span class="project-name">${name}</span>
        </h3>
        <div class="project-cards mb-1">
          ${this.renderChecks()}
        </div>
      </section>
    `;
  }
}
