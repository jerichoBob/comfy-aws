"""CloudFront signed URL generation.

On startup (when CLOUDFRONT_DOMAIN is set), the private key PEM is fetched
from SSM Parameter Store and cached in memory. URL signing is done locally
using RSA + SHA-1 (CloudFront's required algorithm) — zero per-request latency,
zero cost.

When CLOUDFRONT_DOMAIN is empty (local dev), this module is a no-op and callers
fall back to S3 presigned URLs.
"""
import base64
import hashlib
import hmac
import json
import logging
import struct
import time
from datetime import datetime, timezone
from typing import Optional

import aioboto3

from app.config import settings

logger = logging.getLogger(__name__)

_session = aioboto3.Session()

# Private key loaded once at startup
_private_key = None


def _client_kwargs() -> dict:
    kwargs = {"region_name": settings.aws_default_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return kwargs


async def load_private_key() -> None:
    """Fetch the CloudFront private key PEM from SSM and cache it.

    Called once during startup if CLOUDFRONT_DOMAIN is configured.
    """
    global _private_key
    if not settings.cloudfront_domain:
        return

    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        async with _session.client("ssm", **_client_kwargs()) as ssm:
            response = await ssm.get_parameter(
                Name=settings.cloudfront_private_key_ssm_path,
                WithDecryption=False,
            )
        pem = response["Parameter"]["Value"]
        _private_key = serialization.load_pem_private_key(
            pem.encode(), password=None, backend=default_backend()
        )
        logger.info("CloudFront private key loaded from SSM")
    except Exception as exc:
        logger.error("Failed to load CloudFront private key from SSM: %s", exc)
        raise


def _cf_base64(data: bytes) -> str:
    """CloudFront-safe base64: replace +, =, / with -, _, ~"""
    b64 = base64.b64encode(data).decode()
    return b64.replace("+", "-").replace("=", "_").replace("/", "~")


def generate_signed_url(
    s3_key: str,
    expires_in_seconds: int = 604800,  # 7 days default
    private_key=None,
    key_pair_id: Optional[str] = None,
) -> str:
    """Generate a CloudFront signed URL for the given S3 key.

    Uses canned policy (simpler than custom policy; sufficient for single-path URLs).

    Args:
        s3_key: S3 object key, e.g. "outputs/job-id/image.png"
        expires_in_seconds: URL validity duration in seconds
        private_key: RSA private key object (for testing — pass directly without SSM)
        key_pair_id: CloudFront key pair ID (for testing)

    Returns:
        Fully-qualified signed CloudFront URL string
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    key = private_key or _private_key
    kp_id = key_pair_id or settings.cloudfront_key_pair_id
    domain = settings.cloudfront_domain

    if not key or not domain or not kp_id:
        raise RuntimeError("CloudFront not configured — cannot generate signed URL")

    url = f"https://{domain}/{s3_key}"
    expiry = int(time.time()) + expires_in_seconds

    policy = json.dumps(
        {"Statement": [{"Resource": url, "Condition": {"DateLessThan": {"AWS:EpochTime": expiry}}}]},
        separators=(",", ":"),
    )
    policy_bytes = policy.encode()

    signature = key.sign(policy_bytes, padding.PKCS1v15(), hashes.SHA1())  # noqa: S303 — CloudFront requires SHA-1

    return (
        f"{url}"
        f"?Expires={expiry}"
        f"&Signature={_cf_base64(signature)}"
        f"&Key-Pair-Id={kp_id}"
    )


def is_configured() -> bool:
    """Return True if CloudFront is configured and ready for URL signing."""
    return bool(settings.cloudfront_domain and _private_key)
