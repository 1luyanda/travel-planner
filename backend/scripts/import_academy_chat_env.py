"""Copy Academy Day 9 chat-model settings into this project's local .env.

Reads the source file in memory and writes only chat variables.
Does not print secret values. Leaves the Academy file unchanged.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

# backend/scripts -> backend -> Team-4-Final-Project -> Academy2026
SOURCE = Path(__file__).resolve().parents[3] / "SNyamfu" / "AI" / "Day9_Tasks" / ".env"
DEST = Path(__file__).resolve().parents[2] / ".env"

CHAT_KEYS = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    if not SOURCE.is_file():
        print(f"SOURCE_MISSING {SOURCE}")
        return 1

    source_values = _parse_env(SOURCE)
    copied: dict[str, str] = {}
    missing: list[str] = []
    for key in CHAT_KEYS:
        value = source_values.get(key, "").strip()
        if not value:
            missing.append(key)
        else:
            copied[key] = value

    if missing:
        print("MISSING_SOURCE_KEYS", ", ".join(missing))
        return 1

    existing: dict[str, str] = {}
    if DEST.is_file():
        existing = _parse_env(DEST)
        for key in CHAT_KEYS:
            existing.pop(key, None)

    lines = [
        "# Local chat-model settings. Do not commit this file.",
        "# Source: SNyamfu/AI/Day9_Tasks/.env (chat variables only).",
    ]
    for key, value in existing.items():
        lines.append(f"{key}={value}")
    if existing:
        lines.append("")
    for key in CHAT_KEYS:
        lines.append(f"{key}={copied[key]}")
    DEST.write_text("\n".join(lines) + "\n", encoding="utf-8")

    endpoint = copied["AZURE_OPENAI_ENDPOINT"]
    parsed = urlparse(endpoint)
    path = parsed.path or "/"
    if path.rstrip("/").lower().endswith("/openai/v1"):
        style = "openai_v1_base"
    elif path in {"", "/"}:
        style = "azure_resource_root"
    else:
        style = "azure_endpoint_with_path"

    print("source_file=SNyamfu/AI/Day9_Tasks/.env")
    print("source_client=langchain_openai.AzureChatOpenAI")
    print("copied_keys=" + ",".join(CHAT_KEYS))
    print(f"endpoint_style={style}")
    print(f"dest_written={DEST.name}")
    print("embedding_keys_copied=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
