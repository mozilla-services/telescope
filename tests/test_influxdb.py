from unittest import mock

import pytest

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


async def test_influxdb_does_not_send_plot_if_undefined(aiohttp_client):
    config.INFLUXDB_URL = "http://influxdb"

    check = Check(project="p", name="n", description="", module="tests.conftest")
    app = init_app(Checks([check]))
    await aiohttp_client(app)

    emitter = app["poucave.events"]

    with mock.patch("poucave.utils.InfluxDB.report") as mocked:
        emitter.emit(
            "check:run", payload={"check": check, "result": {"success": False}}
        )

    assert mocked.call_args_list == [
        mock.call(
            "check",
            fields={"success": False},
            tags={"project": "p", "name": "n"},
        )
    ]


async def test_influxdb_raises_if_defined_plot_is_not_basic_type(aiohttp_client):
    config.INFLUXDB_URL = "http://influxdb"

    check = Check(
        project="p", name="n", description="", module="tests.conftest", plot=".ping"
    )
    app = init_app(Checks([check]))
    await aiohttp_client(app)

    emitter = app["poucave.events"]
    event = {
        "check": check,
        "result": {
            "data": {"ping": [1, 3, 5]},
            "success": True,
        },
    }
    with pytest.raises(ValueError):
        emitter.emit("check:run", event)


def test_influxdb_client():
    influxDB = InfluxDB()

    with mock.patch.object(influxDB.api, "write") as mocked:
        influxDB.report("check", fields={"data": 12, "success": True}, tags={"t": "x"})

    assert mocked.call_args_list[0][1]["bucket"] == config.INFLUXDB_BUCKET
    assert (
        mocked.call_args_list[0][1]["record"].to_line_protocol()
        == "check,t=x data=12i,success=true"
    )
