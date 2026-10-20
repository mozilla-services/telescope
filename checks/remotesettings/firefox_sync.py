"""
A headless Firefox should be able to synchronize Remote Settings from the specified `server`.

The output of `RemoteSettings.inspect()` is returned.
"""

import asyncio
import os

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

from telescope import config
from telescope.typings import CheckResult


EXPOSED_PARAMETERS = ["server"]

# Executed in the privileged (chrome) context of the browser.
SYNC_SCRIPT = """
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


def sync_from_browser(server: str, timeout_seconds: int) -> dict:
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
            return driver.execute_async_script(SYNC_SCRIPT)
    finally:
        driver.quit()


async def run(server: str, timeout_seconds: int = 120) -> CheckResult:
    try:
        result = await asyncio.to_thread(sync_from_browser, server, timeout_seconds)
    except WebDriverException as e:
        return False, e.msg or str(e)
    return result["ok"], result
