window.addEventListener('load', main);

async function main () {
  const checks = await fetchChecks();

  renderChecks(checks);

  await Promise.all(checks.map(async check => {
    let result;
    try {
      const resp = await fetch(check.url)
      result = await resp.json();
    } catch (e) {
      console.warn(check.project, check.name, e);
      result = {success: false, data: e.toString()};
    }
    renderResult(check, result);
  }));
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

    for(const check of checksByProject[project]) {
      const section = tpl.content.cloneNode(true);
      section.querySelector("section").setAttribute("id", `${check.project}-${check.name}`);
      section.querySelector("h1").textContent = check.name;
      section.querySelector("p.documentation").innerHTML = check.documentation.replace("\n\n", "<br/><br/>");
      section.querySelector("p.description").textContent = check.description;

      main.appendChild(section);
    }
  }
}

function renderResult(check, result) {
  const section = document.querySelector(`section#${check.project}-${check.name}`);
  section.classList.add(result.success ? "success" : "failure");
  section.querySelector("h1").classList.remove("blink");
  section.querySelector(".datetime").textContent = result.datetime;
  section.querySelector("pre.result").textContent = JSON.stringify(result.data, null, 2);
}

async function fetchChecks() {
  const resp = await fetch("/checks");
  const checks = await resp.json();
  return checks;
}
