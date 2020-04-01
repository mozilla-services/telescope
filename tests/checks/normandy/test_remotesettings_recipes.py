from checks.normandy.remotesettings_recipes import NORMANDY_URL, run


NORMANDY_SERVER = "http://n"
REMOTESETTINGS_SERVER = "http://rs/v1"
REMOTESETTINGS_BASELINE_URL = (
    REMOTESETTINGS_SERVER + "/buckets/main/collections/normandy-recipes/records"
)
REMOTESETTINGS_CAPABILITIES_URL = (
    REMOTESETTINGS_SERVER
    + "/buckets/main/collections/normandy-recipes-capabilities/records"
)

NORMANDY_RECIPE = {
    "signature": {
        "timestamp": "2019-08-16T21:14:28.651337Z",
        "signature": "ZQyCVZEltEzmTH1lavnlzY_BiR-hMSNGp2DrqQRhlbnoRy5wBjpvSu8o4DVb2VSUUo5tUMGvC0fFCvedw7XH9y2CIUZl6xQo8x8KJe75RPZr8zLEuoG8LhzWpOnx1Fuz",
        "x5u": "https://content-signature-2.cdn.mozilla.net/chains/normandy.content-signature.mozilla.org-2019-10-02-18-15-02.chain?cachebust=2017-06-13-21-06",
        "public_key": "MHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEwFEtpUsPaLeS0npnCdyHjYDAvRT1cKeaJdRoOXQLuucfVir4DgGGW4FoM7WsddmcVllXMlGHsPeXr01atWe42wHILl1su0ZaFJDtJ42G5gGYd4nH0S6PTGo97/ux3oO0",
    },
    "recipe": {
        "id": 829,
        "name": "Mobile Browser usage",
        "revision_id": "2687",
        "action": "show-heartbeat",
        "arguments": {
            "repeatOption": "once",
            "surveyId": "hb-mobile-browser-usage",
            "message": "Please help make Firefox better by taking this short survey",
            "learnMoreMessage": "Learn More",
            "learnMoreUrl": "https://support.mozilla.org/en-US/kb/rate-your-firefox-experience-heartbeat",
            "engagementButtonLabel": "Take Survey",
            "thanksMessage": "Thanks",
            "postAnswerUrl": "https://qsurvey.mozilla.com/s3/3ea2dbbe74d5",
            "includeTelemetryUUID": False,
        },
        "filter_expression": '(normandy.locale in ["en-US","en-AU","en-GB","en-CA","en-NZ","en-ZA"]) && (normandy.country in ["US"]) && (normandy.channel in ["release"]) && (["global-v1",normandy.userId]|bucketSample(2135,10,10000)) && (!normandy.firstrun)',
    },
}

REMOTESETTINGS_RECIPE = {
    "id": str(NORMANDY_RECIPE["recipe"]["id"]),
    "recipe": {
        "id": NORMANDY_RECIPE["recipe"]["id"],
        "name": NORMANDY_RECIPE["recipe"]["name"],
    },
}

REMOTESETTINGS_RECIPE_WITH_CAPS = {
    "id": "314",
    "recipe": {
        "id": 314,
        "name": f"With caps",
        "capabilities": ["action.preference-experiment"],
    },
}


async def test_positive(mock_aioresponses):
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER, baseline_only=0),
        payload=[NORMANDY_RECIPE, REMOTESETTINGS_RECIPE_WITH_CAPS],
    )
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER, baseline_only=1),
        payload=[NORMANDY_RECIPE],
    )
    mock_aioresponses.get(
        REMOTESETTINGS_CAPABILITIES_URL,
        payload={"data": [REMOTESETTINGS_RECIPE, REMOTESETTINGS_RECIPE_WITH_CAPS]},
    )
    mock_aioresponses.get(
        REMOTESETTINGS_BASELINE_URL, payload={"data": [REMOTESETTINGS_RECIPE]}
    )

    status, data = await run(NORMANDY_SERVER, REMOTESETTINGS_SERVER)

    assert status is True
    assert data == {
        "baseline": {"missing": [], "extras": []},
        "capabilities": {"missing": [], "extras": []},
    }


async def test_negative(mock_aioresponses):
    RECIPE_42 = {"id": "42", "recipe": {"id": 42, "name": "Extra"}}
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER, baseline_only=0),
        payload=[NORMANDY_RECIPE, REMOTESETTINGS_RECIPE_WITH_CAPS],
    )
    mock_aioresponses.get(
        NORMANDY_URL.format(server=NORMANDY_SERVER, baseline_only=1),
        payload=[NORMANDY_RECIPE],
    )
    mock_aioresponses.get(
        REMOTESETTINGS_CAPABILITIES_URL,
        payload={"data": [REMOTESETTINGS_RECIPE_WITH_CAPS]},
    )
    mock_aioresponses.get(
        REMOTESETTINGS_BASELINE_URL, payload={"data": [RECIPE_42]},
    )
    status, data = await run(NORMANDY_SERVER, REMOTESETTINGS_SERVER)

    assert status is False
    assert data == {
        "baseline": {
            "missing": [_d(REMOTESETTINGS_RECIPE)],
            "extras": [_d(RECIPE_42)],
        },
        "capabilities": {"missing": [_d(REMOTESETTINGS_RECIPE)], "extras": []},
    }


def _d(d):
    return {k: v for k, v in d["recipe"].items() if k in ("id", "name")}
