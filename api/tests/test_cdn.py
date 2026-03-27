"""Unit tests for CloudFront signed URL generation — no AWS calls."""
import re
import time

import pytest


@pytest.fixture(scope="module")
def rsa_key_pair():
    """Generate a fresh RSA-2048 key pair for tests."""
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        pytest.skip("cryptography library not installed")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key


def test_signed_url_contains_required_params(rsa_key_pair, monkeypatch):
    """Generated URL must contain Expires, Signature, and Key-Pair-Id."""
    monkeypatch.setenv("CLOUDFRONT_DOMAIN", "d123.cloudfront.net")
    monkeypatch.setenv("CLOUDFRONT_KEY_PAIR_ID", "KTEST123")

    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    import app.services.cdn as cdn_mod
    importlib.reload(cdn_mod)

    url = cdn_mod.generate_signed_url(
        "outputs/test-job/image.png",
        expires_in_seconds=3600,
        private_key=rsa_key_pair,
        key_pair_id="KTEST123",
    )

    assert "https://d123.cloudfront.net/outputs/test-job/image.png" in url
    assert "Expires=" in url
    assert "Signature=" in url
    assert "Key-Pair-Id=KTEST123" in url


def test_signed_url_expiry_is_in_future(rsa_key_pair, monkeypatch):
    """Expiry timestamp in URL must be in the future."""
    monkeypatch.setenv("CLOUDFRONT_DOMAIN", "d123.cloudfront.net")

    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    import app.services.cdn as cdn_mod
    importlib.reload(cdn_mod)

    url = cdn_mod.generate_signed_url(
        "outputs/test-job/image.png",
        expires_in_seconds=3600,
        private_key=rsa_key_pair,
        key_pair_id="KTEST123",
    )

    match = re.search(r"Expires=(\d+)", url)
    assert match, "No Expires param in URL"
    expiry = int(match.group(1))
    assert expiry > time.time(), "Expiry should be in the future"
    assert expiry < time.time() + 7200, "Expiry should not be more than 2x the requested duration"


def test_signed_url_raises_without_config(monkeypatch):
    """generate_signed_url raises RuntimeError when CloudFront is not configured."""
    monkeypatch.setenv("CLOUDFRONT_DOMAIN", "")
    monkeypatch.setenv("CLOUDFRONT_KEY_PAIR_ID", "")

    import importlib
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    import app.services.cdn as cdn_mod
    importlib.reload(cdn_mod)

    with pytest.raises(RuntimeError, match="CloudFront not configured"):
        cdn_mod.generate_signed_url("outputs/x/y.png", private_key=None, key_pair_id=None)
