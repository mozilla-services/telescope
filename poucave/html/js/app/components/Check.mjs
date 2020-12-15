import { Component, html } from "../../htm_preact.mjs";
import { PLOT_COLORS } from "../constants.mjs";

import Markdown from "./Markdown.mjs";
import TimeAgo from "./TimeAgo.mjs";

export default class Check extends Component {
  constructor() {
    super();
    this.cardRef = {};
    this.state = {
      focused: false,
      moreDetailsOpened: false,
    };
    this.handleAnimationEnd = this.handleAnimationEnd.bind(this);
    this.handleRefreshButtonClick = this.handleRefreshButtonClick.bind(this);
    this.handleToggleMoreDetails = this.handleToggleMoreDetails.bind(this);
  }

  componentDidUpdate(prevProps) {
    const { project, name } = this.props.focusedCheckContext;
    const { project: prevProject, name: prevName } = prevProps.focusedCheckContext;
    const { data } = this.props;

    const focusChanged = prevProject !== project || prevName !== name;

    if (focusChanged) {
      if (project === data.project && name === data.name) {
        this.setState({
          focused: true,
        });
        const card = this.cardRef.current;
        card.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      } else {
        this.setState({
          focused: false,
        });
      }
    }

    this.togglePlot();
  }

  handleAnimationEnd() {
    const { setValue } = this.props.focusedCheckContext;
    setValue(null, null);
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

  renderHeader() {
    const { data, result } = this.props;

    let statusClass = "bg-gray";
    if (!result.isLoading) {
      statusClass = result.success ? "bg-green" : "bg-red";
    }

    return html`
      <div class="card-status card-status-top ${statusClass}"></div>
      <div class="card-header">
        <h4 class="card-title check-name">${data.name}</h4>
        <div class="card-options">
          <a class="check-url" title="Open check API data" href="${data.url}" target="_blank">
            <i class="fa fa-sm fa-external-link-alt" />
          </a>
          <a class="ml-3" href="#" title="Show more details" onClick=${this.handleToggleMoreDetails}>
            <i class="fa fa-eye" />
          </a>
        </div>
      </div>
    `;
  }

  renderBody() {
    const { data } = this.props;

    let tags = null;

    if (data.tags.length) {
      tags = html`
        <p class="check-tags lh-1">
          ${data.tags.map(t => html`<span class="badge mr-1 mb-1">${t}</span>`)}
        </p>
      `;
    }

    return html`
      <div class="card-body">
        ${tags}
        <${Markdown} md="${data.description}" />
      </div>
    `;
  }

  renderMoreDetails() {
    const { moreDetailsOpened } = this.state;
    const { data, result } = this.props;

    let tags = null;

    if (data.tags.length) {
      tags = html`
        <p class="check-tags lh-1">
          ${data.tags.map(t => html`<span class="badge mr-1 mb-1">${t}</span>`)}
        </p>
      `;
    }

    // Populate the list of params or provide a fallback
    let parameters = html`<em>No parameters.</em>`;
    if (result.parameters && Object.keys(result.parameters).length) {
      const parameterItems = Object.keys(result.parameters).map(k => (html`
        <dt>${k}</dt>
        <dd>${JSON.stringify(result.parameters[k], null, 2)}</dd>
      `));
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

    let resultData = null;
    if (result.data) {
      resultData = html`
        <h4>Result Data</h4>
        <pre class="check-result">${JSON.stringify(result.data, null, 2)}</pre>
      `;
    }

    let plot = html`<em>No history.</em>`;
    if (result.history?.length > 0) {
      plot = html`<div id="plot-${data.project}-${data.name}" />`;
    }

    let bugList = html`<em>No bugs.</em>`;
    if (result.buglist && result.buglist.length) {
      bugList = html`
        <ul>
          ${result.buglist.map(
        (bug) => html`<li class="${bug.open ? "open" : "closed"} ${bug.heat}">
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

    let statusClass = "text-gray";
    let icon = "question-circle"
    if (!result.isLoading) {
      statusClass = result.success ? "text-green" : "text-red";
      icon = result.success ? "check-circle" : "times-circle";
    }

    return html`
      <div class="check-details slideout-panel ${moreDetailsOpened ? "open" : ""}">
        <div class="close-button" onClick=${this.handleToggleMoreDetails} />
        <div class="slideout-panel-content">
          <h2 class="d-flex align-items-center">
            <i class="fa fa-${icon} ${statusClass}" />
            <span class="ml-2">${data.project}/${data.name}</span>
          </h2>
          
          <hr />
          
          ${tags}
          <${Markdown} md="${data.description}" />
          
          <hr />
          
          <${Markdown} md="${data.documentation}" />
  
          <h4>Parameters</h4>
          <p class="check-parameters">${parameters}</p>
  
          <h4>TTL</h4>
          <p>${data.ttl}</p>
          
          ${duration}
          ${resultData}
          
          <h4>History</h4>
          <p>${plot}</p>
  
          <h4>Known Issues</h4>
          <p class="check-buglist lh-1">
            ${bugList}
          </p>
          
          <hr />
            
          <p>
            <a class="check-troubleshooting" href="${data.troubleshooting}" target="_blank">
              <i class="fa fa-tools"></i> Troubleshooting
            </a>
          </p>
        </div>
      </div>
    `;
  }

  renderFooter() {
    const { result } = this.props;
    const updated = result.datetime ? new Date(result.datetime) : new Date();

    return html`
      <div class="card-footer">
        <div class="float-right">
          <button
            class="check-refresh btn btn-sm btn-secondary"
            onClick="${this.handleRefreshButtonClick}"
            disabled="${result.isLoading}"
          >
            <i class="fa fa-sync-alt mr-1 ${result.isLoading ? 'fa-spin' : ''}"></i>
            Refresh
          </button>
        </div>
        <span>
          Updated <${TimeAgo} date="${updated}" />
        </span>
      </div>
    `;
  }

  render({ data }) {
    const cardClass = this.state.focused ? "animate-blink" : "";
    return html`
      <div
        ref="${this.cardRef}"
        class="check-card card ${cardClass}"
        id="check--${data.project}--${data.name}"
        onAnimationEnd="${this.handleAnimationEnd}"
      >
        ${this.renderHeader()}
        ${this.renderBody()}
        ${this.renderMoreDetails()}
        ${this.renderFooter()}
      </div>
    `;
  }

  handleToggleMoreDetails(ev) {
    ev.preventDefault();
    const { moreDetailsOpened } = this.state;
    this.setState({ moreDetailsOpened: !moreDetailsOpened });
  }

  get plotDiv() {
    const { data } = this.props;
    return `plot-${data.project}-${data.name}`;
  }

  togglePlot() {
    const { result: { history = [] } } = this.props;
    if (history.length == 0) {
      // Data not loaded. Nothing to do.
      return;
    }

    const { moreDetailsOpened } = this.state;
    if (!moreDetailsOpened) {
      // Details panel closed, clean-up.
      Plotly.purge(this.plotDiv);
      return;
    }

    // Red dots for values associated to failing statuses.
    const failuresPlot = {
      x: [],
      y: [],
      mode: 'markers',
      marker: {
        color: PLOT_COLORS.MARKERS_FAILURE,
        size: 12,
      }
    };
    // Yellow lines with history of values.
    const scalarPlot = {
      x: [],
      y: [],
      mode: 'lines',
      fill: 'tonexty',
      fillcolor: PLOT_COLORS.FILL_SCALAR,
      line: {
        shape: 'hvh',
        color: PLOT_COLORS.LINE_SCALAR,
        width: 1,
      },
      type: 'scatter'
    };
    // This baseline will be used to define the area of fill
    // for the scalar plot (fill=tonexty), instead of
    // showing y=0 (fill=tozeroy).
    const baselinePlot = {
      x: [history[0].t, history[history.length - 1].t],
      y: [],
      mode: 'lines',
      line: {
        width: 0,
      }
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
      scalarPlot.y.push(scalar);
      maxValue = Math.max(maxValue, scalar);
      // Keep lowest value as baseline.
      if (!baselinePlot.y[0] || scalar < baselinePlot.y[0]) {
        baselinePlot.y = [scalar, scalar];
      }
    }

    Plotly.react(
      this.plotDiv,
      [
        baselinePlot,
        scalarPlot,
        failuresPlot,
      ],
      {
        showlegend: false,
        paper_bgcolor: "#00000000", // transparent.
        plot_bgcolor: "#00000000",
        margin: {
          b: 80,
          // adjust left margin size to Y scale.
          l: `${Math.round(maxValue)}`.length * 8,
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
        }
      },
      {
        staticPlot: true,
        responsive: true
      }
    );

    // This is necessary for the responsivity of the chart.
    if (!this.resizeHandler) {
      this.resizeHandler = () => Plotly.Plots.resize(this.plotDiv);
    }
    window.addEventListener('resize', this.resizeHandler);
    this.resizeHandler();
  }
}
