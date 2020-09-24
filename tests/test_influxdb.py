from unittest import mock

from poucave import config
from poucave.app import Check, Checks, init_app
from poucave.utils import InfluxDB


async def test_sends_influxdb(aiohttp_client):
    config.INFLUXDB_URL = "http://influxdb"

    check = Check(
        project="p", name="n", description="", module="tests.conftest", plot=".max_age"
    )
    app = init_app(Checks([check]))
    await aiohttp_client(app)

    emitter = app["poucave.events"]
    event = {
        "check": check,
        "result": {
            "data": {"max_age": 12},
            "success": True,
        },
    }

    with mock.patch("poucave.utils.InfluxDB.report") as mocked:
        emitter.emit("check:run", event)

    assert mocked.call_args_list == [
        mock.call(
            "check",
            fields={"success": True, "data": 12},
            tags={"project": "p", "name": "n"},
        )
    ]


def test_influxdb_client():
    influxDB = InfluxDB()

    with mock.patch.object(influxDB.api, "write") as mocked:
        influxDB.report("check", fields={"a": 12}, tags={"t": "x"})

    assert mocked.call_args_list[0][1]["bucket"] == config.INFLUXDB_BUCKET
    assert mocked.call_args_list[0][1]["record"].to_line_protocol() == "check,t=x a=12i"
