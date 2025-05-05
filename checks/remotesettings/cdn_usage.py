"""
Analyze the CDN usage of Remote Settings.

For each endpoint, the top 5 collections by bandwidth and hits are returned.
"""

import json
import os

from telescope.typings import CheckResult
from telescope.utils import fetch_bigquery


QUERY = """
WITH attachments_urls AS (
  SELECT
    'attachments' AS source,
    http_request.request_url AS url,
    http_request.response_size AS size,
    *
  FROM `moz-fx-remote-settings-prod.remote_settings_prod_default_log_linked._AllLogs`
  WHERE http_request.request_url LIKE '{attachments_base_url}%' -- exclude bad URLs
),
api_urls AS (
  SELECT
    'api' AS source,
    http_request.request_url AS url,
    http_request.response_size AS size,
    *
  FROM `moz-fx-remote-settings-prod.gke_remote_settings_prod_log_linked._AllLogs`
  WHERE http_request.request_url LIKE '{api_base_url}%'  -- exclude writers, etc.
),
urls AS (
  SELECT * FROM attachments_urls
  UNION ALL
  SELECT * FROM api_urls
),
urls_with_endpoint AS (
  SELECT
  CASE
    WHEN url LIKE '%/v1/' THEN 'root'
    WHEN url LIKE '%/bundles/%' THEN 'bundles'
    WHEN url LIKE '{attachments_base_url}/%/%/%' THEN 'attachments'
    WHEN url LIKE '%/records%' THEN 'records'
    WHEN url LIKE '%/changeset%' AND url LIKE '%collection=%' THEN 'filtered-monitor'
    WHEN url LIKE '%/changeset%' THEN 'changeset'
    WHEN url LIKE '%/collections/%' THEN 'collection'
    ELSE 'unknown'
  END AS endpoint,
  *
  FROM urls
  WHERE timestamp >= TIMESTAMP(DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH))
    AND timestamp < TIMESTAMP(DATE_TRUNC(CURRENT_DATE(), MONTH))
    AND http_request.status = 200
),
urls_with_types_bid_cid AS (
  SELECT
  CASE
    WHEN endpoint = 'bundles' THEN REGEXP_EXTRACT(url, r'/bundles/([^\\.]+)')
    WHEN endpoint = 'attachments' THEN REGEXP_EXTRACT(url, r'https://[^/]+/([^/]+)/[^/]+/[^/]+')
    WHEN endpoint = 'filtered-monitor' THEN REGEXP_EXTRACT(url, r'bucket=([^&]+)')
    ELSE REGEXP_EXTRACT(url, r'/buckets/([^/]+)/')
  END AS bid,
  CASE
    WHEN endpoint = 'bundles' THEN REGEXP_EXTRACT(url, r'/bundles/([^\\.]+)')
    WHEN endpoint = 'attachments' THEN REGEXP_EXTRACT(url, r'https://[^/]+/[^/]+/([^/]+)/[^/]+')
    WHEN endpoint = 'filtered-monitor' THEN REGEXP_EXTRACT(url, r'collection=([^&]+)')
    ELSE REGEXP_EXTRACT(url, r'/collections/([^/?]+)')
  END AS cid,
  *
  FROM urls_with_endpoint
),
period AS (
  SELECT
    FORMAT_TIMESTAMP('%FT%T%Ez', MIN(timestamp)) AS period_start,
    FORMAT_TIMESTAMP('%FT%T%Ez', MAX(timestamp)) AS period_end
  FROM urls_with_endpoint
),
total_size_hits_by_cid AS (
  SELECT
    source,
    endpoint,
    REPLACE(
        REPLACE(
            REPLACE(bid, "-staging", ""),
            "staging", "blocklists"
        ),
        "-workspace", ""
    ) AS bid,
    COALESCE(SPLIT(cid, '--')[SAFE_OFFSET(1)], cid) AS cid,
    SUM(size) AS size,
    COUNT(*) AS hits
  FROM urls_with_types_bid_cid
  GROUP BY
    source,
    endpoint,
    bid,
    cid
),
totals_by_source AS (
  SELECT source, SUM(size) AS total_size, COUNT(*) AS total_hits
  FROM urls_with_endpoint
  GROUP BY source
)
SELECT
  period_start,
  period_end,
  bid AS bucket_id,
  cid AS collection_id,
  t1.source,
  t1.endpoint,
  hits,
  size,
  total_hits,
  total_size
FROM
  period,
  total_size_hits_by_cid AS t1
    LEFT JOIN totals_by_source AS t2
    ON (t1.source = t2.source)
WHERE t1.hits > 2 -- ignore noise (not real clients)
"""


