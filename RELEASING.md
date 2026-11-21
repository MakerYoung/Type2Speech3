# 发布流程

本项目采用 **SemVer + Keep a Changelog + GitHub Actions** 的标准发布流程。

## 1. 版本规则

- **MAJOR**：不兼容变更（数据格式、配置位置、快捷键语义等）
- **MINOR**：向后兼容的新功能
- **PATCH**：向后兼容的 Bug 修复

版本号唯一来源：`version.py` 中的 `APP_VERSION`。
窗口标题、Release 标题、tag、资产文件名都由它派生。

## 2. 一次发布包含什么

| 内容 | 位置 |
|---|---|
| 版本号 | `version.py` → `APP_VERSION` |
| 变更记录 | `CHANGELOG.md` 中 `## [X.Y.Z] - YYYY-MM-DD` |
| Git tag | 附注 tag `vX.Y.Z` |
| GitHub Release | 标题 `Type2Speech3 vX.Y.Z`，正文取自 CHANGELOG |
| Windows 包 | `Type2Speech3-vX.Y.Z-win64.zip`（PyInstaller onedir） |
| 校验文件 | 同名 `.sha256` |

发布说明必须按 `docs/release-notes-template.md` 的章节组织，CI 会自动把
CHANGELOG 中该版本的正文作为 Release 正文。

## 3. 操作步骤

### 3.1 发布前

1. 确认在 `main` 分支且工作区干净（`CHANGELOG.md` 的编辑除外）。
2. 确认 GitHub Actions 的 CI 为绿色。
3. 本地验证：

   ```bash
   python -m unittest discover -s tests -v
   python -m PyInstaller main.spec --noconfirm   # 可选，本地打包验证
   ```

### 3.2 写发布内容

编辑 `CHANGELOG.md`，把 `[Unreleased]` 下的内容整理到新版本标题下：

```markdown
## [3.1.0] - 2026-12-01

### Added
- ...
### Changed
- ...
### Fixed
- ...
### Upgrade Notes
- 数据迁移、配置变化、需要用户手动操作的事项
```

规则：

- 面向用户描述“发生了什么变化”，不要写提交号。
- 破坏性变更必须在 **Upgrade Notes** 中说明迁移方式。
- 已知限制单独列出，避免用户在 Release 里重复提问。

### 3.3 执行发布脚本

```bash
python scripts/release.py 3.1.0 --dry-run   # 先检查
python scripts/release.py 3.1.0
```

脚本会依次：

1. 预检分支、工作区、版本递增、CHANGELOG 条目、远程 tag 冲突
2. 运行单元测试
3. 写入 `version.py`
4. 提交 `CHANGELOG.md` + `version.py`（`chore(release): vX.Y.Z`）
5. 创建附注 tag `vX.Y.Z`
6. 推送 `main` 与 tag

推送 tag 后，`.github/workflows/release.yml` 自动执行：

- 安装依赖 + 单元测试
- PyInstaller 打包
- 压缩 `dist/main` 并生成 SHA256
- 从 CHANGELOG 提取发布说明
- 创建或更新 GitHub Release 并上传两个附件

### 3.4 发布后验证

- [ ] Release 页面的正文与 CHANGELOG 一致
- [ ] `.zip` 与 `.sha256` 均可下载
- [ ] 解压后 `main.exe` 可启动，标题显示新版本号
- [ ] 首次启动数据位于 `%APPDATA%\Type2Speech3`
- [ ] EdgeTTS / PyTTSX3 至少各测一次合成与播放

## 4. 发布说明模板

见 [`docs/release-notes-template.md`](docs/release-notes-template.md)。
CI 使用 `scripts/changelog_notes.py` 从 CHANGELOG 提取对应版本内容，
所以模板本质上就是 CHANGELOG 的条目格式。

## 5. 重跑 / 补传附件

Actions → **Release** → **Run workflow**，输入已有 tag（例如 `v3.0.0`）：

- 会重新测试、打包，并把 `.zip` + `.sha256` 上传到该 Release（已存在则覆盖）。
- 同时用 CHANGELOG 中对应版本更新 Release 正文。
- 不会移动或重建 tag。

## 6. 手动发布（CI 不可用时）

```bash
python -m PyInstaller main.spec --noconfirm
powershell -Command "Compress-Archive -Path 'dist/main/*' -DestinationPath 'Type2Speech3-vX.Y.Z-win64.zip' -Force"
python scripts/changelog_notes.py X.Y.Z -o release_notes.md

gh release create vX.Y.Z \
  --title "Type2Speech3 vX.Y.Z" \
  --notes-file release_notes.md \
  "Type2Speech3-vX.Y.Z-win64.zip"
```

如果没有 `gh` CLI，也可以在 GitHub 网页上创建 Release 并手动上传附件。

## 7. 回滚

| 阶段 | 操作 |
|---|---|
| 尚未推送 | `git tag -d vX.Y.Z`，恢复 `version.py` |
| 已推送、CI 失败 | 删除远程 tag：`git push origin :refs/tags/vX.Y.Z`，修复后重新发布 |
| Release 已创建但有问题 | 删除 Release 与 tag，重新发布；不要复用已发布的 tag |
| 已有人下载 | 发布 PATCH 版本修复，不移动已有 tag |

已发布过的 tag 视为不可变；修正问题请发布新的 PATCH/MINOR 版本。

## 8. 凭据与网络

- 发布脚本只负责推送，不需要 Token。
- CI 使用仓库自带的 `GITHUB_TOKEN`（`permissions: contents: write`）。
- 本地手动创建 Release 时，`GH_TOKEN` 通过环境变量提供，**不要写入仓库或 CHANGELOG**。
- 本机如使用 TLS 代理（例如 Steamcommunity302），git 已配置代理/证书策略；
  若用 curl/Python 调 GitHub API，需要 `--cacert` 或 `SSL_CERT_FILE` 指向代理 CA。
