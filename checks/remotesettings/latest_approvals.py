"""
Dummy-check to obtain information about the last approvals of each collection.

For each collection, the list of latest approvals is returned. The date, author and
number of applied changes are provided.
"""
import asyncio

from .utils import KintoClient as Client, fetch_signed_resources


def get_latest_approvals(client, bucket, collection, max_approvals):
    """
    Return information about the latest approvals for the specified collection.

    Example:

    ::

        [
          {
            "date": "2019-03-06T17:36:51.912770",
            "by": "ldap:jane@mozilla.com",
            "changes": 3
          },
          {
            "date": "2019-01-29T19:05:30.332373",
            "by": "account:user",
            "changes": 15
          },
          {
            "date": "2019-01-28T22:07:58.439230",
            "by": "ldap:tarzan@mozilla.com",
            "changes": 6
          }
        ]
    """

    # Start by fetching the latest approvals for this collection.
    history = client.get_history(
        bucket=bucket,
        **{
            "resource_name": "collection",
            "target.data.id": collection,
            "target.data.status": "to-sign",
            "_sort": "-last_modified",
            "_limit": max_approvals + 1,
        },
    )
    # Now fetch the number of changes for each approval.

    # If there was only one approval, add a fake previous.
    if len(history) == 1:
        history.append({"last_modified": 0})

    # For each pair (previous, current) fetch the number of history entries
    # on records.
    results = []
    for i, current in enumerate(history[:-1]):
        previous = history[i + 1]
        after = previous["last_modified"]
        before = current["last_modified"]
        changes = client.get_history(
            bucket=bucket,
            **{
                "resource_name": "record",
                "collection_id": collection,
                "gt_target.data.last_modified": after,
                "lt_target.data.last_modified": before,
            },
        )
        results.append(
            {
                "datetime": current["date"],
                "by": current["user_id"],
                "changes": len(changes),
            }
        )

    return results


async def run(server, auth, max_approvals=3):
    client = Client(server_url=server, auth=auth)

    source_collections = [
        (r["source"]["bucket"], r["source"]["collection"])
        for r in fetch_signed_resources(server, auth)
    ]

    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(
            None, get_latest_approvals, client, bid, cid, max_approvals
        )
        for (bid, cid) in source_collections
    ]
    results = await asyncio.gather(*futures)

    # Sort collections by latest approval descending.
    date_sorted = sorted(
        zip(source_collections, results),
        key=lambda item: item[1][0]["datetime"] if len(item[1]) > 0 else "0000-00-00",
        reverse=True,
    )

    approvals = {f"{bid}/{cid}": entries for (bid, cid), entries in date_sorted}

    return True, approvals
