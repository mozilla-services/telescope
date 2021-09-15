import { Component, html } from "../../htm_preact.mjs";
import { PLOT_COLORS } from "../constants.mjs";

import Markdown from "./Markdown.mjs";
import TimeAgo from "./TimeAgo.mjs";

export default class CheckDetails extends Component {
  constructor() {
    super();
    this.handleRefreshButtonClick = this.handleRefreshButtonClick.bind(this);
  }

  componentDidUpdate(prevProps) {
    if (prevProps.opened && !this.props.opened) {
      Plotly.purge(this.plotDivID);
    } else if (this.props.opened) {
      this.displayPlot();
    }
  }

  get plotDivID() {
    const { data } = this.props;
    return `plot-${data.project}-${data.name}`;
  }

  displayPlot() {
    const {
      result: { history = [] },
    } = this.props;
    if (history.length === 0) {
      // Data not loaded. Nothing to do.
      return;
    }

    // Red dots for values associated to failing statuses.
    const failuresPlot = {
      x: [],
      y: [],
      mode: "markers",
      marker: {
        color: PLOT_COLORS.MARKERS_FAILURE,
        size: 12,
      },
    };
    // Yellow lines with history of values.
    const scalarPlot = {
      x: [],
      y: [],
      mode: "lines",
      fill: "tonexty",
      fillcolor: PLOT_COLORS.FILL_SCALAR,
      line: {
        shape: "hvh",
        color: PLOT_COLORS.LINE_SCALAR,
        width: 1,
      },
      type: "scatter",
    };
    // This baseline will be used to define the area of fill
    // for the scalar plot (fill=tonexty), instead of
    // showing y=0 (fill=tozeroy).
    const baselinePlot = {
      x: [history[0].t, history[history.length - 1].t],
      y: [],
      mode: "lines",
      line: {
        width: 0,
      },
    };

    let maxValue = history[0].scalar;
    for (let { t, success, scalar } of history) {
      // Only plot failures.
      if (!success) {
        failuresPlot.x.push(t);
        failuresPlot.y.push(scalar);
      }
      // History of scalars.
      scalarPlot.x.push(t);
      scalarPlot.y.push(scalar.toFixed(2));
      maxValue = Math.max(maxValue, scalar);
      // Keep lowest value as baseline.
      if (!baselinePlot.y[0] || scalar < baselinePlot.y[0]) {
        baselinePlot.y = [scalar, scalar];
      }
    }

    Plotly.react(
      this.plotDivID,
      [baselinePlot, scalarPlot, failuresPlot],
      {
        showlegend: false,
        paper_bgcolor: "#00000000", // transparent.
        plot_bgcolor: "#00000000",
        margin: {
          b: 60,
          // adjust left margin size to Y scale.
          l: `${maxValue.toFixed(2)}`.length * 8 + 10,
          t: 0,
          r: 0,
        },
        xaxis: {
          color: PLOT_COLORS.AXIS,
          gridcolor: PLOT_COLORS.GRID,
        },
        yaxis: {
          color: PLOT_COLORS.AXIS,
          gridcolor: PLOT_COLORS.GRID,
        },
      },
      {
        staticPlot: true,
        responsive: true,
      }
    );

    // This is necessary for the responsivity of the chart.
    if (!this.resizeHandler) {
      this.resizeHandler = () => Plotly.Plots.resize(this.plotDivID);
    }
    window.addEventListener("resize", this.resizeHandler);
    this.resizeHandler();
  }

  handleRefreshButtonClick() {
    const { data, fetchCheckResult } = this.props;
    let refreshSecret = localStorage.getItem("refresh-secret");
    if (!refreshSecret) {
      refreshSecret = prompt("Refresh secret?") || "";
      localStorage.setItem("refresh-secret", refreshSecret);
    }
    fetchCheckResult(data, { refreshSecret });
  }

