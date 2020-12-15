import { Component, html } from "../../htm_preact.mjs";
import FocusedCheck from "../contexts/FocusedCheck.mjs";
import { ROOT_URL } from "../constants.mjs";

import Overview from "./Overview.mjs";
import Project from "./Project.mjs";

export default class Dashboard extends Component {
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
    const url = new URL("/checks", ROOT_URL);
    const response = await fetch(url.toString());
    const checksData = await response.json();

    // Sort by project/name.
    checksData.sort((a, b) => {
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
      const url = new URL(check.url, ROOT_URL);
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

    // Group by project
    const projects = {};
    Object.values(checks)
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
