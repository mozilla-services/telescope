from datetime import datetime, timezone
from unittest import mock

from checks.core.maintenance import run


async def test_positive(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734086,
                "draft": False,
                "review_comments_url": "https://api.github.com/repos/Kinto/kinto/pulls/615734086/comments",
                "updated_at": "2019-01-09T13:59:35Z",
            }
        ],
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls/615734086/comments?sort=updated_at&direction=desc",
        status=200,
        payload=[],
    )

    fake_now = datetime(2019, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
    with mock.patch("checks.core.maintenance.utcnow", return_value=fake_now):
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
                "review_comments_url": "https://api.github.com/repos/Kinto/kinto/pulls/615734086/comments",
                "updated_at": "2019-01-09T13:59:35Z",
            }
        ],
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls/615734086/comments?sort=updated_at&direction=desc",
        status=200,
        payload=[],
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
                "review_comments_url": "https://api.github.com/repos/Kinto/kinto/pulls/615734086/comments",
                "updated_at": "2019-01-09T13:59:35Z",
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
                "review_comments_url": "https://api.github.com/repos/Kinto/kinto-wizard/pulls/615734086/comments",
                "updated_at": "2000-01-05T00:00:00Z",
            },
            {
                "id": 615734087,
                "draft": False,
                "review_comments_url": "https://api.github.com/repos/Kinto/kinto-wizard/pulls/615734087/comments",
                "updated_at": "2019-01-12T00:00:00Z",
            },
        ],
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto-wizard/pulls/615734086/comments?sort=updated_at&direction=desc",
        status=200,
        payload=[
            {
                "updated_at": "2019-01-09T13:59:35Z",
            },
            {
                "updated_at": "1982-01-01T00:00:00Z",
            },
        ],
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto-wizard/pulls/615734087/comments?sort=updated_at&direction=desc",
        status=200,
        payload=[],
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


async def test_fail_if_no_activity_for_days(mock_aioresponses):
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls?state=open",
        status=200,
        payload=[
            {
                "id": 615734086,
                "draft": False,
                "review_comments_url": "https://api.github.com/repos/Kinto/kinto/pulls/615734086/comments",
                "updated_at": "2000-01-05T00:00:00Z",
            },
        ],
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls/615734086/comments?sort=updated_at&direction=desc",
        status=200,
        payload=[
            {
                "updated_at": "2019-01-09T13:59:35Z",
            },
            {
                "updated_at": "1982-01-01T00:00:00Z",
            },
        ],
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/Kinto/kinto/pulls/615734087/comments?sort=updated_at&direction=desc",
        status=200,
        payload=[],
    )

    status, data = await run(repositories=["Kinto/kinto"])

    assert status is False
    assert data == {"Kinto/kinto": {"pulls": {"old": 1, "total": 1}}}
