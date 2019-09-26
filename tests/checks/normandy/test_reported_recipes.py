from checks.normandy.reported_recipes import run
from tests.utils import patch_async

MODULE = "checks.normandy.reported_recipes"

FAKE_ROWS = [
    {
        "status": "success",
        "source": "normandy/recipe/123",
        "total": 20000,
        "min_timestamp": "2019-09-16T02:36:12.348",
        "max_timestamp": "2019-09-16T06:24:58.741",
    },
    {
        "status": "backoff",
        "source": "normandy/recipe/456",
        "total": 15000,
        "min_timestamp": "2019-09-16T03:36:12.348",
        "max_timestamp": "2019-09-16T05:24:58.741",
    },
    {
        "status": "apply_error",
        "source": "normandy/recipe/123",
        "total": 5000,
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    },
]


async def test_positive(mock_aioresponses):
    mock_aioresponses.get(
        "http://normandy/api/v1/recipe/signed/",
        payload=[{"recipe": {"id": 123}}, {"recipe": {"id": 456}}],
    )

    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(server="http://normandy", api_key="")

    assert status is True
    assert data == {
        "missing": [],
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_negative(mock_aioresponses):
    mock_aioresponses.get(
        "http://normandy/api/v1/recipe/signed/",
        payload=[
            {"recipe": {"id": 123}},
            {"recipe": {"id": 456}},
            {"recipe": {"id": 789}},
        ],
    )

    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(server="http://normandy", api_key="")

    assert status is False
    assert data == {
        "missing": [789],
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }
