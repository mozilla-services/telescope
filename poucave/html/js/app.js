import { h, createRef, Component, Fragment, render } from 'https://unpkg.com/preact?module';
import htm from 'https://unpkg.com/htm?module';

// Initialize htm with Preact
const html = htm.bind(h);

class App extends Component {
  render() {
    return html`
      <div class="page overflow-auto pb-6">
        <div class="flex-fill">
          <div class="header py-3">
            <div class="container">
              <h3>
                <i class="fa fa-tachometer-alt mr-2"></i>
                Delivery System Status
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
    `;
  }
}

class Dashboard extends Component {
  constructor() {
    super();
    this.triggerRecheck = this.triggerRecheck.bind(this);
    this.fetchCheckResult = this.fetchCheckResult.bind(this);
    this.state = {
      checks: {},
      results: {},
      recheckTimeouts: {},
    };
  }

  async componentDidMount() {
    const response = await fetch("/checks");
    const checksData = await response.json();

    const checks = {};
    const results = {}
    checksData.forEach(c => {
      const key = `${c.project}.${c.name}`;
      checks[key] = c;
      results[key] = {
        isLoading: true,
      };
      this.triggerRecheck(c);
    });
    this.setState({
      checks,
      results,
    });
  }

  componentWillUnmount() {
    const { recheckTimeouts } = this.state;
    Object.keys(recheckTimeouts).forEach(k => {
      clearTimeout(recheckTimeouts[k]);
    });
  }

  componentDidUpdate() {
    this.updateFavicon();
  }

  updateFavicon() {
    const { results } = this.state;

    let isLoading = false;
    let isHealthy = true;

    Object.keys(results).forEach(k => {
      const r = results[k];
      isLoading |= r.isLoading;
      isHealthy &= r.success;
    });

    let favicon = "img/loading.png";
    if (!isLoading) {
      favicon = isHealthy ? "img/success.png" : "img/failure.png";
    }
    document.querySelector("link[rel*='icon']").setAttribute("href", favicon);
  }

  async triggerRecheck(check) {
     // Fetch the result
    await this.fetchCheckResult(check);

    // Reschedule the check
    const key = `${check.project}.${check.name}`;
    const timeout = setTimeout(() => this.triggerRecheck(check), check.ttl * 1000);
    const recheckTimeouts = {
      ...this.state.recheckTimeouts,
      [key]: timeout,
    };
    this.setState({
      recheckTimeouts,
    });
  }

  async fetchCheckResult(check, options = {}) {
    // Mark the check as loading and then proceed
    const key = `${check.project}.${check.name}`;
    const results = {
      ...this.state.results,
      [key]: {
        ...this.state.results[key],
        isLoading: true,
      }
    };
    this.setState({
      results,
    }, async () => {
      const {refreshSecret = null} = options;
      const domain = window.location.href.split('/')[2];
      const url = new URL(check.url, `${window.location.protocol}//${domain}`);
      if (refreshSecret) {
        url.searchParams.append("refresh", refreshSecret);
      }

      // Fetch the check result and update
      let response;
      let result;
      try {
        response = await fetch(url.toString());
        result = await response.json();
      } catch (err) {
        if (response && /Invalid refresh secret/.test(response.statusText)) {
          // Forget about this refresh secret
          localStorage.removeItem("refresh-secret");
        }
        console.warn(check.project, check.name, err);
        result = {success: false, data: err.toString(), duration: 0};
      } finally {
        const results = {
          ...this.state.results,
          [key]: result,
        }
        this.setState({results});
      }
    });
  }

  renderProjects() {
    const { checks, results } = this.state;

    // Sort the keys by project and then by name
    const sortedCheckKeys = Object.keys(checks).sort((ka, kb) => {
      const a = checks[ka];
      const b = checks[kb];
      if (a.project == b.project) {
        if (a.name == b.name) {
          return 0;
        } else {
          return a.name < b.name ? -1 : 1;
        }
      } else {
        return a.project < b.project ? -1 : 1;
      }
    });

    // Group the checks by project
    const projects = {};
    sortedCheckKeys.forEach(k => {
      const p = checks[k].project;
      if (!(p in projects)) {
        projects[p] = [];
      }
      projects[p].push({
        data: checks[k],
        result: results[k],
      });
    });

    return Object.keys(projects).map(
      name => html`
        <${Project} 
          name="${name}" 
          checks="${projects[name]}" 
          fetchCheckResult="${this.fetchCheckResult}" 
        />
      `,
    );
  }

