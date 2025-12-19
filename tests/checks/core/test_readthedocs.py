from datetime import datetime, timezone
from unittest import mock

import aiohttp
import pytest

from checks.core.readthedocs import run


GITHUB_BRANCH_PAYLOAD = {
    "name": "main",
    "commit": {"sha": "abc123", "commit": {"author": {"date": "2025-04-28T12:00:00Z"}}},
}

RTD_BUILDS_PAGE = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Builds - Read the Docs Community </title>
    <meta name="description" content="Read the Docs is a documentation publishing and hosting platform for technical documentation" />
    <meta name="keywords" content="documentation hosting" />
  </head>
  <body class="">
    <div class="ui basic fitted attached segment" data-bind="using: HeaderView()">
      <script type="application/json" data-bind="jsonInit: config">
        {
          "api_projects_list_url": "/api/v3/projects/"
        }
      </script>
      <div class="ui container">
        <div class="ui vertically fitted segment">
          <table class="ui very basic stacking table">
            <tbody>
              <tr class="middle aligned">
                <td class="">
                  <div class="ui tiny header">
                    <span class="ui center aligned image">
                      <i class="ui icon green inverted circular fa-solid fa-check"></i>
                    </span>
                    <div class="content">
                      <a href="/projects/remote-settings/builds/30742594/">
                        <span class="ui  breadcrumb">
                          <span class="section"> Version latest </span>
                          <span class="divider">/</span>
                          <span class="active section">
                            <span class="ui grey text"> #30742594 </span>
                          </span>
                        </span>
                      </a>
                      </a>
                      <div class="sub header">
                        <div class="item" data-bind="semanticui: { popup: { content: 'Dec. 18, 2025, 9:02 a.m.', position: 'top center', delay: { show: 500 }, variation: 'small'}}"> Started an hour ago </div>
                      </div>
                    </div>
                  </div>
                </td>
                <td>
                  <div class="ui relaxed stackable small middle aligned horizontal list">
                    <a href="https://github.com/mozilla/remote-settings/commit/abc123" class="item" aria-label="View commit 51137d26">
                      <i class="fa-duotone fa-code-commit icon"></i>
                      <code>51137d26</code>
                    </a>
                  </div>
                </td>
                <td class="collapsing">
                  <div class="ui relaxed stackable small middle aligned horizontal list">
                    <div class="item">
                      <div data-bind="with: $root.PopupcardView('/api/v3/projects/remote-settings/versions/latest/')">
                        <a class="ui basic label" data-bind="semanticui: { popup: popup_config() }" href="/projects/remote-settings/?slug=latest">
                          <i class="fa-solid icon fa-code-branch"></i> latest <div class="detail">
                            <i class="fa-solid icon fa-check"></i>
                          </div>
                        </a>
                        <div class="ui flowing popup" data-bind="using: data">
                          <div class="ui small basic horizontal card" data-bind="css: { loading: $parent.is_loading() }">
                            <div class="content" data-bind="if: $parent.is_loaded()">
                              <div class="header"> Version latest </div>
                              <div class="meta"></div>
                              <div class="description">
                                <div class="ui list">
                                  <div class="item">
                                    <i class="fa-duotone fa-box icon"></i>
                                    <div class="content">
                                      <div class="header">Builds</div>
                                      <div class="description">
                                        <a class="item" href="/projects/remote-settings/builds/?version__slug=latest"> For version latest </a>
                                      </div>
                                    </div>
                                  </div>
                                  <div class="item">
                                    <i class="fa-duotone fa-code-branch icon"></i>
                                    <div class="content">
                                      <div class="header">Branch</div>
                                      <div class="description">
                                        <a href="https://github.com/mozilla/remote-settings/tree/main/"> latest </a>
                                      </div>
                                    </div>
                                  </div>
                                  <div class="item" data-bind="if: urls && active && built">
                                    <i class="fad fa-book icon"></i>
                                    <div class="content">
                                      <div class="header">Documentation</div>
                                      <div class="description">
                                        <a data-bind="text: urls.documentation, attr: { href: urls.documentation }"></a>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                            <div class="extra content" data-bind="if: $parent.is_loaded()">
                              <span></span>
                              <div class="right floated">
                                <span> Active <i class="fas fa-check icon"></i>
                                </span>
                                <span> Built <i class="fas fa-check icon"></i>
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </body>
</html>
"""


@pytest.mark.asyncio
async def test_positive_all_match(mock_aioresponses):
    """Test when latest GitHub SHA and tag match ReadTheDocs build and version."""

    # Mock ReadTheDocs
    mock_aioresponses.get(
        "https://app.readthedocs.org/projects/remote-settings/builds/",
        body=RTD_BUILDS_PAGE,
    )

    # Mock GitHub
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/branches/main",
        payload=GITHUB_BRANCH_PAYLOAD,
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
        },
        "readthedocs": {
            "latest_build": "abc123",
        },
    }


@pytest.mark.asyncio
async def test_positive_commit_recent(mock_aioresponses):
    """Test when commit is recent enough (within lag margin)."""
    mock_aioresponses.get(
        "https://app.readthedocs.org/projects/remote-settings/builds/",
        body=RTD_BUILDS_PAGE.replace("/commit/abc123", "/commit/differentcommit"),
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/branches/main",
        payload=GITHUB_BRANCH_PAYLOAD,
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
    assert data["readthedocs"]["latest_build"] == "differentcommit"


@pytest.mark.asyncio
async def test_negative_not_recent_and_not_matching(mock_aioresponses):
    """Test when commit is not recent and build/version don't match."""
    mock_aioresponses.get(
        "https://app.readthedocs.org/projects/remote-settings/builds/",
        body=RTD_BUILDS_PAGE.replace("/commit/abc123", "/commit/differentcommit"),
    )
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings/branches/main",
        payload=GITHUB_BRANCH_PAYLOAD,
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
    assert data["readthedocs"]["latest_build"] == "differentcommit"


@pytest.mark.asyncio
async def test_bad_status(mock_aioresponses, config):
    config.REQUESTS_MAX_RETRIES = 0
    mock_aioresponses.get(
        "https://app.readthedocs.org/projects/remote-settings/builds/",
        body="<html>Backoff</html>",
        content_type="text/html",
        status=403,
    )

    with pytest.raises(aiohttp.ClientResponseError):
        await run(
            repo="mozilla/remote-settings",
            rtd_slug="remote-settings",
        )
