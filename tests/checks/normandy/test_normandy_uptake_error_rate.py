from checks.normandy.uptake_error_rate import run
from tests.utils import patch_async


MODULE = "checks.normandy.uptake_error_rate"

FAKE_ROWS = [
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "success",
        "source": "normandy/recipe/123",
        "total": 20000,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "apply_error",  # recipe_execution_error
        "source": "normandy/recipe/123",
        "total": 10000,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "download_error",  # recipe_invalid_action
        "source": "normandy/recipe/123",
        "total": 5000,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "backoff",  # recipe_didnt_match_filter
        "source": "normandy/recipe/123",
        "total": 4000,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "custom_2_error",  # recipe_didnt_match_filter in Fx 67
        "source": "normandy/recipe/123",
        "total": 1000,
    },
    {
        "min_timestamp": "2019-09-16T00:50:00",
        "max_timestamp": "2019-09-16T01:00:00",
        "status": "success",
        "source": "normandy/recipe/123",
        "total": 1000,
    },
    {
        "min_timestamp": "2019-09-16T00:50:00",
        "max_timestamp": "2019-09-16T01:00:00",
        "status": "apply_error",  # recipe_execution_error
        "source": "normandy/recipe/123",
        "total": 500,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "success",
        "source": "normandy/action/AddonStudyAction",
        "total": 9000,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "custom_2_error",
        "source": "normandy/action/AddonStudyAction",
        "total": 1000,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "success",
        "source": "normandy/runner",
        "total": 2000,
    },
    {
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T00:40:00",
        "status": "server_error",
        "source": "normandy/runner",
        "total": 500,
    },
    {
        "min_timestamp": "2019-09-16T00:50:00",
        "max_timestamp": "2019-09-16T01:00:00",
        "status": "success",
        "source": "normandy/runner",
        "total": 1000,
    },
]


async def test_positive():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(api_key="", max_error_percentage=100.0)

    assert status is True
    assert data == {
        "sources": {},
        "min_rate": 33.33,
        "max_rate": 37.5,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_negative():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(api_key="", max_error_percentage=0.1)

    assert status is False
    assert data == {
        "sources": {
            "recipe/123": {
                "error_rate": 37.5,
                "statuses": {
                    "success": 20000,
                    "recipe_didnt_match_filter": 5000,
                    "recipe_execution_error": 10000,
                    "recipe_invalid_action": 5000,
                },
                "ignored": {},
                "min_timestamp": "2019-09-16T00:30:00",
                "max_timestamp": "2019-09-16T00:40:00",
            }
        },
        "min_rate": 33.33,
        "max_rate": 37.5,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_ignore_status():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="",
            max_error_percentage=0.1,
            ignore_status=["recipe_execution_error", "recipe_invalid_action"],
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_rate": 0.0,
        "max_rate": 0.0,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_min_total_events():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", max_error_percentage=0.1, min_total_events=40001
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_rate": None,
        "max_rate": None,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_filter_on_action_uptake():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", sources=["action"], max_error_percentage=10
        )

    assert status is False
    assert data == {
        "sources": {
            "action/AddonStudyAction": {
                "error_rate": 10.0,
                "statuses": {"success": 9000, "action_post_execution_error": 1000},
                "ignored": {},
                "min_timestamp": "2019-09-16T00:30:00",
                "max_timestamp": "2019-09-16T00:40:00",
            }
        },
        "min_rate": 10.0,
        "max_rate": 10.0,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_filter_on_runner_uptake():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", sources=["runner"], max_error_percentage=0.1
        )

    assert status is False
    assert data == {
        "sources": {
            "runner": {
                "error_rate": 20.0,
                "statuses": {"success": 2000, "server_error": 500},
                "ignored": {},
                "min_timestamp": "2019-09-16T00:30:00",
                "max_timestamp": "2019-09-16T00:40:00",
            }
        },
        "min_rate": 0.0,
        "max_rate": 20.0,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }
