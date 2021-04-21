from datetime import datetime

from checks.normandy.uptake_error_rate import NORMANDY_URL, run
from tests.utils import patch_async


NORMANDY_SERVER = "http://normandy"
MODULE = "checks.normandy.uptake_error_rate"

FAKE_ROWS = [
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "success",
        "source": "normandy/recipe/456",
        "channel": "release",
        "total": 20000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "success",
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 20000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "apply_error",  # recipe_execution_error
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 10000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "download_error",  # recipe_invalid_action
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 5000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "backoff",  # recipe_didnt_match_filter
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 4000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "custom_2_error",  # recipe_didnt_match_filter in Fx 67
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 1000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:50:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T01:00:00"),
        "status": "success",
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 1000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:50:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T01:00:00"),
        "status": "apply_error",  # recipe_execution_error
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 500,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "success",
        "source": "normandy/action/AddonStudyAction",
        "channel": "release",
        "total": 9000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "custom_2_error",
        "source": "normandy/action/AddonStudyAction",
        "channel": "release",
        "total": 1000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "success",
        "source": "normandy/runner",
        "channel": "release",
        "total": 2000,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:30:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T00:40:00"),
        "status": "server_error",
        "source": "normandy/runner",
        "channel": "release",
        "total": 500,
    },
    {
        "min_timestamp": datetime.fromisoformat("2019-09-16T00:50:00"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T01:00:00"),
        "status": "success",
        "source": "normandy/runner",
        "channel": "release",
        "total": 1000,
    },
]

RECIPE = {
    "id": 123,
    "name": "un dos tres",
    "filter_expression": "",
}


async def test_positive(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[{"recipe": RECIPE}],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=100.0,
            channels=["release"],
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_rate": 33.33,
        "max_rate": 37.5,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_negative(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[{"recipe": RECIPE}],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=0.1,
            channels=["release"],
        )

    assert status is False
    assert data == {
        "sources": {
            "recipe/123": {
                "error_rate": 37.5,
                "name": "un dos tres",
                "with_telemetry": False,
                "with_classify_client": False,
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


async def test_ignore_status(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[{"recipe": RECIPE}],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=0.1,
            ignore_status=["recipe_execution_error", "recipe_invalid_action"],
            channels=["release"],
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_rate": 0.0,
        "max_rate": 0.0,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_ignore_disabled_recipes(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[{"recipe": {**RECIPE, "id": 456}}],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=0.1,
            channels=["release"],
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_rate": 0.0,
        "max_rate": 0.0,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_min_total_events(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[{"recipe": RECIPE}],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=0.1,
            min_total_events=40001,
            channels=["release"],
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_rate": None,
        "max_rate": None,
        "min_timestamp": "2019-09-16T00:30:00",
        "max_timestamp": "2019-09-16T01:00:00",
    }


async def test_filter_on_action_uptake(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[{"recipe": RECIPE}],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            sources=["action"],
            server=NORMANDY_SERVER,
            max_error_percentage=10,
            channels=["release"],
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


async def test_filter_on_runner_uptake(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[{"recipe": RECIPE}],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            sources=["runner"],
            server=NORMANDY_SERVER,
            max_error_percentage=0.1,
            channels=["release"],
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


async def test_error_rate_with_classify(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[
            {"recipe": {**RECIPE, "filter_expression": '(normandy.country in ["US"])'}}
        ],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=0.1,
        )

    assert status is False
    assert data["sources"]["recipe/123"]["with_classify_client"]


async def test_error_rate_with_telemetry(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[
            {
                "recipe": {
                    **RECIPE,
                    "filter_expression": "(normandy.telemetry.main.sum > 0)",
                }
            }
        ],
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=0.1,
        )

    assert status is False
    assert data["sources"]["recipe/123"]["with_telemetry"]


async def test_error_rate_with_classifyclient_and_telemetry(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER),
        payload=[
            {
                "recipe": {
                    **RECIPE,
                    "filter_expression": (
                        '(normandy.country in ["US"]) &&'
                        "(normandy.telemetry.main.sum > 0)"
                    ),
                }
            }
        ],
    )
    max_error_percentage = {
        "default": 0.1,
        "with_classify_client": 20,
        "with_telemetry": 30,
    }
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            server=NORMANDY_SERVER,
            max_error_percentage=max_error_percentage,
        )

    assert status is False
    assert data["sources"]["recipe/123"]["error_rate"] == 37.5
    assert data["sources"]["recipe/123"]["with_telemetry"]
    assert data["sources"]["recipe/123"]["with_classify_client"]
