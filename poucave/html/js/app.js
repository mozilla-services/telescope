import { html, createContext, Component, render } from './htm_preact.module.js';

const FocusedCheck = createContext({
  project: null,
  name: null,
  setValue: () => {},
});

class App extends Component {
  render() {
    return html`
      <div class="auto-theme-dark">
        <div class="page overflow-auto pb-6">
          <div class="flex-fill">
            <div class="header py-3">
              <div class="container">
                <h3 class="my-0">
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
      </div>
    `;
  }
}

class Dashboard extends Component {
  constructor() {
    super();
    this.triggerRecheck = this.triggerRecheck.bind(this);
    this.fetchCheckResult = this.fetchCheckResult.bind(this);
    this.setFocusedCheck = this.setFocusedCheck.bind(this);
    this.state = {
      checks: {},
      results: {},
      recheckTimeouts: {},
      focusedCheck: {
        name: null,
        project: null,
      },
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
    Object.values(recheckTimeouts).forEach(timeoutId => {
      clearTimeout(timeoutId);
    });
  }

  componentDidUpdate() {
    this.updateFavicon();
  }

  updateFavicon() {
    const { results } = this.state;

    const isLoading = Object.values(results).some(r => r.isLoading);
    const isHealthy = Object.values(results).every(r => r.success);

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
        result = {
          project: check.project,
          name: check.name,
          success: false,
          datetime: new Date(),
          data: err.toString(),
          duration: 0
        };
      } finally {
        const results = {
          ...this.state.results,
          [key]: result,
        }
        this.setState({results});
      }
    });
  }

  setFocusedCheck(project, name) {
    this.setState({
      focusedCheck: {
        project,
        name,
      },
    });
  }

  renderProjects() {
    const { checks, results } = this.state;

    // Sort checks and group by project
    const projects = {};
    Object.values(checks)
      .sort((a, b) => {
        if (a.project == b.project) {
          if (a.name == b.name) {
            return 0;
          } else {
            return a.name < b.name ? -1 : 1;
          }
        } else {
          return a.project < b.project ? -1 : 1;
        }
      })
      .forEach(check => {
        const p = check.project;
        if (!(p in projects)) {
          projects[p] = [];
        }
        projects[p].push({
          data: check,
          result: results[`${check.project}.${check.name}`],
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
    const { checks, results, focusedCheck } = this.state;

    const focusedCheckContext = {
      ...focusedCheck,
      setValue: this.setFocusedCheck,
    };

    return html`
      <${FocusedCheck.Provider} value="${focusedCheckContext}">
        <${Overview} checks="${checks}" results="${results}" />
        ${this.renderProjects()}
      </>
    `;
  }
}

class Overview extends Component {
  render({ checks, results }) {
    const failing = Object.values(results).filter(r => !r.isLoading && !r.success);
    const isHealthy = failing.length == 0;

    const iconClass = isHealthy ? "fa-check-circle text-green" : "fa-times-circle text-red";

    return html`
      <div class="mt-4 mb-5">
        <${FocusedCheck.Consumer}>
          ${
            focusedCheckContext => (html`
              <${SystemDiagram}
                checks="${checks}"
                results="${results}"
                focusedCheckContext="${focusedCheckContext}"
              />
            `)
          }
        </>

        <div class="card">
          <div class="card-body text-center">
            <i class="fa fa-4x ${iconClass}"></i>
            <p>
              <strong>The system ${isHealthy ? "is currently healthy" : "has failing checks"}.</strong>
              <br />
              <span class="text-gray-medium">
                Last updated <${TimeAgo} date="${new Date()}" />.
              </span>
            </p>
            ${this.renderErrorList(failing)}
          </div>
        </div>
      </div>
    `;
  }

  renderErrorList(failing) {
    if (failing.length == 0) {
      return "";
    }

    return html`
      <ul class="text-red">
        <${FocusedCheck.Consumer}>
          ${focusedCheckContext => (
            failing.map(r => (
              html`<li>
                <a class="text-red" href="#" onClick=${e => {
                  e.preventDefault();
                  focusedCheckContext.setValue(r.project, r.name);
                }}>
                  ${r.project} / ${r.name}
                </a>
              </li>`
            ))
          )}
        </>
      </ul>
    `;
  }
}

class SystemDiagram extends Component {
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

class Project extends Component {
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

class Check extends Component {
  constructor() {
    super();
    this.cardRef = {};
    this.state = {
      focused: false,
    };
    this.handleAnimationEnd = this.handleAnimationEnd.bind(this);
    this.handleRefreshButtonClick = this.handleRefreshButtonClick.bind(this);
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
        class="card ${cardClass}"
        id="check--${data.project}--${data.name}"
        onAnimationEnd="${this.handleAnimationEnd}"
      >
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

    const isDateNewlySet = date && !prevProps.date;
    const isDateChanged = date &&  prevProps.date && date.getTime() !== prevProps.date.getTime();
    if (isDateNewlySet || isDateChanged) {
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

// Initialize the app on page load
window.addEventListener("load", () => {
  // Clear the application container and render the application
  const appContainer = document.getElementById("app");
  appContainer.innerHTML = "";
  render(html`<${App} />`, appContainer);
});
