from checks.remotesettings.blocked_pages import run


COLLECTION_URL = "/buckets/{}/collections/{}"
RECORDS_URL = COLLECTION_URL + "/records"


def mock_kinto_responses(mock_responses, server_url):
    mock_responses.get(
        server_url + RECORDS_URL.format("blocklists", "plugins"),
        payload={"data": [{"id": "1-2-3", "blockID": "abc"}, {"id": "4-5-6"}]},
        headers={"ETag": '"157556192042"'},
    )
    mock_responses.get(
        server_url + RECORDS_URL.format("blocklists", "addons"),
        payload={
            "data": [{"id": "def", "blockID": "7-8-9", "last_modified": 1568816392824}]
        },
        headers={"ETag": '"1568816392824"'},
    )
    mock_responses.head(
        server_url + RECORDS_URL.format("blocklists", "certificates"),
        headers={"ETag": '"1181628381652"'},
    )


async def test_positive(mock_aioresponses, mock_responses):
    server_url = "http://fake.local/v1"
    blocked_url = "http://blocked.cdn"

    mock_kinto_responses(mock_responses, server_url)

    page_content = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<body>
  <ul id="blocked-items">
    <li><span class="dt">Sep 18, 2019</span>: <a href="abc.html">FSCH</a></li>
    <li><span class="dt">Sep 17, 2019</span>: <a href="4-5-6.html">Youtube Downloaders</a></li>
    <li><span class="dt">Sep 16, 2019</span>: <a href="7-8-9.html">Plugin</a></li>
  </ul>
</body>
    """
    mock_aioresponses.get(blocked_url + "/", body=page_content)
    mock_aioresponses.head(blocked_url + "/abc.html")
    mock_aioresponses.head(blocked_url + "/4-5-6.html")
    mock_aioresponses.head(blocked_url + "/7-8-9.html")

    status, data = await run(
        remotesettings_server=server_url, blocked_pages=blocked_url
    )

    assert status is True
    assert data == {
        "addons-timestamp": 1568816392824,
        "plugins-timestamp": 157556192042,
        "certificates-timestamp": 1181628381652,
        "broken-links": [],
        "missing": [],
        "extras": [],
    }


async def test_negative(mock_aioresponses, mock_responses):
    server_url = "http://fake.local/v1"
    blocked_url = "http://blocked.cdn"

    mock_kinto_responses(mock_responses, server_url)

    page_content = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<body>
  <ul id="blocked-items">
    <li><span class="dt">Sep 17, 2019</span>: <a href="4-5-6.html">Youtube Downloaders</a></li>
    <li><span class="dt">Sep 16, 2019</span>: <a href="7-8-9.html">Plugin</a></li>
    <li><span class="dt">Sep 16, 2019</span>: <a href="extra.html">Extra</a></li>
  </ul>
</body>
    """
    mock_aioresponses.get(blocked_url + "/", body=page_content)
    mock_aioresponses.head(blocked_url + "/4-5-6.html")
    mock_aioresponses.head(blocked_url + "/extra.html")

    status, data = await run(
        remotesettings_server=server_url, blocked_pages=blocked_url
    )

    assert status is False
    assert data == {
        "addons-timestamp": 1568816392824,
        "plugins-timestamp": 157556192042,
        "certificates-timestamp": 1181628381652,
        "broken-links": ["7-8-9.html"],
        "missing": ["abc"],
        "extras": ["extra"],
    }
