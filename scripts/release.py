#!/usr/bin/env python3
"""标准发布驱动脚本。

流程：预检 -> 跑测试 -> 写入版本号 -> 提交 -> 打 tag -> 推送。
推送 tag 后由 GitHub Actions（.github/workflows/release.yml）
自动测试、打包并创建 Release 附件。

用法：
    python scripts/release.py 3.1.0
    python scripts/release.py 3.1.0 --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.changelog_notes import extract_section  # noqa: E402
VERSION_FILE = ROOT / "version.py"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"

APP_VERSION_RE = re.compile(r'(APP_VERSION\s*=\s*")([^"]*)(")')


class ReleaseError(RuntimeError):
    pass


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    if not match:
        raise ReleaseError(f"版本号格式不正确: {text}（应为 X.Y.Z）")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def replace_version_text(text: str, version: str) -> str:
    updated, count = APP_VERSION_RE.subn(rf'\g<1>{version}\g<3>', text)
    if count != 1:
        raise ReleaseError("version.py 中未找到 APP_VERSION")
    return updated


def read_current_version() -> str:
    if not VERSION_FILE.is_file():
        raise ReleaseError(f"找不到 {VERSION_FILE}")
    match = APP_VERSION_RE.search(VERSION_FILE.read_text(encoding="utf-8"))
    if not match:
        raise ReleaseError("version.py 中未找到 APP_VERSION")
    return match.group(2)


def repo_slug_from_url(url: str) -> str | None:
    url = url.strip()
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else None


def run(cmd: list[str], *, dry_run: bool = False, capture: bool = False) -> str:
    printable = " ".join(cmd)
    print(f"  $ {printable}")
    if dry_run:
        return ""
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=capture,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ReleaseError(f"命令失败: {printable}\n{detail}")
    return (result.stdout or "").strip() if capture else ""


def git(*args: str, dry_run: bool = False, capture: bool = False) -> str:
    return run(["git", *args], dry_run=dry_run, capture=capture)


def ensure_preconditions(new_version: str, branch: str, dry_run: bool, skip_remote_check: bool) -> None:
    slug = repo_slug_from_url(git("config", "--get", "remote.origin.url", capture=True))
    if not slug:
        raise ReleaseError("无法从 remote.origin.url 解析仓库地址")

    current_branch = git("rev-parse", "--abbrev-ref", "HEAD", capture=True)
    if current_branch != branch:
        raise ReleaseError(f"当前分支为 {current_branch}，请先切换到 {branch}")

    dirty = git("status", "--porcelain", capture=True).splitlines()
    unexpected = [
        line for line in dirty
        if line.strip() and not line[3:].strip().endswith("CHANGELOG.md")
    ]
    if unexpected:
        raise ReleaseError(
            "工作区存在未提交改动（CHANGELOG.md 除外）：\n" + "\n".join(unexpected)
        )

    current = read_current_version()
    if parse_version(new_version) <= parse_version(current):
        raise ReleaseError(f"新版本 {new_version} 必须大于当前版本 {current}")

    if not CHANGELOG_FILE.is_file():
        raise ReleaseError("找不到 CHANGELOG.md")
    section = extract_section(CHANGELOG_FILE.read_text(encoding="utf-8"), new_version)
    if not section:
        raise ReleaseError(
            f"CHANGELOG.md 缺少 ## [{new_version}] 条目。请先按模板写好发布内容。"
        )

    tag = f"v{new_version}"
    local_tags = git("tag", "--list", tag, capture=True)
    if local_tags:
        raise ReleaseError(f"本地已存在 tag {tag}")

    if not skip_remote_check:
        remote_tags = git(
            "ls-remote", "--tags", "origin", f"refs/tags/{tag}", capture=True
        )
        if remote_tags:
            raise ReleaseError(f"远程已存在 tag {tag}")

    print(f"仓库: {slug}")
    print(f"版本: {current} -> {new_version}")
    print(f"发布说明: CHANGELOG.md 中 {len(section)} 字符")


def run_tests(dry_run: bool) -> None:
    print("[3/6] 运行单元测试")
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Type2Speech3 标准发布")
    parser.add_argument("version", help="新版本号，例如 3.1.0")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--dry-run", action="store_true", help="只做检查，不写入/提交/推送")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--no-push", action="store_true", help="只提交并打 tag，不推送")
    parser.add_argument("--skip-remote-check", action="store_true")
    args = parser.parse_args(argv)

    try:
        print("[1/6] 预检")
        ensure_preconditions(
            args.version, args.branch, args.dry_run, args.skip_remote_check
        )

        if not args.skip_tests:
            run_tests(args.dry_run)
        else:
            print("[3/6] 已跳过测试")

        print("[4/6] 写入版本号并提交")
        new_text = replace_version_text(
            VERSION_FILE.read_text(encoding="utf-8"), args.version
        )
        if args.dry_run:
            print(f"  (dry-run) 将写入 version.py: APP_VERSION = \"{args.version}\"")
        else:
            VERSION_FILE.write_text(new_text, encoding="utf-8")
            git("add", "version.py", "CHANGELOG.md")
            git("commit", "-m", f"chore(release): v{args.version}")

        print("[5/6] 创建 tag")
        git(
            "tag", "-a", f"v{args.version}", "-m", f"Type2Speech3 v{args.version}",
            dry_run=args.dry_run,
        )

        print("[6/6] 推送")
        if args.no_push:
            print("  已指定 --no-push，请手动执行:")
            print(f"    git push origin {args.branch}")
            print(f"    git push origin v{args.version}")
        else:
            git("push", "origin", f"HEAD:{args.branch}", dry_run=args.dry_run)
            git("push", "origin", f"v{args.version}", dry_run=args.dry_run)
            slug = repo_slug_from_url(
                git("config", "--get", "remote.origin.url", capture=True)
            ) or "OWNER/REPO"
            print(f"  GitHub Actions: https://github.com/{slug}/actions")

        print("\n发布流程已触发。Actions 会运行测试、打包并创建 Release 附件。")
        return 0
    except ReleaseError as exc:
        print(f"\n发布失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
