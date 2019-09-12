import logging
import time
from datetime import datetime

from aiohttp import web
from aiohttp.web import middleware


logger = logging.getLogger(__name__)
summary_logger = logging.getLogger("request.summary")


@middleware
async def request_summary(request, handler):
    # Bind infos for request summary logger.
    previous_time = time.time()
    infos = {
        "agent": request.headers.get("User-Agent"),
        "path": str(request.rel_url),
        "method": request.method,
        "lang": request.headers.get("Accept-Language"),
        "querystring": dict(request.query),
        "errno": 0,
    }

    response = await handler(request)

    current = time.time()
    duration = int((current - previous_time) * 1000.0)
    isotimestamp = datetime.fromtimestamp(current).isoformat()
    infos = {"time": isotimestamp, "code": response.status, "t": duration, **infos}

    summary_logger.info("", extra=infos)

    return response


@web.middleware
async def error_middleware(request, handler):
    try:
        response = await handler(request)
        return response

    except web.HTTPException:
        # HTTP exceptions are served with framework defaults.
        raise

    except Exception as e:
        # Unexpected errors are returned as JSON with 500 status.
        logger.exception(e)
        body = {"success": False, "data": str(e)}
        return web.json_response(body, status=web.HTTPInternalServerError.status_code)
