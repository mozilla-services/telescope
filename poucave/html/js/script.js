const STATUS_LOADING = "Loading";
const STATUS_HEALTHY = "Healthy";
const STATUS_UNHEALTHY = "Unhealthy";

const COLOR_GRAY = "#acb0b8";
const COLOR_GREEN = "#5eba00";
const COLOR_RED = "#fa4654";

const CLASS_LOADING = "bg-gray";
const CLASS_SUCCESS = "bg-green";
const CLASS_FAILURE = "bg-red";

class Dashboard {
  constructor() {
    this.handleLoading = this.handleLoading.bind(this);
    this.handleUpdate = this.handleUpdate.bind(this);

    this.node = document.createElement("div");
    this.projects = {};
    this.overview = new Overview();

    this.initialize();
  }

  async initialize() {
    const response = await fetch("/checks");
    const checksData = await response.json();

    // Insert the overview
    this.node.appendChild(this.overview.node);

    // Check if the diagram exists and initialize
    try {
      await this.initializeDiagram();
    } catch (err) {
      this.overview.diagramCard.classList.add("d-none");
      console.warn("SVG diagram could not be found. Check out documentation.");
    }

    checksData
      .sort((a, b) => a.name < b.name ? -1 : 1)
      .forEach(data => {
        if (!(data.project in this.projects)) {
          const project = new Project(data.project);
          this.projects[data.project] = project;

          // Register update handler for the project
          project.registerLoadingHandler(this.handleLoading);
          project.registerUpdateHandler(this.handleUpdate);
        }

        const check = new Check(data);
        if (this.overview.diagramContentDocument) {
          check.linkIndicator(this.overview.findIndicatorElementForCheck(data.project, data.name));
        }
        this.projects[data.project].appendCheck(check);
      });

    // Sort projects and add them to the dashboard
    Object.keys(this.projects).sort().forEach(k => {
      this.node.appendChild(this.projects[k].node);
    });
  }

  initializeDiagram() {
    return new Promise((resolve, reject) => {
      // Check if the diagram exists and initialize
      const diagramSVG = this.overview.diagram;
      diagramSVG.addEventListener("error", () => {
        reject();
      });
      diagramSVG.addEventListener("load", () => {
        resolve();
      });
    });
  }

  isLoading() {
    let loading = false;
    Object.keys(this.projects).forEach(k => {
      loading |= this.projects[k].isLoading();
    });
    return loading;
  }

  isHealthy() {
    let healthy = true;
    Object.keys(this.projects).forEach(k => {
      healthy &= this.projects[k].isHealthy();
    });
    return healthy;
  }

  handleLoading() {
    const favicon = document.querySelector("link[rel*='icon']");
    favicon.href = "img/loading.png";
    this.overview.markLoading();
  }

  handleUpdate(check) {
    const favicon = document.querySelector("link[rel*='icon']");
    this.overview.setStatus(this.isHealthy() ? "healthy" : "unhealthy");
    if (this.isLoading()) {
      favicon.href = "img/loading.png";
      this.overview.markLoading();
    } else {
      favicon.href = this.isHealthy() ? "img/success.png" : "img/failure.png";
      this.overview.unmarkLoading();
    }
  }
}

class Overview {
  constructor() {
    this.node = document.getElementById("overview-template").content.cloneNode(true);
    this.diagram = this.node.querySelector("object");
    this.diagramCard = this.node.querySelector(".diagram-card");
    this.statusCard = this.node.querySelector(".overview-status-card");
  }

  get diagramContentDocument() {
    return this.diagram.contentDocument;
  }

  findIndicatorElementForCheck(project, name) {
    if (this.diagramContentDocument) {
      return this.diagramContentDocument.getElementById(`${project}--${name}`);
    }
    return null;
  }

  setStatus(status) {
    this.statusCard.innerHTML = "";
    const fragment = document.getElementById(`overview-${status}-fragment`).content.cloneNode(true);
    if (fragment) {
      this.statusCard.appendChild(fragment);
      const lastUpdated = this.statusCard.querySelector(".overview-last-updated");
      const timestamp = new Timestamp(new Date());
      timestamp.appendTo(lastUpdated);
    }
  }

  markLoading() {
    const options = this.diagramCard.querySelector(".card-options");
    if (!options.querySelector("i.fa.fa-spinner")) {
      const spinner = document.createElement("i");
      spinner.classList.add("fa", "fa-spinner", "fa-spin");
      this.diagramCard.querySelector(".card-options").appendChild(spinner);
    }
  }

  unmarkLoading() {
    this.diagramCard.querySelector(".card-options").innerHTML = "";
  }
}

