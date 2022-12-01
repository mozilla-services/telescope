import { Component, html } from "../../htm_preact.mjs";
import FocusedCheck from "../contexts/FocusedCheck.mjs";
import SelectedTags from "../contexts/SelectedTags.mjs";
import { ROOT_URL, RETRY_INTERVAL } from "../constants.mjs";

import Overview from "./Overview.mjs";
import Project from "./Project.mjs";
import TagListFilter from "./TagListFilter.mjs";

export default class Dashboard extends Component {
  constructor() {
    super();
    this.triggerRecheck = this.triggerRecheck.bind(this);
    this.fetchCheckResult = this.fetchCheckResult.bind(this);
    this.setFocusedCheck = this.setFocusedCheck.bind(this);
    this.onHashChange = this.onHashChange.bind(this);
    this.state = {
      checks: {},
      results: {},
      recheckTimeouts: {},
      focusedCheck: {
        name: null,
        project: null,
      },
      selectedTags: {
        tags: [],
      },
    };
  }

  async componentDidMount() {
    // Fetch projects metadata.
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

    // Execute each check.
    const checks = {};
    const results = {};
    checksData.forEach((c) => {
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
    // Watch history to focus check.
    window.addEventListener("hashchange", this.onHashChange);
    // Check if page has state on load.
    this.onHashChange();
  }

  componentWillUnmount() {
    const { recheckTimeouts } = this.state;
    Object.values(recheckTimeouts).forEach((timeoutId) => {
      clearTimeout(timeoutId);
    });
    window.removeEventListener("hashchange", this.onHashChange);
  }

  componentDidUpdate() {
    this.updateFavicon();
  }

  onHashChange() {
    const [project, name] = window.location.hash.slice(1).split("/");
    // Highlight check in page.
    if (project && name) {
      this.setState({
        focusedCheck: {
          project,
          name,
        },
      });
    }
  }
  updateFavicon() {
    const { results } = this.state;

    const isLoading = Object.values(results).some((r) => r.isLoading);
    const isHealthy = Object.values(results).every((r) => r.success);

    let favicon = "img/loading.png";
    if (!isLoading) {
      favicon = isHealthy ? "img/success.png" : "img/failure.png";
    }
    document.querySelector("link[rel*='icon']").setAttribute("href", favicon);
  }

  async triggerRecheck(check) {
    // Fetch the result
    const result = await this.fetchCheckResult(check);

    // Reschedule the check
    const interval = result.isIncomplete ? RETRY_INTERVAL : check.ttl * 1000;
    const key = `${check.project}.${check.name}`;
    const timeout = setTimeout(() => this.triggerRecheck(check), interval);
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
      },
    };
    return new Promise((resolve) => {
      this.setState(
        {
          results,
        },
        async () => {
          const { refreshSecret = null } = options;
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
            if (
              response &&
              /Invalid refresh secret/.test(response.statusText)
            ) {
              // Forget about this refresh secret
              localStorage.removeItem("refresh-secret");
            }
            console.warn(check.project, check.name, err);
            result = {
              project: check.project,
              name: check.name,
              datetime: new Date(),
              data: err.toString(),
              duration: 0,
              success: false, // Mark as failed.
              isIncomplete: true, // Distinguish network errors from failing checks.
            };
          } finally {
            const results = {
              ...this.state.results,
              [key]: result,
            };
            this.setState({ results });
          }
          resolve(result);
        }
      );
    });
  }

  setFocusedCheck(project, name) {
    if (project && name) {
      // Reflect change of focused change in URL bar.
      window.location.hash = `#${project}/${name}`;
    } else {
      // Clear hash (lose focus on close).
      window.location.hash = "#";
    }
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
    Object.values(checks).forEach((check) => {
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
      (name) => html`
        <${Project}
          name="${name}"
          checks="${projects[name]}"
          fetchCheckResult="${this.fetchCheckResult}"
        />
      `
    );
  }

  render() {
    const { checks, results, focusedCheck, selectedTags } = this.state;

    const focusedCheckContext = {
      ...focusedCheck,
      setValue: this.setFocusedCheck,
    };

    const selectedTagsContext = {
      ...selectedTags,
      add: (t) => {
        this.setState({
          selectedTags: {
            tags: this.state.selectedTags.tags.concat([t]),
          },
        });
      },
      remove: (t) => {
        this.setState({
          selectedTags: {
            tags: this.state.selectedTags.tags.filter((s) => s != t),
          },
        });
      },
    };

    return html`
      <${FocusedCheck.Provider} value="${focusedCheckContext}">
        <${SelectedTags.Provider} value="${selectedTagsContext}">
          <${Overview} checks="${checks}" results="${results}" />
          <${TagListFilter} checks="${checks}" />
          ${this.renderProjects()}
        </${SelectedTags.Provider}>
      </${FocusedCheck.Provider}>
    `;
  }
}
