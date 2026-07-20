from unittest import mock

import pytest
from aiointercept import CallbackResult

from checks.remotesettings.compression_dictionaries import (
    BAD_DICT_ID,
    MANIFEST_URL_PATTERN,
    UNKNOWN_DICT_ID,
    run,
)
from telescope.utils import utcnow


MODULE = "checks.remotesettings.compression_dictionaries"

SERVER_URL = "http://fake.local/v1"
BASE_URL = "http://cdn/"
FAKE_AUTH = "Bearer abc"

BID, CID, RID = "bid", "cid", "rid1"

LATEST_NAME = "rid1-v2.bin"
OLD_NAME = "rid1-v1.bin"
LATEST_LOCATION = f"{BID}/{CID}/{LATEST_NAME}"
OLD_LOCATION = f"{BID}/{CID}/{OLD_NAME}"
MIMETYPE = "application/octet-stream"

TARGET_URL = BASE_URL + LATEST_LOCATION
EXPECTED_UAD = f'match="/{BID}/{CID}/*--{RID}--*", id="{LATEST_NAME}", type=raw'

CHANGESET_URL = SERVER_URL + f"/buckets/{BID}/collections/{CID}/changeset"
HISTORY_URL = SERVER_URL + f"/buckets/{BID}/history"

DICT_FETCH_HEADERS = {"Accept-Encoding": "dcz", "Dictionary-ID": f'"{OLD_NAME}"'}
MANIFEST_URL = MANIFEST_URL_PATTERN.format(bid=BID, cid=CID, realm="nonprod", env="dev")


def make_cdn_callback(**hooks):
    """
    Build a CDN HEAD callback, based on the request,
    and allowing to override the response for given scenarios.
    """

    def callback(url, headers={}, **kwargs):
        accept = headers.get("Accept-Encoding", "")
        dict_id = headers.get("Dictionary-ID")

        situation = "dict_fetch"
        if dict_id is None:
            situation = "first_fetch"
        if "dcz" not in accept:
            situation = "plain"
        if dict_id == UNKNOWN_DICT_ID:
            situation = "unknown_dict"
        if dict_id == LATEST_NAME:
            situation = "same_target"
        if dict_id == BAD_DICT_ID:
            situation = "bad_dict_id"

        if situation in hooks:
            return hooks[situation]

        if situation == "plain":
            # No `Content-Encoding: dcz`, no `Use-As-Dictionary`.
            return CallbackResult(status=200, headers={"Content-Length": "1000"})

        if situation == "dict_fetch":
            # Subsequent download, dcz encoded, with `Use-As-Dictionary` for the next.
            return CallbackResult(
                status=200,
                headers={
                    "Content-Encoding": "dcz",
                    "Content-Length": "500",
                    "Use-As-Dictionary": EXPECTED_UAD,
                },
                content_type=MIMETYPE,
            )

        # Unless overridden, all other situations should advertise the dictionary
        # and serve the plain (uncompressed) attachment as a fallback.
        return CallbackResult(
            status=200,
            headers={"Use-As-Dictionary": EXPECTED_UAD, "Content-Length": "1000"},
        )

    return callback


@pytest.fixture
def mock_fetch_signed_resources():
    with mock.patch(
        f"{MODULE}.fetch_signed_resources",
        return_value=[{"source": {"bucket": BID, "collection": CID}}],
    ) as mocked:
        yield mocked


@pytest.fixture
def run_check(mock_aioresponses, mock_fetch_signed_resources, monkeypatch):
    """
    All the default responses and callbacks cover the positive case.

    In the tests below, we will either:
    - overwrite default `mock_aioresponses` for basic server responses
    - inject CDN responses in different situations via `make_cdn_callback()`
    """
    mock_aioresponses.get(
        MANIFEST_URL,
        payload={LATEST_NAME: [OLD_NAME]},
        repeat=True,
    )

    mock_aioresponses.get(
        SERVER_URL + "/",
        payload={"capabilities": {"attachments": {"base_url": BASE_URL}}},
        repeat=True,
    )
    mock_aioresponses.get(
        CHANGESET_URL,
        payload={
            "metadata": {
                "bucket": BID,
                "id": CID,
                "flags": ["compression-dictionaries"],
            },
            "changes": [{"id": RID}],
        },
        repeat=True,
    )
    mock_aioresponses.get(
        HISTORY_URL,
        payload={
            "data": [
                {
                    "last_modified": 1544035467383,
                    "target": {
                        "data": {
                            "id": RID,
                            "attachment": {"location": location, "mimetype": MIMETYPE},
                        }
                    },
                }
                for location in [LATEST_LOCATION, OLD_LOCATION]
            ]
        },
        repeat=True,
    )
    mock_aioresponses.head(BASE_URL + "bid/cid/unknown.jpeg", status=404, repeat=True)

    async def _run(*, cdn_callback_hooks={}, **kwargs):
        cdn_callback = make_cdn_callback(**cdn_callback_hooks)
        mock_aioresponses.head(TARGET_URL, callback=cdn_callback, repeat=True)
        return await run(SERVER_URL, FAKE_AUTH, **kwargs)

    return _run