class Project {
  constructor(name) {
    this.handleLoading = this.handleLoading.bind(this);
    this.handleUpdate = this.handleUpdate.bind(this);

    this.loadingHandlers = [];
    this.updateHandlers = [];
    this.name = name;
    this.checks = [];

    this.node = document.getElementById("project-template").content.cloneNode(true);
    this.projectStatus = this.node.querySelector(".project-status");

    this.cards = this.node.querySelector(".project-cards");

    // Populate data
    this.node.querySelector(".project-name").textContent = name;
  }

  registerLoadingHandler(handler) {
    this.loadingHandlers.push(handler);
  }

  registerUpdateHandler(handler) {
    this.updateHandlers.push(handler);
  }

  appendCheck(check) {
    this.checks.push(check);
    this.cards.appendChild(check.card.node);
    check.registerLoadingHandler(this.handleLoading);
    check.registerUpdateHandler(this.handleUpdate);
  }

  isLoading() {
    let loading = false;
    this.checks.forEach(c => {
      loading |= c.isLoading();
    });
    return loading;
  }

  isHealthy() {
    let healthy = true;
    this.checks.forEach(c => {
      healthy &= c.isHealthy();
    });
    return healthy;
  }

  updateHealthIndicator(cls, message) {
    this.projectStatus.innerHTML = "";

    const healthIndicator = document.createElement("span");
    healthIndicator.classList.add("badge", cls);
    healthIndicator.textContent = message;
    this.projectStatus.appendChild(healthIndicator);
  }

  handleLoading() {
    this.updateHealthIndicator(CLASS_LOADING, STATUS_LOADING);
    this.loadingHandlers.forEach(h => { h(); });
  }

  handleUpdate(check) {
    if (this.isLoading()) {
      this.updateHealthIndicator(CLASS_LOADING, STATUS_LOADING);
    } else {
      if (this.isHealthy()) {
        this.updateHealthIndicator(CLASS_SUCCESS, STATUS_HEALTHY)
      } else {
        this.updateHealthIndicator(CLASS_FAILURE, STATUS_UNHEALTHY)
      }
    }
    this.updateHandlers.forEach(h => { h(check); });
  }
}

class Check {
  constructor(data) {
    this.refresh = this.refresh.bind(this);
    this.refreshAndRequeue = this.refreshAndRequeue.bind(this);

    this._isLoading = false;
    this.loadingHandlers = [];
    this.updateHandlers = [];
    this.data = data;
    this.result = {};
    this.card = new Card(this);
    this.refreshTimeout = null;
    this.indicator = null;

    this.refreshAndRequeue();
  }

  registerLoadingHandler(handler) {
    this.loadingHandlers.push(handler);
  }

  registerUpdateHandler(handler) {
    this.updateHandlers.push(handler);
  }

  linkIndicator(indicator) {
    if (indicator) {
      this.indicator = indicator;
      indicator.setAttribute("cursor", "pointer");
      indicator.setAttribute("fill", COLOR_GRAY);

      // Add tooltip
      const titleElement = document.createElementNS("http://www.w3.org/2000/svg", "title");
      titleElement.textContent = `${this.data.project}/${this.data.name}:\n${this.data.description}`;
      indicator.appendChild(titleElement);

      // Make it clickable, scroll to section.
      indicator.addEventListener("click", () => {
        this.card.scrollIntoView();
      });
    }
  }

  async refreshAndRequeue() {
    await this.refresh();
    this.refreshTimeout = setTimeout(this.refreshAndRequeue, this.data.ttl * 1000);
  }
  
  async refresh(options = {}) {
    const { refreshSecret = null } = options;
    const domain = window.location.href.split('/')[2];
    const url = new URL(this.data.url, `${window.location.protocol}//${domain}`);
    if (refreshSecret) {
      url.searchParams.append("refresh", refreshSecret);
    }

    // Prepare the card
    this._isLoading = true;
    this.loadingHandlers.forEach(h => { h(); });
    this.card.markLoading();
    this.card.disableRefreshButton();
    if (this.indicator) {
      this.indicator.setAttribute("fill", COLOR_GRAY);
    }

    // Fetch the check result and update
    let response;
    try {
      response = await fetch(url.toString());
      this.result = await response.json();
    } catch (err) {
      if (response && /Invalid refresh secret/.test(response.statusText)) {
        // Forget about this refresh secret
        localStorage.removeItem("refresh-secret");
      }
      console.warn(this.data.project, this.data.name, err);
      this.result = {success: false, data: err.toString(), duration: 0};
    } finally {
      this._isLoading = false;
      this.card.enableRefreshButton();
      this.update();
    }
  }

  update() {
    this.card.update();
    if (this.indicator) {
      this.indicator.setAttribute("fill", this.isHealthy() ? COLOR_GREEN : COLOR_RED);
    }
    this.updateHandlers.forEach(h => { h(this); });
  }

  isLoading() {
    return this._isLoading;
  }

  isHealthy() {
    return this.result.success;
  }
}

