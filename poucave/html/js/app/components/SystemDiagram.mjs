import { Component, html } from "../../htm_preact.mjs";

export default class SystemDiagram extends Component {
  constructor() {
    super();
    this.svgRef = {};
    this.handleObjectLoad = this.handleObjectLoad.bind(this);
    this.handleObjectError = this.handleObjectError.bind(this);
    this.state = {
      diagramHidden: false,
      diagramReady: false,
    };
  }

  handleObjectLoad() {
    this.setState({
      diagramReady: true,
    });
  }

  handleObjectError() {
    this.setState({
      diagramHidden: true,
    });
  }

  componentDidUpdate() {
    const { diagramReady } = this.state;
    const { focusedCheckContext, checks, results } = this.props;

    // Diagram is not ready so nothing to update
    if (!diagramReady) {
      return;
    }

    const svgDoc = this.svgRef.current.contentDocument;
    Object.keys(results).forEach(k => {
      const c = checks[k];
      const r = results[k];
      const indicator = svgDoc.getElementById(`${c.project}--${c.name}`);

      if (indicator) {
        // Check if the indicator has its tooltip or assume it has not been initialized
        if (indicator.childElementCount === 0) {
          indicator.setAttribute("cursor", "pointer");

          // Add tooltip
          const tooltip = document.createElementNS("http://www.w3.org/2000/svg", "title");
          tooltip.textContent = `${c.project}/${c.name}:\n${c.description}`;
          indicator.appendChild(tooltip);

          indicator.addEventListener("click", () => {
            focusedCheckContext.setValue(c.project, c.name);
          });
        }

        indicator.removeAttribute("fill");
        if (!r.isLoading) {
          indicator.setAttribute("fill", r.success ? "green" : "red");
        }
      }
    });
  }

  render() {
    const { diagramHidden, diagramReady } = this.state;
    const { results } = this.props;
    const diagramClass = diagramReady ? "" : "invisible";
    const diagramCardClass = diagramHidden ? "d-none" : "";

    const isLoading = Object.values(results).some(r => r.isLoading);

    let loader = null;
    if (isLoading) {
      loader = html`<i class="fa fa-spinner fa-spin" />`;
    }

    return html`
      <div class="card ${diagramCardClass}">
        <div class="card-header">
          <h4 class="card-title">System Overview</h4>
          <div class="card-options">${loader}</div>
        </div>
        <div class="card-body">
          <object
            ref="${this.svgRef}"
            onload="${this.handleObjectLoad}"
            onerror="${this.handleObjectError}"
            class="d-block mx-auto system-diagram ${diagramClass}"
            data="/diagram.svg"
            type="image/svg+xml"
          />
        </div>
      </div>
    `;
  }
}