async def test_positive(run_check):
    status, data = await run_check()

    assert status is True
    assert data == {}


async def test_positive_no_collection_with_cdt_flag(mock_aioresponses, run_check):
    mock_aioresponses.get(
        CHANGESET_URL,
        payload={
            "metadata": {"bucket": BID, "id": CID, "flags": []},
            "changes": [],
        },
        repeat=True,
    )
    status, data = await run_check()

    assert status is True
    assert data == {}


async def test_positive_stops_after_max_pairs(mock_aioresponses, run_check):
    mock_aioresponses.get(
        MANIFEST_URL,
        payload={LATEST_NAME: [OLD_NAME]},
        repeat=True,
    )
    mock_aioresponses.get(
        HISTORY_URL,
        payload={
            "data": [
                {
                    "last_modified": 1544035570000,
                    "target": {
                        "data": {
                            "id": RID,
                            "attachment": {"location": location, "mimetype": MIMETYPE},
                        }
                    },
                }
                for location in [
                    LATEST_LOCATION,
                    OLD_LOCATION,
                    "bid/cid/older-ignored.bin",
                ]
            ]
        },
        repeat=True,
    )

    status, data = await run_check(max_pairs=1)

    assert status is True
    assert data == {}


async def test_positive_if_missing_is_recent(mock_aioresponses, run_check):
    mock_aioresponses.get(
        MANIFEST_URL,
        payload={LATEST_NAME: [OLD_NAME]},
        repeat=True,
    )
    mock_aioresponses.get(
        HISTORY_URL,
        payload={
            "data": [
                {
                    "last_modified": timestamp,
                    "target": {
                        "data": {
                            "id": RID,
                            "attachment": {"location": location, "mimetype": MIMETYPE},
                        }
                    },
                }
                for timestamp, location in [
                    (
                        utcnow().timestamp() * 1000 - 100_000,
                        "bid/cid/newer-ignored.bin",
                    ),
                    (1544035570000, LATEST_LOCATION),
                    (1544035470000, OLD_LOCATION),
                ]
            ]
        },
        repeat=True,
    )

    status, data = await run_check(lag_margin_seconds=100)

    assert status is True
    assert data == {}


async def test_negative_missing_pair_in_manifest(mock_aioresponses, run_check):
    mock_aioresponses.get(MANIFEST_URL, payload={}, repeat=True)

    status, data = await run_check()

    assert status is False
    assert data == {
        "missing_pairs": {
            f"{BID}/{CID}": [
                (
                    {
                        "location": LATEST_LOCATION,
                        "mimetype": MIMETYPE,
                    },
                    {"location": OLD_LOCATION, "mimetype": MIMETYPE},
                )
            ]
        }
    }


async def test_negative_unreachable_url(run_check):
    status, data = await run_check(
        cdn_callback_hooks={"plain": CallbackResult(status=404)}
    )

    assert status is False
    assert data == {"unreachable_url": [TARGET_URL]}


async def test_negative_unreachable_first_dcz(run_check):
    status, data = await run_check(
        cdn_callback_hooks={"first_fetch": CallbackResult(status=404)}
    )

    assert status is False
    assert data == {"unreachable_first_dcz": [TARGET_URL]}


async def test_negative_bad_first_use_as_dict(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "first_fetch": CallbackResult(
                status=200,
                headers={"Use-As-Dictionary": "wrong", "Content-Length": "1000"},
            )
        }
    )

    assert status is False
    assert data == {"bad_first_use_as_dict": [(TARGET_URL, "wrong")]}


async def test_negative_missing_first_use_as_dict(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "first_fetch": CallbackResult(
                status=200, headers={"Content-Length": "1000"}
            )
        }
    )

    assert status is False
    assert data == {"missing_first_use_as_dict": [TARGET_URL]}