class Card {
  constructor(check) {
    this.handleRefreshButtonClick = this.handleRefreshButtonClick.bind(this);

    this.check = check;

    this.node = document.getElementById("check-template").content.cloneNode(true);

    const card = this.node.querySelector(".card");
    this.card = card;
    this.tags = card.querySelector(".check-tags");
    this.parameters = card.querySelector(".check-parameters")
    this.refreshButton = card.querySelector("button.check-refresh");
    this.cardStatus = card.querySelector(".card-status");

    this.refreshButton.addEventListener("click", this.handleRefreshButtonClick);

    // Identify the card
    card.setAttribute("id", `${check.data.project}--${check.data.name}`);

    // Populate details
    this.renderTags();
    this.renderParameters();

    card.querySelector(".check-name").textContent = check.data.name;
    card.querySelector(".check-description").innerHTML = marked(check.data.description);
    card.querySelector(".check-documentation").innerHTML = marked(check.data.documentation);

    // Set link locations
    card.querySelector("a.check-url").setAttribute("href", check.data.url);
    card.querySelector("a.check-troubleshooting").setAttribute("href", check.data.troubleshooting);

    this.update();
  }

  update() {
    const result = this.check.result;
    const card = this.card;

    if (this.check.isHealthy()) {
      this.markSuccess();
    } else {
      this.markFailure();
    }

    card.querySelector(".check-result").textContent = JSON.stringify(result.data, null, 2);
    card.querySelector(".check-duration").textContent = result.duration;

    const date =  result.datetime ? new Date(result.datetime) : new Date();
    const dateTimeElem = card.querySelector(".check-datetime");
    dateTimeElem.innerHTML = "";
    const timestamp = new Timestamp(date);
    timestamp.appendTo(dateTimeElem);
  }

  renderParameters() {
    const allParameters = {
      ttl: this.check.data.ttl,
      ...this.check.data.parameters
    };
    const parameterList = document.createElement("ul");

    this.parameters.innerHTML = "";

    Object.keys(allParameters).forEach(k => {
      const parameter = document.createElement("li");
      parameter.textContent = `${k} = ${allParameters[k]}`;
      parameterList.appendChild(parameter);
    });

    this.parameters.appendChild(parameterList);
  }

  renderTags() {
    const tags = this.check.data.tags;

    this.tags.innerHTML = "";

    if (tags.length) {
      this.tags.classList.remove("d-none");
    } else {
      this.tags.classList.add("d-none");
    }

    tags.forEach(t => {
      const el = document.createElement("span");
      el.classList.add("badge", "bg-gray", "mr-1", "mb-1");
      el.textContent = t;
      this.tags.appendChild(el);
    });
  }

  handleRefreshButtonClick() {
    let refreshSecret = localStorage.getItem("refresh-secret");
    if (!refreshSecret) {
      refreshSecret = prompt("Refresh secret?");
      localStorage.setItem("refresh-secret", refreshSecret);
    }
    this.check.refresh();
  }

  clearStatus() {
    this.cardStatus.classList.remove(CLASS_FAILURE, CLASS_LOADING, CLASS_SUCCESS);
    this.refreshButton.querySelector(".fa").classList.remove("fa-spin");
  }

  markLoading() {
    this.clearStatus();
    this.cardStatus.classList.add(CLASS_LOADING);
    this.refreshButton.querySelector(".fa").classList.add("fa-spin");
  }

  markSuccess() {
    this.clearStatus();
    this.cardStatus.classList.add(CLASS_SUCCESS);
  }

  markFailure() {
    this.clearStatus();
    this.cardStatus.classList.add(CLASS_FAILURE);
  }

  disableRefreshButton() {
    this.refreshButton.disabled = true;
  }

  enableRefreshButton() {
    this.refreshButton.disabled = false;
  }

  scrollIntoView() {
    this.card.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
    const listener = () => {
      this.card.classList.remove("animate-blink");
      this.card.removeEventListener("animationend", listener);
    };
    this.card.addEventListener("animationend", listener);
    this.card.classList.add("animate-blink");
  }
}

class Timestamp {
  constructor(date) {
    this.refresh = this.refresh.bind(this);
    this.date = date;
    this.node = document.createElement("time");
    this.node.setAttribute("datetime", date.toISOString());
    this.node.setAttribute("title", date.toString());
  }

  refresh() {
    const now = new Date();
    const timedelta = Math.abs(now.getTime() - this.date.getTime());

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

    this.node.textContent = timeago().format(this.date);

    // If the node is no longer in the document stop recreating the timeout
    if (document.body.contains(this.node)) {
      setTimeout(this.refresh, timeoutDuration);
    }
  }

  appendTo(container) {
    container.appendChild(this.node);
    this.refresh();
  }
}


// Initialize the app on page load
window.addEventListener("load", () => {
  // Clear the main content area
  const main = document.getElementById("main");
  main.innerHTML = "";

  // Create and insert the dashboard
  const dashboard = new Dashboard();
  main.appendChild(dashboard.node);
});