async def run(
    project: str = "moz-fx-remote-settings-prod",
    top_count: int = 5,
    api_base_url="https://firefox.settings.services.mozilla.com/v1",
    attachments_base_url="https://firefox-settings-attachments.cdn.mozilla.net",
) -> CheckResult:
    query = QUERY.format(
        api_base_url=api_base_url, attachments_base_url=attachments_base_url
    )
    print(query)
    if os.path.exists("results.json"):
        with open("results.json", "r") as f:
            rows = json.load(f)
    else:
        rows = await fetch_bigquery(query, project=project)
        rows = [dict(row) for row in rows]
        with open("results.json", "w") as f:
            json.dump(rows, f, indent=4)

    # Compute the total of bandwidth and hits per endpoint.
    totals = {}
    for row in rows:
        endpoint = row["endpoint"]
        totals.setdefault(
            endpoint,
            {
                "bandwidth": 0,
                "hits": 0,
            },
        )
        totals[endpoint]["bandwidth"] += row["size"]
        totals[endpoint]["hits"] += row["hits"]
    # Combine all endpoints into a single `__all__` entry.
    totals["__all__"] = {
        "bandwidth": sum(row["bandwidth"] for row in totals.values()),
        "hits": sum(row["hits"] for row in totals.values()),
    }

    tops_bandwidth_per_endpoint = {}
    tops_hits_per_endpoint = {}
    for endpoint in totals.keys():
        # Sum the bandwidth and hits per collection.
        per_collection = {}
        for row in rows:
            if row["endpoint"] == "unknown":
                # Omit the unknown endpoints, since no collection is associated with them.
                continue
            if row["endpoint"] != endpoint and endpoint != "__all__":
                # Filter rows by endpoint to sum, unless it's the `__all__` entry.
                continue
            if row["endpoint"] == "root":
                cid = "root"
            elif row["endpoint"] == "bundles":
                cid = row["collection_id"]
            else:
                cid = f"{row['bucket_id']}/{row['collection_id']}"

            per_collection.setdefault(cid, {"bandwidth": 0, "hits": 0})
            per_collection[cid]["bandwidth"] += row["size"]
            per_collection[cid]["hits"] += row["hits"]

        # Keep only the top 5 collections by bandwidth and hits.
        tops_bandwidth_per_endpoint[endpoint] = {
            cid: round(100.0 * value["bandwidth"] / totals[endpoint]["bandwidth"], 2)
            for cid, value in sorted(
                per_collection.items(), key=lambda x: x[1]["bandwidth"], reverse=True
            )[:top_count]
        }
        tops_hits_per_endpoint[endpoint] = {
            cid: round(100.0 * value["hits"] / totals[endpoint]["hits"], 2)
            for cid, value in sorted(
                per_collection.items(), key=lambda x: x[1]["hits"], reverse=True
            )[:top_count]
        }

    # Remove the 'root' and 'unknown' endpoints from the top percentages,
    # since they are not collections.
    for endpoint in ("root", "unknown"):
        del tops_bandwidth_per_endpoint[endpoint]
        del tops_hits_per_endpoint[endpoint]

    result = {
        "period_start": rows[0]["period_start"],
        "period_end": rows[0]["period_end"],
        "bandwidth": tops_bandwidth_per_endpoint,
        "hits": tops_hits_per_endpoint,
    }

    return True, result