async def test_negative_missing_fallback(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "unknown_dict": CallbackResult(
                status=500, headers={"Use-As-Dictionary": EXPECTED_UAD}
            )
        }
    )

    assert status is False
    assert data == {"missing_fallback": [TARGET_URL]}


async def test_negative_unexpected_dcz_fallback(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "unknown_dict": CallbackResult(
                status=200,
                headers={
                    "Content-Encoding": "dcz",
                    "Use-As-Dictionary": EXPECTED_UAD,
                },
            )
        }
    )

    assert status is False
    assert data == {"unexpected_dcz_fallback": [(TARGET_URL, "dcz")]}


async def test_negative_bad_fallback_use_as_dict(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "unknown_dict": CallbackResult(
                status=200, headers={"Use-As-Dictionary": "wrong"}
            )
        }
    )

    assert status is False
    assert data == {"bad_fallback_use_as_dict": [(TARGET_URL, "wrong")]}


async def test_negative_missing_fallback_use_as_dict(run_check):
    status, data = await run_check(
        cdn_callback_hooks={"unknown_dict": CallbackResult(status=200, headers={})}
    )

    assert status is False
    assert data == {"missing_fallback_use_as_dict": [TARGET_URL]}


async def test_negative_missing_fallback_same_target(run_check):
    status, data = await run_check(
        cdn_callback_hooks={"same_target": CallbackResult(status=500)}
    )

    assert status is False
    assert data == {"missing_fallback_same_target": [TARGET_URL]}


async def test_negative_missing_bad_dict_id_fallback(run_check):
    status, data = await run_check(
        cdn_callback_hooks={"bad_dict_id": CallbackResult(status=500)}
    )

    assert status is False
    assert data == {"missing_bad_dict_id_fallback": [TARGET_URL]}


async def test_negative_unreachable_dcz(run_check):
    status, data = await run_check(
        cdn_callback_hooks={"dict_fetch": CallbackResult(status=500)}
    )

    assert status is False
    assert data == {"unreachable_dcz": [TARGET_URL]}


async def test_negative_missing_dcz_encoding(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "dict_fetch": CallbackResult(status=200, headers={"Content-Length": "500"})
        }
    )

    assert status is False
    assert data == {"missing_dcz_encoding": [(TARGET_URL, DICT_FETCH_HEADERS, True)]}


async def test_negative_content_type_mismatch(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "dict_fetch": CallbackResult(
                status=200,
                headers={"Content-Encoding": "dcz", "Content-Length": "500"},
                content_type="text/plain",
            )
        }
    )

    assert status is False
    assert data == {
        "content_type_mismatch": [
            (
                TARGET_URL,
                DICT_FETCH_HEADERS,
                f"''text/plain' != '{MIMETYPE}'",
            )
        ]
    }


async def test_negative_content_length_uncompressed(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "dict_fetch": CallbackResult(
                status=200,
                headers={
                    "Content-Encoding": "dcz",
                    "Content-Length": "2000",
                    "Use-As-Dictionary": EXPECTED_UAD,
                },
                content_type=MIMETYPE,
            )
        }
    )

    assert status is False
    assert data == {"content_length_uncompressed": [(TARGET_URL, DICT_FETCH_HEADERS)]}


async def test_negative_bad_next_use_as_dict(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "dict_fetch": CallbackResult(
                status=200,
                headers={
                    "Content-Encoding": "dcz",
                    "Content-Length": "500",
                    "Use-As-Dictionary": "wrong",
                },
                content_type=MIMETYPE,
            )
        }
    )

    assert status is False
    assert data == {"bad_next_use_as_dict": [(TARGET_URL, "wrong")]}


async def test_negative_missing_next_use_as_dict(run_check):
    status, data = await run_check(
        cdn_callback_hooks={
            "dict_fetch": CallbackResult(
                status=200,
                headers={"Content-Encoding": "dcz", "Content-Length": "500"},
                content_type=MIMETYPE,
            )
        }
    )

    assert status is False
    assert data == {"missing_next_use_as_dict": [TARGET_URL]}


async def test_negative_unexpected_status_for_unknown_attachment(
    mock_aioresponses, run_check
):
    unknown_url = BASE_URL + "bid/cid/unknown.jpeg"
    mock_aioresponses.head(unknown_url, status=200, repeat=True)

    status, data = await run_check()

    assert status is False
    assert data == {"unexpected_status_for_unknown_attachment": True}
