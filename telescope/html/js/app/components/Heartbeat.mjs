import { Component, html } from "../../htm_preact.min.mjs";
import { ROOT_URL, RETRY_INTERVAL } from "../constants.mjs";

export default class Heartbeat extends Component {
  constructor() {
    super();
    this.refresh = this.refresh.bind(this);
    this.timeoutId = null;
    this.url = new URL("/__heartbeat__", ROOT_URL);
    this.state = {
      isLoading: true,
      ok: false,
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
    try {
      const response = await fetch(this.url.toString());
      const checks = await response.json();
      this.setState({ isLoading: false, ok: response.ok, checks });
    } catch (e) {
      console.warn(e);
      this.setState({
        isLoading: false,
        ok: false,
        checks: { heartbeat: "unreachable" },
      });
    }
    this.timeoutId = setTimeout(this.refresh, RETRY_INTERVAL);
  }

  render() {
    const { isLoading, ok, checks } = this.state;

    // Some heartbeat checks are only informational and don't fail the endpoint.
    const failing = Object.entries(checks).filter(([, v]) => v != "ok");

    let color;
    if (isLoading) {
      color = "text-gray";
    } else if (!ok) {
      color = "text-red";
    } else if (failing.length > 0) {
      color = "text-yellow";
    } else {
      color = "text-green";
    }

    const details = isLoading
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
