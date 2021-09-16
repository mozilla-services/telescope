from telescope import config


def options_from_params(root_url, client_id, access_token, certificate):
    return {
        "rootUrl": root_url,
        "credentials": (
            {"clientId": client_id.strip(), "accessToken": access_token.strip()}
            if client_id and access_token
            else {"certificate": certificate.strip()}
        ),
        "maxRetries": config.REQUESTS_MAX_RETRIES,
    }
