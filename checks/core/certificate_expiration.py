"""
SSL certificate should not expire for at least some minimum number of days.

Returns expiration date.
"""

import asyncio
import datetime
import logging
import ssl
from urllib.parse import urlparse

import cryptography
import cryptography.x509
from cryptography.hazmat.backends import default_backend as crypto_default_backend

from telescope.typings import CheckResult
from telescope.utils import fetch_text, utcnow


logger = logging.getLogger(__name__)


EXPOSED_PARAMETERS = [
    "server",
    "percentage_remaining_validity",
    "min_remaining_days",
    "max_remaining_days",
]


# Bound the alert thresholds.
LOWER_MIN_REMAINING_DAYS = 10
UPPER_MIN_REMAINING_DAYS = 30  # No need to warn more than 1 month in advance.


async def fetch_cert(url):
    try:
        # If the URL points to a certificate, then use it as it is.
        cert_pem = await fetch_text(url)
        parsed = cryptography.x509.load_pem_x509_certificate(
            cert_pem.encode("utf8"), backend=crypto_default_backend()
        )
    except ValueError:
        # Otherwise, fetch the SSL certificate from the (host, port).
        parsed_url = urlparse(url)
        host, port = (parsed_url.netloc, parsed_url.port or 443)
        loop = asyncio.get_event_loop()
        cert_pem = await loop.run_in_executor(
            None, lambda: ssl.get_server_certificate((host, port))
        )
        parsed = cryptography.x509.load_pem_x509_certificate(
            cert_pem.encode("utf8"), backend=crypto_default_backend()
        )
    return parsed


async def run(
    url: str,
    percentage_remaining_validity: int = 5,
    min_remaining_days: int = LOWER_MIN_REMAINING_DAYS,
    max_remaining_days: int = UPPER_MIN_REMAINING_DAYS,
) -> CheckResult:
    cert = await fetch_cert(url)
    start = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
    end = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
    lifespan = (end - start).days

    # The minimum remaining days depends on the certificate lifespan.
    relative_minimum = lifespan * percentage_remaining_validity / 100
    bounded_minimum = int(
        min(max_remaining_days, max(min_remaining_days, relative_minimum))
    )
    remaining_days = (end - utcnow()).days

    logger.debug(
        f"Certificate lasts {lifespan} days and ends in {remaining_days} days "
        f"({remaining_days - bounded_minimum} days before alert)."
    )

    success = remaining_days > bounded_minimum
    return success, {
        "expires": end.isoformat(),
    }
