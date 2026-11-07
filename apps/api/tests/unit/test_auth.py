"""Supabase JWT verification with a local ES256 key and a fake JWKS."""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from split_ranch.core.errors import TokenExpired, Unauthenticated
from split_ranch.core.security import TokenVerifier
from tests.conftest import ISSUER, FakeJWKS, SigningKey, make_token


@pytest.fixture
def verifier(signing_key: SigningKey) -> TokenVerifier:
    return TokenVerifier(
        jwks_url="https://unused.invalid", issuer=ISSUER, key_source=FakeJWKS([signing_key])
    )


def test_valid_token(verifier: TokenVerifier, signing_key: SigningKey) -> None:
    uid = uuid.uuid4()
    claims = verifier.verify(make_token(signing_key, uid, name="Juli", email="juli@example.com"))
    assert claims.user_id == uid
    assert claims.email == "juli@example.com"
    assert claims.display_name == "Juli"


def test_expired_token(verifier: TokenVerifier, signing_key: SigningKey) -> None:
    with pytest.raises(TokenExpired):
        verifier.verify(make_token(signing_key, uuid.uuid4(), exp_in=-120))


def test_expiry_leeway(verifier: TokenVerifier, signing_key: SigningKey) -> None:
    verifier.verify(make_token(signing_key, uuid.uuid4(), exp_in=-10))


def test_wrong_issuer(verifier: TokenVerifier, signing_key: SigningKey) -> None:
    with pytest.raises(Unauthenticated) as exc:
        verifier.verify(make_token(signing_key, uuid.uuid4(), iss="https://evil.example/auth/v1"))
    assert exc.value.code == "unauthenticated"


def test_wrong_audience(verifier: TokenVerifier, signing_key: SigningKey) -> None:
    with pytest.raises(Unauthenticated):
        verifier.verify(make_token(signing_key, uuid.uuid4(), aud="anon"))


@pytest.mark.parametrize("role", ["anon", "service_role"])
def test_non_authenticated_role(
    verifier: TokenVerifier, signing_key: SigningKey, role: str
) -> None:
    with pytest.raises(Unauthenticated):
        verifier.verify(make_token(signing_key, uuid.uuid4(), role=role))


def test_hs256_rejected(verifier: TokenVerifier, signing_key: SigningKey) -> None:
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iss": ISSUER,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": now + 3600,
        },
        "super-secret-jwt-key-with-enough-length-0123456789",
        algorithm="HS256",
        headers={"kid": signing_key.kid},
    )
    with pytest.raises(Unauthenticated):
        verifier.verify(token)


def test_none_alg_rejected(verifier: TokenVerifier) -> None:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "iss": ISSUER, "aud": "authenticated", "role": "authenticated"},
        None,
        algorithm="none",
    )
    with pytest.raises(Unauthenticated):
        verifier.verify(token)


def test_unknown_kid(verifier: TokenVerifier, signing_key: SigningKey) -> None:
    with pytest.raises(Unauthenticated):
        verifier.verify(make_token(signing_key, uuid.uuid4(), kid="rotated-away"))


def test_signed_by_other_key(verifier: TokenVerifier) -> None:
    other = SigningKey("test-key-1", ec.generate_private_key(ec.SECP256R1()))
    with pytest.raises(Unauthenticated):
        verifier.verify(make_token(other, uuid.uuid4()))


def test_garbage_token(verifier: TokenVerifier) -> None:
    with pytest.raises(Unauthenticated):
        verifier.verify("not-a-jwt")
