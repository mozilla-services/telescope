from datetime import datetime, timezone
from unittest import mock

import pytest

from checks.core.readthedocs import run


GITHUB_BRANCH_PAYLOAD = {
    "name": "main",
    "commit": {"sha": "abc123", "commit": {"author": {"date": "2025-04-28T12:00:00Z"}}},
}

GITHUB_RELEASE_PAYLOAD = {
    "url": "https://api.github.com/repos/mozilla-services/kinto-dist/releases/18962883",
    "assets_url": "https://api.github.com/repos/mozilla-services/kinto-dist/releases/18962883/assets",
    "upload_url": "https://uploads.github.com/repos/mozilla-services/kinto-dist/releases/18962883/assets{?name,label}",
    "html_url": "https://github.com/mozilla-services/kinto-dist/releases/tag/17.1.4",
    "id": 18962883,
    "node_id": "MDc6UmVsZWFzZTE4OTYyODgz",
    "tag_name": "v1.2.3",
    "target_commitish": "master",
    "name": "",
    "author": {"login": "leplatrem", "id": 546692},
}

RTD_VERSIONS_PAYLOAD = {
    "count": 1,
    "next": "https://readthedocs.org/api/v3/projects/remote-settings/versions/?limit=10&offset=10",
    "previous": None,
    "results": [
        {
            "_links": {
                "_self": "https://app.readthedocs.org/api/v3/projects/remote-settings/versions/v33.1.0/",
                "builds": "https://app.readthedocs.org/api/v3/projects/remote-settings/versions/v33.1.0/builds/",
                "project": "https://app.readthedocs.org/api/v3/projects/remote-settings/",
            },
            "active": False,
            "aliases": [],
            "built": False,
            "downloads": {},
            "hidden": False,
            "id": 21175775,
            "identifier": "abc",
            "privacy_level": "public",
            "ref": None,
            "slug": "v1.2.3",
            "type": "tag",
            "urls": {
                "dashboard": {
                    "edit": "https://app.readthedocs.org/dashboard/remote-settings/version/v1.2.3/edit/"
                },
                "documentation": "https://remote-settings.readthedocs.io/en/v1.2.3/",
                "vcs": "https://github.com/mozilla/remote-settings/tree/v1.2.3/",
            },
            "verbose_name": "v1.2.3",
        },
    ],
}

RTD_BUILDS_PAYLOAD = {
    "count": 1,
    "next": "https://readthedocs.org/api/v3/projects/remote-settings/builds/?limit=10&offset=10",
    "previous": None,
    "results": [
        {
            "_links": {
                "_self": "https://app.readthedocs.org/api/v3/projects/remote-settings/builds/27996636/",
                "notifications": "https://app.readthedocs.org/api/v3/projects/remote-settings/builds/27996636/notifications/",
                "project": "https://app.readthedocs.org/api/v3/projects/remote-settings/",
                "version": "https://app.readthedocs.org/api/v3/projects/remote-settings/versions/latest/",
            },
            "commit": "abc123",
            "created": "2025-04-28T15:15:09.247314Z",
            "duration": 47,
            "error": "",
            "finished": "2025-04-28T15:15:56.247314Z",
            "id": 27996636,
            "project": "remote-settings",
            "state": {"code": "finished", "name": "Finished"},
            "success": True,
            "urls": {
                "build": "https://app.readthedocs.org/projects/remote-settings/builds/27996636/",
                "project": "https://app.readthedocs.org/projects/remote-settings/",
                "version": "https://app.readthedocs.org/dashboard/remote-settings/version/latest/edit/",
            },
            "version": "latest",
        }
    ],
}


@pytest.mark.asyncio
async def test_positive_all_match(mock_aioresponses):
    """Test when latest GitHub SHA and tag match ReadTheDocs build and version."""

    # Mock ReadTheDocs
    mock_aioresponses.get(
        "https://readthedocs.org/api/v3/projects/remote-settings/versions/",
        payload=RTD_VERSIONS_PAYLOAD,
    )
    mock_aioresponses.get(
        "https://readthedocs.org/api/v3/projects/remote-settings/builds/",
        payload=RTD_BUILDS_PAYLOAD,
    )

    # Mock GitHub
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/branches/main",
        payload=GITHUB_BRANCH_PAYLOAD,
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/releases/latest",
        payload=GITHUB_RELEASE_PAYLOAD,
    )

    status, data = await run(
        repo="mozilla/remote-settings",
        rtd_slug="remote-settings",
        rtd_token="secrettoken",
    )

    assert status is True
    assert data == {
        "github": {
            "latest_sha": "abc123",
            "latest_version": "v1.2.3",
        },
        "readthedocs": {
            "lastest_build": "abc123",
            "latest_version": "v1.2.3",
        },
    }


@pytest.mark.asyncio
async def test_positive_commit_recent(mock_aioresponses):
    """Test when commit is recent enough (within lag margin)."""

    mock_aioresponses.get(
        "https://readthedocs.org/api/v3/projects/remote-settings/versions/",
        payload={"results": [{"slug": "something-different"}]},
    )
    mock_aioresponses.get(
        "https://readthedocs.org/api/v3/projects/remote-settings/builds/",
        payload={"results": [{"commit": "differentcommit", "success": True}]},
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/branches/main",
        payload=GITHUB_BRANCH_PAYLOAD,
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/releases/latest",
        payload={"tag_name": "different-tag"},
    )

    fake_now = datetime(2025, 4, 28, 12, 10, 0, tzinfo=timezone.utc)

    with mock.patch("checks.core.readthedocs.utcnow", return_value=fake_now):
        status, data = await run(
            repo="mozilla/remote-settings",
            rtd_slug="remote-settings",
            rtd_token="secret",
            lag_margin_seconds=900,
        )

    assert status is True
    assert data["github"]["latest_sha"] == "abc123"
    assert data["readthedocs"]["lastest_build"] == "differentcommit"


@pytest.mark.asyncio
async def test_negative_not_recent_and_not_matching(mock_aioresponses):
    """Test when commit is not recent and build/version don't match."""

    mock_aioresponses.get(
        "https://readthedocs.org/api/v3/projects/remote-settings/versions/",
        payload={"results": [{"slug": "something-else"}]},
    )
    mock_aioresponses.get(
        "https://readthedocs.org/api/v3/projects/remote-settings/builds/",
        payload={
            "results": [{"commit": "abc123", "success": False, "error": "Build failed"}]
        },
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/branches/main",
        payload=GITHUB_BRANCH_PAYLOAD,
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/releases/latest",
        payload={"tag_name": "another-tag"},
    )

    fake_now = datetime(2025, 4, 28, 14, 0, 0, tzinfo=timezone.utc)

    with mock.patch("checks.core.readthedocs.utcnow", return_value=fake_now):
        status, data = await run(
            repo="mozilla/remote-settings",
            rtd_slug="remote-settings",
            rtd_token="secret",
            lag_margin_seconds=900,
        )

    assert status is False
    assert data["github"]["latest_sha"] == "abc123"
    assert data["readthedocs"]["lastest_build"] == "Build failed"
