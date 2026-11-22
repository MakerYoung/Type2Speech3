# Changelog

本文件记录 Type2Speech3 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [3.1.0] - 2026-11-22

### Added

- 游戏窗口识别支持进程名与内置别名（如 `cs2.exe`、`VALORANT-Win64-Shipping.exe`、`LeagueClientUx.exe`）
- 主界面新增“游戏检测”实时命中状态，以及“游戏列表”关键词编辑入口
- 历史记录、预设音频右键支持“打开所在文件夹”；预设文本右键支持“打开数据文件夹”

### Changed

- Qt 绑定从 PyQt5（GPL）迁移到 PySide6 6.8.3（LGPL），解决闭源商用的许可证问题，功能与界面保持不变
- 扩充默认游戏关键词列表；未自定义过的旧默认列表会自动升级
- 播放前做最后一次游戏窗口校验：开麦状态下未命中时只播放、不注入开麦键，避免语音漏到其他程序
- 已在前台游戏窗口时不再重复抢焦点
- 发布流水线新增成品启动冒烟测试，打包后自动验证 exe 可启动并生成配置

### Upgrade Notes

- 无破坏性变更；旧配置与历史记录可继续使用。
- 未自定义过的旧默认游戏列表会自动升级到扩充后的列表。
- Qt 绑定迁移不影响数据目录与配置格式。

## [3.0.1] - 2026-11-21

### Added

- 标准发布流程：`CHANGELOG.md`、`RELEASING.md`、发布说明模板与 `scripts/release.py`
- GitHub Actions：CI 单元测试；tag 触发自动打包、生成 SHA256 并发布 Release 附件
- 发布工具单元测试（CHANGELOG 提取、版本校验、仓库地址解析）

### Fixed

- 修复 CI 打包时 PNG 图标未转换导致 PyInstaller 构建失败（改用预生成的 `resources/icon.ico`）

## [3.0.0] - 2026-11-21

### Added

- 新增 `app/` 服务层：路径、配置、历史、预设、热键、播放调度
- 新增 29 项服务层单元测试（配置 / 迁移 / 预设 / 历史 / 热键 / 引擎契约 / 播放状态机）
- 打包时自动包含 `resources/icon.png`

### Changed

- 用户数据统一迁移到 `%APPDATA%\Type2Speech3`，首次启动自动迁移旧 `conf/`、`preset_audio/`
- 配置改为原子写入；默认值深拷贝，修复多实例共享可变状态
- 热键注册 / 注销统一在监听线程内完成，线程可安全退出
- EdgeTTS 输出文件后缀改为 `.mp3`（实际编码格式）
- `MainWindow` 只保留界面与信号绑定，业务逻辑移至 `app/`

### Fixed

- 修复「停止播放」后「开始转换」按钮永久变灰
- 修复编辑预设文本崩溃、快捷键不会跟随文本迁移
- 修复首次运行无法保存预设（`presets_text` 默认类型错误）
- 修复无输出设备时启动即崩溃
- 修复 PyTTSX3 语速设置无效
- 修复右键菜单“当前快捷键”永远显示为空
- 修复同一秒内多次转换音频文件互相覆盖
- 修复音色加载与播放回调竞态（过期结果会被丢弃）
- 修复 Edge TTS 403（`Sec-MS-GEC-Version` 校验升级，依赖 edge-tts 7.3.1）

### Removed

- 移除 `utils/config_manager.py`、`utils/history_manager.py`（由 `app/config.py`、`app/history.py` 取代）
- 清理注释掉的死代码与未使用导入

### Upgrade Notes

- 首次启动会自动把旧 `conf/`、`preset_audio/` 迁移到 `%APPDATA%\Type2Speech3`，原文件保留。
- 如需自定义数据目录，设置环境变量 `TYPE2SPEECH_DATA_DIR`。
- 旧历史记录的音频路径仍然有效；重新生成后新文件会写入新的数据目录。

[Unreleased]: https://github.com/MakerYoung/Type2Speech3/compare/v3.1.0...HEAD
[3.1.0]: https://github.com/MakerYoung/Type2Speech3/releases/tag/v3.1.0
[3.0.1]: https://github.com/MakerYoung/Type2Speech3/releases/tag/v3.0.1
[3.0.0]: https://github.com/MakerYoung/Type2Speech3/releases/tag/v3.0.0
