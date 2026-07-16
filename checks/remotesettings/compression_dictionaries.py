""" """

import logging
from pathlib import Path
from typing import Any

from telescope.typings import CheckResult
from telescope.utils import fetch_head, fetch_json, run_parallel

from .utils import KintoClient, fetch_signed_resources


logger = logging.getLogger(__name__)


EXPOSED_PARAMETERS = ["env"]

UNKNOWN_DICT_ID = '"178907141337--some-record-id--some-filename"'
BAD_DICT_ID = "some-filename-without-double-dashes.txt"
MANIFEST_URL_PATTERN = "https://storage.googleapis.com/remote-settings-{realm}-{env}-compression-dictionaries/cdt/{bid}/{cid}/manifest.json"


async def run(
    server: str, auth: str, env: str = "dev", max_pairs: int = 5
) -> CheckResult:
    realm = {"dev": "nonprod", "stage": "nonprod", "prod": "prod"}[env]

    # List collections where CDT are enabled.
    client = KintoClient(server_url=server, auth=auth)
    resources = await fetch_signed_resources(client=client)
    futures = [
        client.get_changeset(
            bucket=resource["source"]["bucket"],
            collection=resource["source"]["collection"],
        )
        for resource in resources
    ]
    results_changesets = await run_parallel(*futures)
    collection_with_cdt = [
        changeset
        for changeset in results_changesets
        if "compression-dictionaries" in changeset["metadata"].get("flags", [])
    ]

    # Look at history of live records with attachment in these collections.
    futures = [
        client.get_history(
            bucket=changeset["metadata"]["bucket"],
            params={
                "resource_name": "record",
                "collection_id": changeset["metadata"]["id"],
                "has_target.data.attachment": "true",
                "in_target.data.id": ",".join(r["id"] for r in changeset["changes"]),
                "like_target.data.attachment.location": "--",
                "_sort": "-last_modified",
                # TODO: _limit? _since?
            },
        )
        for changeset in collection_with_cdt
    ]
    results_history = await run_parallel(*futures)

    # Build history per record.
    history_by_rid: dict[tuple[str, str, str], list] = {}
    for changeset, history in zip(collection_with_cdt, results_history):
        bid = changeset["metadata"]["bucket"]
        cid = changeset["metadata"]["id"]
        for entry in history:
            # TODO: ignore history that is too recent (give time to cronjob to have run)
            rid = entry["target"]["data"]["id"]
            history_by_rid.setdefault((bid, cid, rid), []).append(entry)

    # Now keep history entries where attachment was modified.
    pairs_by_rid: dict[tuple[str, str], dict[str, list[tuple]]] = {}
    for (bid, cid, rid), history in history_by_rid.items():
        assert len(history) > 0, "History should never be empty"
        previous = history[0]
        p_attachment = latest_attachment = previous["target"]["data"]["attachment"]
        for next in history[1:]:
            old_attachment = next["target"]["data"]["attachment"]
            # Is this record history entry about attachment modification?
            if p_attachment["location"] != old_attachment["location"]:
                pair = (latest_attachment, old_attachment)
                pairs_by_rid.setdefault((bid, cid), {}).setdefault(rid, []).append(pair)
                previous = next
                p_attachment = old_attachment

                if len(pairs_by_rid[(bid, cid)][rid]) > max_pairs:
                    break

    errors: dict[str, Any] = {}

    # Now check that all recent pairs are published (using `manifest.json`).
    for (bid, cid), rid_pairs in pairs_by_rid.items():
        manifest = await fetch_json(
            MANIFEST_URL_PATTERN.format(bid=bid, cid=cid, realm=realm, env=env),
            raise_for_status=True,
        )

        paircount = sum(len(sources) for sources in manifest.values())
        logger.info("%s pairs in %s/%s's published manifest", paircount, bid, cid)

        for pairs in rid_pairs.values():
            for pair in pairs:
                target, source = pair
                target_filename = Path(target["location"]).name
                source_filename = Path(source["location"]).name
                if (
                    target_filename not in manifest
                    or source_filename not in manifest[target_filename]
                ):
                    errors.setdefault("missing_pairs", {}).setdefault(
                        f"{bid}/{cid}", []
                    ).append(pair)
                    continue

    # Now test the Compression Dictionary Transport content negotiation.

    info = await client.server_info()
    base_url = info["capabilities"]["attachments"]["base_url"]

    # Note: tests are done semi-sequentially for better readability.
    # Performance is not crucial and zipping futures is not great.
    for (bid, cid), rid_pairs in pairs_by_rid.items():
        for rid, pairs in rid_pairs.items():
            latest, _ = pairs[0]
            target_url = f"{base_url}{latest['location']}"
            target_filename = Path(latest["location"]).name

            futures = [
                # Without `Content-Encoding: dcz`
                fetch_head(target_url),
                # With `Content-Encoding: dcz`, but no `Dictionary-ID` (first download).
                fetch_head(target_url, headers={"Accept-Encoding": "dcz"}),
                # With unknown Dictionary-ID
                fetch_head(
                    target_url,
                    headers={
                        "Accept-Encoding": "dcz",
                        "Dictionary-ID": UNKNOWN_DICT_ID,
                    },
                ),
                # With same Dictionary-ID as target
                fetch_head(
                    target_url,
                    headers={
                        "Accept-Encoding": "dcz",
                        "Dictionary-ID": target_filename,
                    },
                ),
                # With unsupported filename for Dictionary-ID
                fetch_head(
                    target_url,
                    headers={
                        "Accept-Encoding": "dcz",
                        "Dictionary-ID": BAD_DICT_ID,
                    },
                ),
            ]
            [
                (plain_status, plain_headers),
                (first_fetch_status, first_fetch_headers),
                (unknown_dict_status, unknown_dict_headers),
                (same_dict_status, _),
                (unsupported_filename_status, _),
            ] = await run_parallel(*futures)

            # Without `Content-Encoding: dcz`
            if plain_status != 200:
                errors.setdefault("unreachable_url", []).append(target_url)
                continue
            logger.debug(
                "Attachment %s is accessible without `dcz` encoding.",
                latest["location"],
            )

            # With `Content-Encoding: dcz`, but no `Dictionary-ID` (first download).
            if first_fetch_status != 200:
                errors.setdefault("unreachable_first_dcz", []).append(target_url)
                continue
            # Check that it tells clients to store it as dictionary.
            expected_use_as_dict = (
                f'match="/{bid}/{cid}/*--{rid}--*", id="{target_filename}", type=raw'
            )
            if use_as_dict := first_fetch_headers.get("Use-As-Dictionary"):
                if use_as_dict != expected_use_as_dict:
                    errors.setdefault("bad_first_use_as_dict", []).append(
                        (target_url, use_as_dict)
                    )
                    continue
            else:
                errors.setdefault("missing_first_use_as_dict", []).append(target_url)
                continue
            logger.debug(
                "Attachment %s first download with `dcz` encoding is working as expected",
                latest["location"],
            )

            # With unknown Dictionary-ID
            if unknown_dict_status != 200:
                errors.setdefault("missing_fallback", []).append(target_url)
            if (encoding := unknown_dict_headers.get("Content-Encoding", "")) == "dcz":
                errors.setdefault("unexpected_dcz_fallback", []).append(
                    (target_url, encoding)
                )
            if use_as_dict := unknown_dict_headers.get("Use-As-Dictionary"):
                if use_as_dict != expected_use_as_dict:
                    errors.setdefault("bad_fallback_use_as_dict", []).append(
                        (target_url, use_as_dict)
                    )
            else:
                errors.setdefault("missing_fallback_use_as_dict", []).append(target_url)
            logger.debug(
                "Attachment %s with unknown dictionary falls back as expected",
                latest["location"],
            )

            # With same Dictionary-ID as target
            if same_dict_status != 200:
                errors.setdefault("missing_fallback_same_target", []).append(target_url)
            logger.debug(
                "Attachment %s with identical dictionary falls back as expected",
                latest["location"],
            )

            # With unsupported filename for Dictionary-ID
            if unsupported_filename_status != 200:
                errors.setdefault("missing_bad_dict_id_fallback", []).append(target_url)
            logger.debug(
                "Attachment %s with unsupported dictionary falls back as expected",
                latest["location"],
            )

            # Now test that we obtain a compressed file for each pair.
            requests_headers = [
                {
                    "Accept-Encoding": "dcz",
                    # With `Content-Encoding: dcz`, and `Dictionary-ID` (subsequent download).
                    "Dictionary-ID": f'"{Path(source["location"]).name}"',
                }
                for _, source in pairs
            ]
            futures = [
                fetch_head(target_url, headers=headers) for headers in requests_headers
            ]
            results = await run_parallel(*futures)

            # Now inspect the results.
            for (target, source), req_headers, (status, resp_headers) in zip(
                pairs, requests_headers, results
            ):
                if status != 200:
                    errors.setdefault("unreachable_dcz", []).append(target_url)
                    continue
                # Make sure content-encoding is dcz.
                if encoding := resp_headers.get("Content-Encoding", "") != "dcz":
                    errors.setdefault("missing_dcz_encoding", []).append(
                        (target_url, req_headers, encoding)
                    )
                    continue
                # Make sure content-type is original's one.
                if (ctype := resp_headers.get("Content-Type", "")) != (
                    ttype := target["mimetype"]
                ):
                    errors.setdefault("content_type_mismatch", []).append(
                        (target_url, req_headers, f"'{ctype!r} != {ttype!r}")
                    )
                    continue
                # Make sure its size is less.
                if int(resp_headers.get("Content-Length", "0")) >= int(
                    plain_headers.get("Content-Length", 0)
                ):
                    errors.setdefault("content_length_uncompressed", []).append(
                        (target_url, req_headers)
                    )
                # It becomes the new dictionary.
                if use_as_dict := resp_headers.get("Use-As-Dictionary"):
                    if use_as_dict != expected_use_as_dict:
                        errors.setdefault("bad_next_use_as_dict", []).append(
                            (target_url, use_as_dict)
                        )
                        continue
                else:
                    errors.setdefault("missing_next_use_as_dict", []).append(target_url)
                    continue
                logger.debug(
                    "Compression dictionary served for %s from %s",
                    latest["location"],
                    req_headers["Dictionary-ID"],
                )

    # Unknown attachment should not do anything weird.
    status, resp_headers = await fetch_head(
        f"{base_url}bid/cid/unknown.jpeg",
        headers={
            "Accept-Encoding": "dcz",
            "Dictionary-ID": "178907141337--some-record-id--some-filename",
        },
    )
    if status != 404:
        errors["unexpected_status_for_unknown_attachment"] = True

    return len(errors) == 0, errors
