"""Real google-auth verification of signed JWTs, with a throwaway key standing in for Google's.

Only the certificate download is faked. Signature, issuer, audience and expiry checks are
google-auth's own, so this proves our wiring rejects what it must.
"""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt, jwt

from app.config import get_settings
from app.errors import AppError
from app.services.google import verify_google_credential

CLIENT_ID = "test-client-id"  # set in conftest
ISSUER = "https://accounts.google.com"


def make_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return private_pem, cert.public_bytes(serialization.Encoding.PEM).decode()


GOOGLE_KEY, GOOGLE_CERT = make_key()
OTHER_KEY, _ = make_key()


class FakeCertsResponse:
    status = 200
    headers: dict = {}  # noqa: RUF012

    def __init__(self, certs: dict[str, str]) -> None:
        self.data = json.dumps(certs).encode()


@pytest.fixture(autouse=True)
def google_certs(monkeypatch):
    def fake_request(url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        assert "googleapis.com" in url
        return FakeCertsResponse({"kid-1": GOOGLE_CERT})

    monkeypatch.setattr("app.services.google._transport", lambda: fake_request)


def sign(claims: dict, key: bytes = GOOGLE_KEY) -> str:
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "1101",
        "email": "g.user@example.com",
        "email_verified": True,
        "name": "G User",
        "picture": "https://lh3.example.com/p.png",
        "iat": now,
        "exp": now + 3600,
    }
    payload.update(claims)
    payload = {k: v for k, v in payload.items() if v is not None}
    signer = crypt.RSASigner.from_string(key, key_id="kid-1")
    return jwt.encode(signer, payload).decode()


async def test_valid_token_yields_claims():
    claims = await verify_google_credential(sign({}))
    assert (claims.sub, claims.email, claims.email_verified, claims.name) == (
        "1101",
        "g.user@example.com",
        True,
        "G User",
    )
    assert claims.picture == "https://lh3.example.com/p.png"


@pytest.mark.parametrize(
    ("label", "override", "key"),
    [
        ("wrong audience", {"aud": "someone-elses-client-id"}, GOOGLE_KEY),
        ("wrong issuer", {"iss": "https://evil.example.com"}, GOOGLE_KEY),
        ("expired", {"iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600}, GOOGLE_KEY),
        ("signed with another key", {}, OTHER_KEY),
        ("no subject", {"sub": None}, GOOGLE_KEY),
        ("no email", {"email": None}, GOOGLE_KEY),
    ],
)
async def test_bad_tokens_are_rejected(label, override, key):
    with pytest.raises(AppError) as excinfo:
        await verify_google_credential(sign(override, key))
    assert excinfo.value.status == 401
    assert excinfo.value.code == "invalid_google_token", label


async def test_garbage_is_rejected():
    for junk in ("not-a-jwt", "a.b.c", ""):
        with pytest.raises(AppError) as excinfo:
            await verify_google_credential(junk)
        assert excinfo.value.code == "invalid_google_token"


async def test_accepts_the_legacy_issuer_form():
    claims = await verify_google_credential(sign({"iss": "accounts.google.com"}))
    assert claims.sub == "1101"


async def test_email_verified_variants():
    assert (await verify_google_credential(sign({"email_verified": "true"}))).email_verified is True
    assert (await verify_google_credential(sign({"email_verified": False}))).email_verified is False
    assert (await verify_google_credential(sign({"email_verified": None}))).email_verified is False
    assert (await verify_google_credential(sign({"email_verified": "false"}))).email_verified is False


async def test_non_https_picture_is_dropped():
    assert (await verify_google_credential(sign({"picture": "http://x.example.com/p.png"}))).picture is None
    assert (await verify_google_credential(sign({"picture": "javascript:alert(1)"}))).picture is None


async def test_not_configured_returns_503(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    with pytest.raises(AppError) as excinfo:
        await verify_google_credential(sign({}))
    assert (excinfo.value.status, excinfo.value.code) == (503, "google_not_configured")


async def test_endpoint_with_the_real_verifier_end_to_end(client, db):
    ok = await client.post("/api/auth/google", json={"credential": sign({"sub": "e2e-sub"})})
    assert ok.status_code == 200
    assert ok.json()["email"] == "g.user@example.com"
    client.cookies.clear()
    forged = await client.post("/api/auth/google", json={"credential": sign({"sub": "e2e-sub"}, OTHER_KEY)})
    assert forged.status_code == 401
    assert forged.json()["error"]["code"] == "invalid_google_token"


async def test_auth_config_exposes_only_the_public_client_id(client):
    body = (await client.get("/api/auth/config")).json()
    assert body == {"google_client_id": CLIENT_ID}
