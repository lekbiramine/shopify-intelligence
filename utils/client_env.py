import os
from pathlib import Path

from dotenv import load_dotenv


def load_client_env(env_file: str | None) -> Path | None:
    if not env_file:
        return None
    path = Path(env_file).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Client env file not found: {path}")
    load_dotenv(dotenv_path=path, override=True)
    return path


def env_value(*keys: str, default: str = "") -> str:
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return default
