from poucave import config, utils


def options_from_params(root_url, client_id, access_token, certificate):
    return {
        "rootUrl": root_url,
        "credentials": (
            {"clientId": client_id, "accessToken": access_token}
            if client_id and access_token
            else {"certificate": certificate}
        ),
        "maxRetries": config.REQUESTS_MAX_RETRIES,
    }