  render({ data, result, opened, onClickCloseButton }) {
    let tags = null;

    if (data.tags.length) {
      tags = html`
        <p class="check-tags lh-1">
          ${data.tags.map(
            (t) => html`<span class="badge mr-1 mb-1">${t}</span>`
          )}
        </p>
      `;
    }

    // Populate the list of params or provide a fallback
    let parameters = html`<em>No parameters.</em>`;
    if (result.parameters && Object.keys(result.parameters).length) {
      const parameterItems = Object.keys(result.parameters).map(
        (k) => html`
          <dt>${k}</dt>
          <dd>${JSON.stringify(result.parameters[k], null, 2)}</dd>
        `
      );
      parameters = html`<dl>${parameterItems}</dl>`;
    }

    let duration = null;
    if (result.duration) {
      duration = html`
        <span class="float-right text-gray-medium lh-1">
          Executed in ${result.duration}ms.
        </span>
      `;
    }

    let statusClass = "text-gray";
    let icon = "question-circle";
    if (!result.isLoading) {
      statusClass = result.success
        ? "text-green"
        : result.isIncomplete
        ? "text-yellow"
        : "text-red";
      icon = result.success ? "check-circle" : "times-circle";
    }

    const updated = result.datetime ? new Date(result.datetime) : new Date();
    let resultData = null;
    if (result.data) {
      resultData = html`
        <h4>Result Data</h4>
        <pre class="mb-0 check-result ${statusClass}">
${JSON.stringify(result.data, null, 2)}</pre
        >
        <div class="mt-2 mb-3 text-gray-medium">
          Updated <${TimeAgo} date="${updated}" />
        </div>
      `;
    }

    let plot = html`<em>No history.</em>`;
    if (result.history?.length > 0) {
      plot = html`<div id="${this.plotDivID}" />`;
    }

    let bugList = html`<em>No bugs.</em>`;
    if (result.buglist && result.buglist.length) {
      bugList = html`
        <ul>
          ${result.buglist.map(
            (bug) => html`<li
              class="${bug.open ? "open" : "closed"} ${bug.heat}"
            >
              <a
                title="${bug.status} - ${bug.summary} (updated: ${bug.last_update})"
                href="${bug.url}"
                target="_blank"
              >
                ${bug.id}
              </a>
              ${" ("}${bug.status}${", "}${timeago().format(bug.last_update)})
            </li>`
          )}
        </ul>
      `;
    }

    return html`
      <div class="check-details slideout-panel ${opened ? "open" : ""}">
        <div class="close-button" onClick=${onClickCloseButton} />
        <div class="slideout-panel-content">
          <div class="d-flex align-items-center">
            <h2 class="d-flex align-items-center flex-grow-1">
              <i class="fa fa-${icon} ${statusClass}" />
              <span class="ml-2 flex-grow-1">${data.project}/${data.name}</span>
            </h2>
            <span class="ml-3">
              <a
                class="check-url text-gray-medium"
                title="Open check API data"
                href="${data.url}"
                target="_blank"
              >
                <i class="fa fa-sm fa-external-link-alt" />
              </a>
            </span>
            <span class="text-right ml-4">
              <button
                class="check-refresh btn btn-sm btn-secondary"
                onClick="${this.handleRefreshButtonClick}"
                disabled="${result.isLoading}"
              >
                <i
                  class="fa fa-sync-alt mr-1 ${result.isLoading
                    ? "fa-spin"
                    : ""}"
                ></i>
                Refresh
              </button>
            </span>
          </div>

          <hr />

          <div class="w-50">
            ${tags}
            <${Markdown} md="${data.description}" />
          </div>

          <hr />

          <div class="d-flex">
            <div class="w-50">
              <h4>Documentation</h4>
              <${Markdown} md="${data.documentation}" />
            </div>
            <div class="pl-2">
              <h4>TTL</h4>
              <p>${data.ttl}</p>
            </div>
          </div>

          <h4>Parameters</h4>
          <p class="check-parameters">${parameters}</p>

          ${duration} ${resultData}

          <h4>History</h4>
          <p>${plot}</p>

          <h4>Known Issues</h4>
          <p class="check-buglist lh-1">${bugList}</p>

          <hr />

          <p>
            <a
              class="check-troubleshooting"
              href="${data.troubleshooting}"
              target="_blank"
            >
              <i class="fa fa-tools"></i> Troubleshooting
            </a>
          </p>
        </div>
      </div>
    `;
  }
}
