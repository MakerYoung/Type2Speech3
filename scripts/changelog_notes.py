#!/usr/bin/env python3
"""从 CHANGELOG.md 提取指定版本的发布说明。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"

HEADER_RE = re.compile(
    r"^##\s+\[?(?P<version>\d+\.\d+\.\d+)\]?(?:\s*-\s*\d{4}-\d{2}-\d{2})?\s*$"
)


def extract_section(text: str, version: str) -> str | None:
    """返回 `## [version]` 与下一个 `## ` 之间的正文；找不到或为空返回 None。"""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        match = HEADER_RE.match(line.strip())
        if match and match.group("version") == version:
            start = index + 1
            break
    if start is None:
        return None

    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    section = "\n".join(body).strip()
    return section or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提取 CHANGELOG 中某个版本的发布说明")
    parser.add_argument("version", help="版本号，例如 3.0.0")
    parser.add_argument("-o", "--output", help="写入文件（默认输出到 stdout）")
    parser.add_argument("--changelog", default=str(DEFAULT_CHANGELOG), help="CHANGELOG 路径")
    args = parser.parse_args(argv)

    changelog = Path(args.changelog)
    if not changelog.is_file():
        print(f"找不到 {changelog}", file=sys.stderr)
        return 1

    section = extract_section(changelog.read_text(encoding="utf-8"), args.version)
    if section is None:
        print(f"CHANGELOG 中没有 {args.version} 的条目", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(section + "\n", encoding="utf-8")
    else:
        print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
