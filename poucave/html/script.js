window.addEventListener('load', main);

async function main () {
  const resp = await fetch("/checks");
  const checks = await resp.json();

  renderChecks(checks);

  checks.map(refreshCheck);
}

async function refreshCheck(check, options = {}) {
  const { manual = false } = options;

  const favicon = document.querySelector("link[rel*='icon']");
  const section = document.querySelector(`section#${check.project}-${check.name}`);

  // If refreshed manually, we should provide the refresh secret.
  let refresh = null;
  if (manual) {
    refresh = localStorage.getItem("refresh-secret");
    if (!refresh) {
      refresh = prompt("Refresh secret?");
      localStorage.setItem("refresh-secret", refresh);
    }
  }

  // Clear potential previous result.
  section.className = "";
  section.querySelector(".datetime").textContent = "";
  section.querySelector("pre.result").textContent = "";

  // Show as loading...
  section.classList.add("loading");
  section.querySelector("button.refresh").disabled = true;
  favicon.href = "loading.png";

  const result = await fetchCheck(check, { refresh });

  // Show result!
  section.classList.add(result.success ? "success" : "failure");
  section.classList.remove("loading");
  section.querySelector("button.refresh").disabled = false;
  section.querySelector(".datetime").setAttribute("title", result.datetime);
  section.querySelector(".datetime").textContent = timeago().format(new Date(result.datetime));
  section.querySelector("pre.result").textContent = JSON.stringify(result.data, null, 2);
  section.querySelector(".duration").textContent = result.duration;

  // Refresh favicon based on success.
  const allSuccess = document.querySelectorAll("section.failure").length == 0;
  favicon.href = allSuccess ? "success.png" : "failing.png";

  if (!manual) {
    // When refreshed manually, we don't want to spin a new timer.
    setTimeout(refreshCheck.bind(null, check), check.ttl * 1000);
  }
}

async function fetchCheck(check, options = {}) {
  const { refresh = null } = options;
  const qs = refresh ? `?refresh=${encodeURIComponent(refresh)}` : "";
  let resp;
  try {
    resp = await fetch(check.url + qs);
    return await resp.json();
  } catch (e) {
    if (resp && /Invalid refresh secret/.test(resp.statusText)) {
      // Forget about this refresh secret
      localStorage.removeItem("refresh-secret");
    }
    console.warn(check.project, check.name, e);
    return {success: false, data: e.toString(), duration: 0};
  }
}

function renderChecks(checks) {
  const checksByProject = checks.reduce((acc, check) => {
    if (!(check.project in acc)) {
      acc[check.project] = [];
    }
    acc[check.project].push(check);
    return acc;
  }, {});


  const tpl = document.getElementById("check-tpl");

  const main = document.getElementById("main");
  main.innerHTML = "";

  for(const project of Object.keys(checksByProject)) {
    const title = document.createElement("h1");
    title.textContent = project;
    main.appendChild(title);

    const grid = document.createElement("div");

    for(const check of checksByProject[project]) {
      const allParameters = { ttl: check.ttl, ...check.parameters };
      const parameters = Object.keys(allParameters).map(k => `- ${k} = ${allParameters[k]}`).join("<br/>");

      const section = tpl.content.cloneNode(true);
      section.querySelector("section").setAttribute("id", `${check.project}-${check.name}`);
      section.querySelector(".name").textContent = check.name;
      section.querySelector("a.url").setAttribute("href", check.url);
      section.querySelector("p.tags").innerHTML = check.tags.map(t => `<span>${t}</span>`).join(" ");
      section.querySelector("p.description").innerHTML = marked(check.description);
      section.querySelector("p.parameters").innerHTML = parameters;
      section.querySelector("p.documentation").innerHTML = marked(check.documentation);
      section.querySelector("button.refresh").addEventListener("click", refreshCheck.bind(null, check, { manual: true }));
      section.querySelector("a.troubleshooting").setAttribute("href", check.troubleshooting);

      grid.appendChild(section);
    }

    main.appendChild(grid);
  }
}
