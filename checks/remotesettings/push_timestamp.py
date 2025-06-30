"""
The version number published on the Push server must match the Remote Settings
latest change timestamp.

Both values are returned.
"""

import json
import logging

import websockets

from telescope.typings import CheckResult
from telescope.utils import utcfromtimestamp, utcnow

from .utils import KintoClient


BROADCAST_ID = "remote-settings/monitor_changes"

EXPOSED_PARAMETERS = ["remotesettings_server", "push_server"]


logger = logging.getLogger(__name__)


async def get_push_timestamp(uri) -> str:
    async with websockets.connect(uri) as websocket:  # type: ignore
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
    return etag.strip('"')


async def get_remotesettings_timestamp(uri) -> str:
    client = KintoClient(server_url=uri)
    entries = await client.get_monitor_changes(bust_cache=True)

    # sort by timestamp desc as the records are returned by bucket/collection
    entries.sort(key=lambda e: e["last_modified"], reverse=True)

    # Some collections are excluded (eg. preview)
    # https://github.com/mozilla-services/cloudops-deployment/blob/master/projects/kinto/puppet/modules/kinto/templates/kinto.ini.erb
    matched = [e for e in entries if "preview" not in e["bucket"]]
    return str(matched[0]["last_modified"])


async def run(
    remotesettings_server: str, push_server: str, lag_margin: int = 600
) -> CheckResult:
    rs_timestamp = await get_remotesettings_timestamp(remotesettings_server)
    push_timestamp = await get_push_timestamp(push_server)

    rs_datetime = utcfromtimestamp(rs_timestamp)
    push_datetime = utcfromtimestamp(push_timestamp)

    return (
        # Fail if timestamps are different and data was published a while ago.
        rs_timestamp == push_timestamp or (utcnow() - rs_datetime).total_seconds() < lag_margin,
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
