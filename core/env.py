"""Minimal .env support, so API keys can live in a file instead of the shell (no extra dependency)."""
import os


def load_dotenv(path: str):
    """Read KEY=value lines from path, if it exists. Never overrides variables already set in the shell."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            value = value.strip().strip('"').strip("'")
            if value and key not in os.environ:
                os.environ[key] = value
