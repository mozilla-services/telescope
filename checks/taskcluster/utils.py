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


async def list_artifacts(queue, task_id, run_id):
    """Helper to list all task artifacts."""
    page = await queue.listArtifacts(task_id, run_id)
    artifacts = page.get("artifacts", [])
    while page.get("continuationToken"):
        artifacts += page.get("artifacts", [])
        page = await queue.listArtifacts(
            task_id,
            run_id,
            query={"continuationToken": page.get("continuationToken")},
        )
    futures = [
        queue.artifact(task_id, run_id, artifact["name"]) for artifact in artifacts
    ]
    infos = await utils.run_parallel(*futures)
    return infos
