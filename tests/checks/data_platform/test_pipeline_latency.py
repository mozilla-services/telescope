from checks.data_platform.pipeline_latency import run
from tests.utils import patch_async


MODULE = "checks.data_platform.pipeline_latency"

INPUT_ROWS = [
    {
        "timestamp": "2020-03-19T22:00:00",
        "value": 20,
        "component": "decoder_sub_unacked",
    },
    {
        "timestamp": "2020-03-19T22:00:00",
        "value": 20,
        "component": "decoder_watermark_age",
    },
    {
        "timestamp": "2020-03-19T21:00:00",
        "value": 50,
        "component": "decoder_sub_unacked",
    },
    {
        "timestamp": "2020-03-19T21:00:00",
        "value": 10,
        "component": "decoder_watermark_age",
    },
    {
        "timestamp": "2020-03-19T20:00:00",
        "value": 10,
        "component": "decoder_sub_unacked",
    },
    {
        "timestamp": "2020-03-19T20:00:00",
        "value": 10,
        "component": "decoder_watermark_age",
    },
    {
        "timestamp": "2020-03-19T19:00:00",
        "value": 10,
        "component": "decoder_sub_unacked",
    },
    {
        "timestamp": "2020-03-19T19:00:00",
        "value": 20,
        "component": "decoder_watermark_age",
    },
    {
        "timestamp": "2020-03-19T18:00:00",
        "value": 10,
        "component": "decoder_sub_unacked",
    },
    {
        "timestamp": "2020-03-19T18:00:00",
        "value": 0,
        "component": "decoder_watermark_age",
    },
]


async def test_success():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=35, value_count=4, max_over_rate=0.5
        )

        assert success
        assert data == {
            "results": {
                "2020-03-19T22:00:00": 40,
                "2020-03-19T21:00:00": 60,
                "2020-03-19T20:00:00": 20,
                "2020-03-19T19:00:00": 30,
            },
            "over_count": 2,
        }


async def test_max_threshold():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=20, value_count=4, max_over_rate=0.5
        )

        assert success is False
        assert len(data["results"]) == 4


async def test_value_count():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=35, value_count=2, max_over_rate=0.5
        )

        assert success is False
        assert len(data["results"]) == 2


async def test_max_over_rate():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=35, value_count=2, max_over_rate=0.3
        )

        assert success is False
        assert len(data["results"]) == 2