  render() {
    const { checks, results } = this.state;

    return html`
      <${Overview} checks="${checks}" results="${results}" />
      ${this.renderProjects()}
    `;
  }
}

class Overview extends Component {
  render({ checks, results }) {
    let isHealthy = true;

    Object.keys(results).forEach(k => {
      const r = results[k];
      isHealthy &= r.success;
    });

    const iconClass = isHealthy ? "fa-check-circle text-green" : "fa-times-circle text-red";

    return html`
      <div class="mt-4 mb-5">
        <${SystemDiagram} checks="${checks}" results="${results}" />
  
        <div class="card">
          <div class="card-body text-center">
            <i class="fa fa-4x ${iconClass}"></i>
            <p>
              <strong>The current system status is ${isHealthy ? "Healthy" : "Unhealthy"}.</strong>
              <br />
              <span class="text-gray">
                Last updated <${TimeAgo} date="${new Date()}" />.
              </span>
            </p>
          </div>
        </div>
      </div>
    `;
  }
}

class SystemDiagram extends Component {
  svgRef = createRef();

  constructor() {
    super();
    this.handleObjectLoad = this.handleObjectLoad.bind(this);
    this.handleObjectError = this.handleObjectError.bind(this);
    this.state = {
      diagramHidden: false,
      diagramReady: false,
    };
  }

  handleObjectLoad() {
    const { checks } = this.props;

    const svgDoc = this.svgRef.current.contentDocument;
    Object.keys(checks).forEach(k => {
      const c = checks[k];
      const indicator = svgDoc.getElementById(`${c.project}--${c.name}`);
      if (indicator) {
        indicator.setAttribute("cursor", "pointer");
        indicator.setAttribute("fill", "#acb0b8");

        // Add tooltip
        const tooltip = document.createElementNS("http://www.w3.org/2000/svg", "title");
        tooltip.textContent = `${c.project}/${c.name}:\n${c.description}`;
        indicator.appendChild(tooltip);

        indicator.addEventListener("click", () => {
          document.getElementById(`check--${c.project}--${c.name}`).scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
        });
      }
    });

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
    const {checks, results} = this.props;

    const svgDoc = diagramReady ? this.svgRef.current.contentDocument : null;

    Object.keys(results).forEach(k => {
      const c = checks[k];
      const r = results[k];

      if (svgDoc) {
        const indicator = svgDoc.getElementById(`${c.project}--${c.name}`);
        if (indicator) {
          let fillColor = "#acb0b8";
          if (!r.isLoading) {
            fillColor = r.success ? "#5eba00" : "#fa4654";
          }
          indicator.setAttribute("fill", fillColor);
        }
      }
    });
  }

