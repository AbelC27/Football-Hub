from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

try:
    hash = pwd_context.hash("password123")
    print(f"Hash generated: {hash}")
    verify = pwd_context.verify("password123", hash)
    print(f"Verification: {verify}")
except Exception as e:
    print(f"Error: {e}")
