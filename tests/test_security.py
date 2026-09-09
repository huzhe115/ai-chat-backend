import jwt
import pytest

from app.security import create_token, decode_token, hash_password, verify_password


def test_hash_and_verify():
    hashed = hash_password("secret123")
    assert hashed != "secret123"  # 不存明文
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_hash_is_salted():
    # 同样的密码两次哈希结果不同(随机盐)
    assert hash_password("secret123") != hash_password("secret123")


def test_token_roundtrip():
    token = create_token(42)
    assert decode_token(token) == 42


def test_tampered_token_rejected():
    token = create_token(42)
    tampered = token[:-4] + "abcd"
    with pytest.raises(jwt.PyJWTError):
        decode_token(tampered)
