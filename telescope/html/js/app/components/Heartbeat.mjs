import { Component, html } from "../../htm_preact.min.mjs";
import { ROOT_URL, RETRY_INTERVAL } from "../constants.mjs";

export default class Heartbeat extends Component {
  constructor() {
    super();
    this.refresh = this.refresh.bind(this);
    this.timeoutId = null;
    this.url = new URL("/__heartbeat__", ROOT_URL);
    this.state = {
      // idle | loading | success | failure
      status: "idle",
      checks: {},
    };
  }

  componentDidMount() {
    this.refresh();
  }

  componentWillUnmount() {
    clearTimeout(this.timeoutId);
  }

  async refresh() {
    // Only show the loading state on first fetch, to avoid flickering on polls.
    if (this.state.status == "idle") {
      this.setState({ status: "loading" });
    }
    try {
      const response = await fetch(this.url.toString());
      const checks = await response.json();
      this.setState({ status: response.ok ? "success" : "failure", checks });
    } catch (e) {
      console.warn(e);
      this.setState({
        status: "failure",
        checks: { heartbeat: "unreachable" },
      });
    }
    this.timeoutId = setTimeout(this.refresh, RETRY_INTERVAL);
  }

  render() {
    const { status, checks } = this.state;
    const isPending = status == "idle" || status == "loading";

    // Some heartbeat checks are only informational and don't fail the endpoint.
    const failing = Object.entries(checks).filter(([, v]) => v != "ok");

    let color;
    if (isPending) {
      color = "text-gray";
    } else if (status == "failure") {
      color = "text-red";
    } else if (failing.length > 0) {
      color = "text-yellow";
    } else {
      color = "text-green";
    }

    const details = isPending
      ? ["Loading..."]
      : Object.entries(checks).map(([k, v]) => `${k}: ${v}`);
    const title = ["Heartbeat", ...details].join("\n");

    return html`
      <a
        class="heartbeat ${color}"
        href="${this.url.toString()}"
        target="_blank"
        title="${title}"
      >
        <i class="fa fa-circle"></i>
      </a>
    `;
  }
}
