from unittest import mock

import pytest
from selenium.common.exceptions import WebDriverException

from checks.remotesettings.firefox_sync import run


MODULE = "checks.remotesettings.firefox_sync"


@pytest.fixture
def mocked_driver():
    with mock.patch(f"{MODULE}.webdriver.Firefox") as mocked:
        yield mocked.return_value


async def test_positive(mocked_driver):
    mocked_driver.execute_async_script.return_value = {
        "ok": True,
        "error": None,
        "inspect": {"serverTimestamp": 42},
    }

    status, data = await run("http://server.local/v1")

    assert status is True
    assert data["inspect"] == {"serverTimestamp": 42}
    mocked_driver.set_script_timeout.assert_called_with(120)
    mocked_driver.quit.assert_called_once()


async def test_negative(mocked_driver):
    mocked_driver.execute_async_script.return_value = {
        "ok": False,
        "error": "InvalidSignatureError: Invalid content signature (main/foo)",
        "inspect": {"serverTimestamp": 42},
    }

    status, data = await run("http://server.local/v1")

    assert status is False
    assert data["error"].startswith("InvalidSignatureError")
    mocked_driver.quit.assert_called_once()


async def test_negative_webdriver_error(mocked_driver):
    mocked_driver.execute_async_script.side_effect = WebDriverException("Timed out")

    status, data = await run("http://server.local/v1")

    assert status is False
    assert data == "Timed out"
    mocked_driver.quit.assert_called_once()


async def test_browser_options():
    with (
        mock.patch(f"{MODULE}.webdriver.Firefox") as mocked_firefox,
        mock.patch(f"{MODULE}.Service") as mocked_service,
    ):
        mocked_firefox.return_value.execute_async_script.return_value = {"ok": True}

        await run("http://server.local/v1")

    options = mocked_firefox.call_args.kwargs["options"]
    assert "-headless" in options.arguments
    assert options.preferences["services.settings.server"] == "http://server.local/v1"
    env = mocked_service.call_args.kwargs["env"]
    assert env["MOZ_REMOTE_ALLOW_SYSTEM_ACCESS"] == "1"
    assert env["MOZ_REMOTE_SETTINGS_DEVTOOLS"] == "1"


async def test_positive_rust(mocked_driver):
    mocked_driver.execute_async_script.return_value = {
        "ok": True,
        "error": None,
        "synced": ["search-config-v2"],
        "collections": {
            "search-config-v2": {"lastModified": 42, "records": 158},
        },
    }

    status, data = await run("http://server.local/v1", client="rust")

    assert status is True
    assert data["collections"]["search-config-v2"]["records"] == 158
    script, collections = mocked_driver.execute_async_script.call_args.args
    assert "RustSharedRemoteSettingsService" in script
    assert collections == ["search-config-v2"]


async def test_negative_rust(mocked_driver):
    mocked_driver.execute_async_script.return_value = {
        "ok": False,
        "error": "Error: reason: Error in network response: status code: 406",
    }

    status, data = await run(
        "http://server.local/v1", client="rust", collections=["foo"]
    )

    assert status is False
    assert data["error"].startswith("Error: reason")
    _, collections = mocked_driver.execute_async_script.call_args.args
    assert collections == ["foo"]


async def test_unknown_client(mocked_driver):
    with pytest.raises(ValueError, match="Unknown client 'kotlin'"):
        await run("http://server.local/v1", client="kotlin")

    mocked_driver.execute_async_script.assert_not_called()
