from datetime import datetime, timezone
from unittest import mock

from checks.core.maintenance import run


async def test_positive(mock_aioresponses, config):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734086,
                "draft": False,
                "updated_at": "2019-01-09T13:59:35Z",
                "labels": [],
            }
        ],
    )

    fake_now = datetime(2019, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
    with mock.patch("checks.core.maintenance.utcnow", return_value=fake_now):
        with mock.patch.object(config, "GITHUB_TOKEN", "s3cr3t"):
            status, data = await run(repositories=["Kinto/kinto"])

    assert status is True
    assert data == {"Kinto/kinto": {"pulls": {"old": 1, "total": 1}}}


async def test_negative(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734086,
                "draft": False,
                "updated_at": "2019-01-09T13:59:35Z",
                "labels": [],
            }
        ],
    )

    status, data = await run(repositories=["Kinto/kinto"], max_opened_pulls=0)

    assert status is False
    assert data == {"Kinto/kinto": {"pulls": {"old": 1, "total": 1}}}


async def test_no_pulls(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls?state=open",
        status=200,
        payload=[],
    )

    status, data = await run(repositories=["Kinto/kinto"])

    assert status is True
    assert data == {}


async def test_ignore_draft_pulls(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734086,
                "draft": True,
                "updated_at": "2019-01-09T13:59:35Z",
                "labels": [],
            }
        ],
    )

    status, data = await run(repositories=["Kinto/kinto"])

    assert status is True
    assert data == {}


async def test_recent_pulls_dont_count(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto-wizard/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734086,
                "draft": False,
                "updated_at": "2019-01-09T00:00:00Z",
                "labels": [],
            },
            {
                "id": 615734087,
                "draft": False,
                "updated_at": "2019-01-12T00:00:00Z",
                "labels": [],
            },
        ],
    )

    fake_now = datetime(2019, 1, 12, 12, 0, 0, tzinfo=timezone.utc)
    with mock.patch("checks.core.maintenance.utcnow", return_value=fake_now):
        status, data = await run(
            repositories=["Kinto/kinto-wizard"],
            max_opened_pulls=0,
            max_days_last_activity=3,
        )

    assert status is True
    assert data == {"Kinto/kinto-wizard": {"pulls": {"old": 0, "total": 2}}}


async def test_pulls_with_labels_blocked_dont_count(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto-wizard/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734087,
                "draft": False,
                "labels": [
                    {"id": 1203232965, "name": "dependencies"},
                    {"id": 4559590550, "name": "blocked"},
                ],
                "updated_at": "2019-01-12T00:00:00Z",
            },
        ],
    )
    status, data = await run(repositories=["Kinto/kinto-wizard"])

    assert status is True
    assert data == {}


async def test_fail_if_no_activity_for_days(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734086,
                "draft": False,
                "updated_at": "2000-01-05T00:00:00Z",
                "labels": [],
            },
        ],
    )

    status, data = await run(repositories=["Kinto/kinto"])

    assert status is False
    assert data == {"Kinto/kinto": {"pulls": {"old": 1, "total": 1}}}
