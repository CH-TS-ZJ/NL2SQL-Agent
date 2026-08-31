"""
认证安全工具

提供密码哈希与校验、JWT 签发与解析的纯函数。
密码用 stdlib PBKDF2-SHA256 加随机盐哈希，避免引入额外依赖；
JWT 用 PyJWT 的 HS256 签名，secret 从应用配置读取。
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.conf.app_config import app_config

# PBKDF2 迭代次数，兼顾安全性与登录耗时
PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """把明文密码哈希为单字符串 pbkdf2_sha256$iterations$salt$hash"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """校验明文密码与已存哈希是否匹配，使用恒时比较避免时序攻击"""
    try:
        _, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str) -> str:
    """签发带过期时间的 JWT，claims 用 sub 承载用户编号"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=app_config.auth.expire_minutes),
    }
    return jwt.encode(
        payload, app_config.auth.secret_key, algorithm=app_config.auth.algorithm
    )


def decode_access_token(token: str) -> str:
    """解析 JWT 并返回用户编号；签名或过期校验失败时抛出 jwt 异常"""
    payload = jwt.decode(
        token, app_config.auth.secret_key, algorithms=[app_config.auth.algorithm]
    )
    return payload["sub"]
