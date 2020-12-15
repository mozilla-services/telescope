import { Component, html } from "../../htm_preact.mjs";

import CheckDetails from "./CheckDetails.mjs";
import Markdown from "./Markdown.mjs";

export default class Check extends Component {
  constructor() {
    super();
    this.cardRef = {};
    this.state = {
      focused: false,
      detailsOpened: false,
    };
    this.handleAnimationEnd = this.handleAnimationEnd.bind(this);
    this.handleRefreshButtonClick = this.handleRefreshButtonClick.bind(this);
    this.handleToggleDetails = this.handleToggleDetails.bind(this);
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
          <a class="check-url" title="Open check API data" href="${data.url}" target="_blank">
            <i class="fa fa-sm fa-external-link-alt" />
          </a>
          <a class="ml-3" href="#" title="Show more details" onClick=${this.handleToggleDetails}>
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

  render({ data, result, fetchCheckResult }) {
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
