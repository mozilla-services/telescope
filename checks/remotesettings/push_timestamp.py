"""
The version number published on the Push server must match the Remote Settings
latest change timestamp.

Both values are returned.
"""
import json
import logging

import websockets

from poucave.typings import CheckResult
from poucave.utils import utcfromtimestamp

from .utils import KintoClient

BROADCAST_ID = "remote-settings/monitor_changes"

EXPOSED_PARAMETERS = ["remotesettings_server", "push_server"]


logger = logging.getLogger(__name__)


async def get_push_timestamp(uri) -> str:
    async with websockets.connect(uri) as websocket:
        logging.info(f"Send hello handshake to {uri}")
        data = {
            "messageType": "hello",
            "broadcasts": {BROADCAST_ID: "v0"},
            "use_webpush": True,
        }
        await websocket.send(json.dumps(data))
        body = await websocket.recv()
        response = json.loads(body)

    etag = response["broadcasts"][BROADCAST_ID]
    return etag[1:-1]  # strip quotes.


async def get_remotesettings_timestamp(uri) -> str:
    client = KintoClient(server_url=uri)
    return await client.get_records_timestamp(bucket="monitor", collection="changes")


async def run(remotesettings_server: str, push_server: str) -> CheckResult:
    rs_timestamp = await get_remotesettings_timestamp(remotesettings_server)
    push_timestamp = await get_push_timestamp(push_server)

    rs_datetime = utcfromtimestamp(rs_timestamp)
    push_datetime = utcfromtimestamp(push_timestamp)

    return (
        push_timestamp == rs_timestamp,
        {
            "push": {
                "timestamp": push_timestamp,
                "datetime": push_datetime.isoformat(),
            },
            "remotesettings": {
                "timestamp": rs_timestamp,
                "datetime": rs_datetime.isoformat(),
            },
        },
    )
