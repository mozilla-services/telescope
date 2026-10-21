"""
A headless Firefox should be able to synchronize Remote Settings from the specified `server`.

With the `js` client, the output of `RemoteSettings.inspect()` is returned.
With the `rust` client, the specified `collections` are synchronized using the
shared Rust service, along with those registered by Firefox itself. The timestamp
and number of records of every synchronized collection are returned.
"""

import asyncio
import os

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

from telescope import config
from telescope.typings import CheckResult


EXPOSED_PARAMETERS = ["server", "client", "collections"]

# Scripts are executed in the privileged (chrome) context of the browser.
JS_SYNC_SCRIPT = """
const resolve = arguments[arguments.length - 1];
const { RemoteSettings } = ChromeUtils.importESModule(
  "resource://services-settings/remote-settings.sys.mjs"
);
(async () => {
  let error = null;
  try {
    await RemoteSettings.pollChanges({ trigger: "manual" });
  } catch (e) {
    error = `${e.name}: ${e.message}`;
  }
  let inspect = null;
  try {
    inspect = await RemoteSettings.inspect();
  } catch (e) {
    error = error || `${e.name}: ${e.message}`;
  }
  resolve({ ok: error === null, error, inspect });
})();
"""

RUST_SYNC_SCRIPT = """
const resolve = arguments[arguments.length - 1];
const [names] = arguments;
const { SharedRemoteSettingsService } = ChromeUtils.importESModule(
  "resource://gre/modules/RustSharedRemoteSettingsService.sys.mjs"
);
(async () => {
  try {
    const service = SharedRemoteSettingsService.rustService();
    const clients = {};
    for (const name of names) {
      clients[name] = await service.makeClient(name);
    }
    // Synchronizes our clients, and those created by Firefox itself.
    const synced = await service.sync();
    const collections = {};
    for (const name of synced) {
      const client = clients[name] ?? (await service.makeClient(name));
      const records = await client.getRecords(false);
      collections[name] = {
        lastModified: await client.getLastModifiedTimestamp(),
        records: records?.length ?? null,
      };
    }
    const missing = names.filter(name => !synced.includes(name));
    const error = missing.length ? `Not synchronized: ${missing.join(", ")}` : null;
    resolve({ ok: error === null, error, synced, collections });
  } catch (e) {
    resolve({ ok: false, error: `${e.name}: ${e.message}` });
  }
})();
"""

SCRIPTS = {"js": JS_SYNC_SCRIPT, "rust": RUST_SYNC_SCRIPT}


def sync_from_browser(
    server: str, script: str, args: list, timeout_seconds: int
) -> dict:
    options = Options()
    options.binary_location = config.FIREFOX_BINARY_PATH
    options.add_argument("-headless")
    options.set_preference("services.settings.server", server)
    options.set_preference("services.settings.loglevel", "debug")
    service = Service(
        executable_path=config.GECKODRIVER_BINARY_PATH,
        env={
            **os.environ,
            # Allow executing scripts in the privileged (chrome) context.
            "MOZ_REMOTE_ALLOW_SYSTEM_ACCESS": "1",
            # Allow overriding the server URL in release builds.
            "MOZ_REMOTE_SETTINGS_DEVTOOLS": "1",
        },
    )
    driver = webdriver.Firefox(options=options, service=service)
    try:
        driver.set_script_timeout(timeout_seconds)
        with driver.context(driver.CONTEXT_CHROME):
            return driver.execute_async_script(script, *args)
    finally:
        driver.quit()


async def run(
    server: str,
    client: str = "js",
    collections: list[str] = ["search-config-v2"],
    timeout_seconds: int = 120,
) -> CheckResult:
    if client not in SCRIPTS:
        raise ValueError(f"Unknown client {client!r}")

    args = [collections] if client == "rust" else []
    try:
        result = await asyncio.to_thread(
            sync_from_browser, server, SCRIPTS[client], args, timeout_seconds
        )
    except WebDriverException as e:
        return False, e.msg or str(e)
    return result["ok"], result