  render() {
    const { diagramHidden, diagramReady } = this.state;
    const { results } = this.props;
    const diagramClass = diagramReady ? "" : "invisible";
    const diagramCardClass = diagramHidden ? "d-none" : "";

    let isLoading = false;
    Object.keys(results).forEach(k => {
      const r = results[k];
      isLoading |= r.isLoading;
    });

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

class Project extends Component {
  renderStatus() {
    const { checks } = this.props;

    let isLoading = false;
    let isHealthy = true;

    checks.forEach(c => {
      isLoading |= c.result.isLoading;
      isHealthy &= c.result.success;
    });

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

  render({ name, checks, fetchCheckResult }) {
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
          ${checks.map(c => html`<${Check} data="${c.data}" result="${c.result}" fetchResult="${fetchCheckResult}" />`)}
        </div>
      </section>
    `;
  }
}

class Check extends Component {
  constructor() {
    super();
    this.handleRefreshButtonClick = this.handleRefreshButtonClick.bind(this);
  }

  handleRefreshButtonClick() {
    const { data, fetchResult } = this.props;
    let refreshSecret = localStorage.getItem("refresh-secret");
    if (!refreshSecret) {
      refreshSecret = prompt("Refresh secret?");
      localStorage.setItem("refresh-secret", refreshSecret);
    }
    fetchResult(data);
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
          <a class="check-url" href="${data.url}" target="_blank">
            <i class="fa fa-sm fa-external-link-alt"></i>
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
          ${data.tags.map(t => html`<span class="badge bg-gray mr-1 mb-1">${t}</span>`)}
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

  renderDetails() {
    const { data, result } = this.props;

    // Populate the list of params or provide a fallback
    let parameters = html`<em>No parameters.</em>`;
    if (result.parameters && Object.keys(result.parameters).length) {
      const parameterItems = Object.keys(result.parameters).map(k => (html`
        <dt>${k}</dt>
        <dd>${result.parameters[k]}</dd>
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

    return html`
      <div class="card-footer check-details">
        <details>
          <summary>
            <div class="float-right fs-1 lh-1">
              <span class="badge bg-gray-medium">
                TTL: ${data.ttl}
              </span>
            </div>
            Details
          </summary>

          <${Markdown} md="${data.documentation}" />

          <h4>Parameters</h4>
          <p class="check-parameters">${parameters}</p>

          ${duration}
          ${resultData}

          <p>
            <a class="check-troubleshooting" href="${data.troubleshooting}" target="_blank">
              <i class="fa fa-tools"></i> Troubleshooting
            </a>
          </p>
        </details>
      </div>
    `;
  }

  renderFooter() {
    const { data, result } = this.props;
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
        <span class="text-fine">
          Updated <${TimeAgo} date="${updated}" />
        </span>
      </div>
    `;
  }

  render({ data }) {
    return html`
      <div class="card" id="check--${data.project}--${data.name}">
        ${this.renderHeader()}
        ${this.renderBody()}
        ${this.renderDetails()}
        ${this.renderFooter()}
      </div>
    `;
  }
}

class TimeAgo extends Component {
  constructor() {
    super();
    this.refresh = this.refresh.bind(this);
    this.state = {
      timeago: "some time ago",
      timeoutId: null,
    }
  }

  componentDidMount() {
    this.refresh();
  }

  componentDidUpdate(prevProps, prevState) {
    const { date } = this.props;
    const { timeoutId } = this.state;
    if (prevState.timeoutId && timeoutId !== prevState.timeoutId) {
      clearTimeout(prevState.timeoutId);
    }
    if (date &&  prevProps.date && date.getTime() !== prevProps.date.getTime()) {
      clearTimeout(timeoutId);
      this.refresh();
    }
  }

  componentWillUnmount() {
    const { timeoutId } = this.state;
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }

  refresh() {
    const { date } = this.props;

    if (date) {
      // Determine how often to refresh the timeago value
      const now = new Date();
      const timedelta = Math.abs(now.getTime() - date.getTime());
      let timeoutDuration;
      if (timedelta < 60 * 1000) {
        timeoutDuration = 1000;
      } else if (timedelta < 60 * 60 * 1000) {
        timeoutDuration = 60 * 1000;
      } else if (timedelta < 24 * 60 * 60 * 1000) {
        timeoutDuration = 10 * 60 * 1000;
      } else {
        timeoutDuration = 60 * 60 * 1000;
      }

      const timeoutId = setTimeout(this.refresh, timeoutDuration);

      this.setState({
        timeago: timeago().format(date),
        timeoutId,
      });
    }
  }

  render({ date }) {
    const isoDate = date ? date.toISOString() : '';
    const title = date ? date.toString() : '';
    return html`
      <time datetime="${isoDate}" title="${title}">
        ${this.state.timeago}
      </time>
    `;
  }
}

class Markdown extends Component {
  render({ md }) {
    const innerHTML = {
      __html: marked(md),
    };

    return html`<div dangerouslySetInnerHTML="${innerHTML}" />`;
  }
}

// Clear the application container and render the application
const appContainer = document.getElementById("app");
appContainer.innerHTML = "";
render(html`<${App} />`, appContainer);
