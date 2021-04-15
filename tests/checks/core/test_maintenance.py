from checks.core.maintenance import run


async def test_positive(mock_aioresponses):
    url = "https://api.github.com/repos/Kinto/kinto/pulls"
    mock_aioresponses.get(
        url,
        status=200,
        payload=[
            {
                "url": "https://api.github.com/repos/Kinto/kinto/pulls/1883",
                "id": 615734086,
            }
        ],
    )

    status, data = await run(repositories=["Kinto/kinto"])

    assert status is True
    assert data == {"pulls": {"Kinto/kinto": 1}}


async def test_negative(mock_aioresponses):
    url = "https://api.github.com/repos/Kinto/kinto/pulls"
    mock_aioresponses.get(
        url,
        status=200,
        payload=[
            {
                "url": "https://api.github.com/repos/Kinto/kinto/pulls/1883",
                "id": 615734086,
            },
            {
                "url": "https://api.github.com/repos/Kinto/kinto/pulls/1884",
                "id": 615734087,
            },
        ],
    )

    status, data = await run(repositories=["Kinto/kinto"], max_opened_pulls=1)

    assert status is False
    assert data == {"pulls": {"Kinto/kinto": 2}}
