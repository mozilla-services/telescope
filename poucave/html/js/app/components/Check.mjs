import { Component, html } from "../../htm_preact.mjs";

import CheckDetails from "./CheckDetails.mjs";
import Markdown from "./Markdown.mjs";

export default class Check extends Component {
  constructor() {
    super();

    this.state = {
      detailsOpened: false,
    };

    this.handleRefreshButtonClick = this.handleRefreshButtonClick.bind(this);
    this.handleToggleDetails = this.handleToggleDetails.bind(this);
    this.onKeyDown = this.onKeyDown.bind(this);
  }

  componentDidMount() {
    document.body.addEventListener("keydown", this.onKeyDown);
  }

  componentWillUnmount() {
    document.body.removeEventListener("keydown", this.onKeyDown);
  }

  onKeyDown(ev) {
    if (ev.key == "Escape") {
      this.setState({ detailsOpened: false });
    }
  }

  componentDidUpdate(prevProps) {
    const { project, name } = this.props.focusedCheckContext;
    const { project: prevProject, name: prevName } = prevProps.focusedCheckContext;
    const { data } = this.props;

    const focusChanged = prevProject !== project || prevName !== name;

    if (focusChanged) {
      this.setState({
        detailsOpened: project === data.project && name === data.name,
      });
    }
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
      <div class="card-header cursor-pointer" onClick=${this.handleToggleDetails}>
        <h4 class="card-title check-name">${data.name}</h4>
        <div class="card-options">
          <span class="ml-3" href="#" title="Show more details">
            <i class="fa fa-eye" />
          </span>
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

  render({ data, result, fetchCheckResult }) {
    return html`
      <div
        class="check-card card"
        id="check--${data.project}--${data.name}"
      >
        ${this.renderHeader()}
        ${this.renderBody()}
        <${CheckDetails}
          data=${data}
          result=${result}
          opened=${this.state.detailsOpened}
          onClickCloseButton=${this.handleToggleDetails}
          fetchCheckResult=${fetchCheckResult}
        />
      </div>
    `;
  }

  handleToggleDetails(ev) {
    ev.preventDefault();
    const { detailsOpened } = this.state;
    this.setState({ detailsOpened: !detailsOpened });
  }
}
