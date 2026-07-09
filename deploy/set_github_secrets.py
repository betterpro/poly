from __future__ import annotations

import json
import subprocess
import sys

from dotenv import dotenv_values


def _repo() -> str:
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner,viewerPermission"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return payload["nameWithOwner"], payload["viewerPermission"]


def _active_gh_user() -> str:
    result = subprocess.run(
        ["gh", "api", "user", "-q", ".login"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    try:
        repo, permission = _repo()
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc.stdout or str(exc), file=sys.stderr)
        print("Run: gh auth login", file=sys.stderr)
        return 1

    if permission not in {"ADMIN", "MAINTAIN", "WRITE"}:
        user = _active_gh_user()
        print(
            f"Cannot set secrets on {repo}: active account '{user}' has '{permission}' access.\n"
            "Need ADMIN/MAINTAIN/WRITE. Try:\n"
            "  gh auth switch -u <owner-account>\n"
            "Or ask a repo admin to add secrets under Settings -> Secrets and variables -> Actions.",
            file=sys.stderr,
        )
        return 1

    cfg = dotenv_values(".env")
    secrets = {
        "RAILWAY_TOKEN": cfg.get("RAILWAY_TOKEN"),
        "POLYMARKET_API_KEY": cfg.get("POLYMARKET_API_KEY") or "",
        "POLYMARKET_API_SECRET": (cfg.get("POLYMARKET_API_SECRET") or "").strip('"'),
        "POLYMARKET_API_PASSPHRASE": cfg.get("POLYMARKET_API_PASSPHRASE") or "",
        "POLYMARKET_PRIVATE_KEY": cfg.get("POLYMARKET_PRIVATE_KEY") or "",
        "POLYMARKET_FUNDER_ADDRESS": cfg.get("POLYMARKET_FUNDER_ADDRESS") or "",
    }

    print(f"Setting secrets on {repo} as {_active_gh_user()}...")
    for name, value in secrets.items():
        if not value:
            print(f"skip {name} (empty)")
            continue
        subprocess.run(["gh", "secret", "set", name, "--body", value, "--repo", repo], check=True)
        print(f"set {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
