"""Password hashing with bcrypt."""

import bcrypt


def hash_password(password: str) -> str:
    # gensalt() creates a random salt; bcrypt stores it inside the hash itself.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())
