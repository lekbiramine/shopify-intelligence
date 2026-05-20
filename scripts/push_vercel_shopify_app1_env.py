"""Sync SHOPIFY_APP_1_KEY / SHOPIFY_APP_1_SECRET from .env to Vercel."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def _npx_executable() -> str:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx:
        return npx
    candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "npx.cmd"
    if candidate.is_file():
        return str(candidate)
    raise FileNotFoundError("npx not found; install Node.js or add npx to PATH.")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")

    key = (os.getenv("SHOPIFY_APP_1_KEY") or os.getenv("SHOPIFY_API_KEY") or "").strip()
    secret = (os.getenv("SHOPIFY_APP_1_SECRET") or os.getenv("SHOPIFY_API_SECRET") or "").strip()
    if not key or not secret:
        print(
            "ERROR: Set SHOPIFY_APP_1_KEY/SECRET or SHOPIFY_API_KEY/SECRET in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    npx = _npx_executable()
    # (name, environment). Preview uses "" as git-branch arg = all preview branches (CLI workaround).
    targets: list[tuple[str, str]] = [
        ("SHOPIFY_APP_1_KEY", "production"),
        ("SHOPIFY_APP_1_SECRET", "production"),
        ("SHOPIFY_APP_1_KEY", "preview"),
        ("SHOPIFY_APP_1_SECRET", "preview"),
        ("SHOPIFY_APP_1_KEY", "development"),
        ("SHOPIFY_APP_1_SECRET", "development"),
    ]

    for name, target in targets:
        value = key if name.endswith("_KEY") else secret
        cmd = [
            npx,
            "--yes",
            "vercel@54.2.0",
            "env",
            "add",
            name,
            target,
        ]
        if target == "preview":
            cmd.append("")  # all Preview branches; required for non-interactive CLI
        cmd.extend(["--value", value, "--yes", "--force", "--non-interactive"])
        print(f"vercel env add {name} {target}")
        r = subprocess.run(cmd, cwd=str(root))
        if r.returncode != 0:
            sys.exit(r.returncode)

    print("VERCEL_ENV_OK")


if __name__ == "__main__":
    main()
