"""
The age of the specified resource at URL should be less than the specified maximum.

The age in hours is returned.
"""

from telescope.typings import CheckResult
from telescope.utils import fetch_head, utcfromhttpdate, utcnow


EXPOSED_PARAMETERS = ["url", "max_age_hours"]
DEFAULT_PLOT = ".age_hours"


async def run(url: str, max_age_hours: int) -> CheckResult:
    _, headers = await fetch_head(url)

    last_modified = headers.get("Last-Modified", "Mon, 01 Jan 1970 00:00:00 GMT")
    try:
        last_modified_dt = utcfromhttpdate(last_modified)
    except ValueError:
        return False, {"error": f"Invalid Last-Modified header: {last_modified!r}"}

    age_hours = int((utcnow() - last_modified_dt).total_seconds() / 3600)

    return age_hours < max_age_hours, {"age_hours": age_hours}
