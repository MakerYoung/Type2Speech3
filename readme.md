# Type2Speech3 项目介绍与使用（v3.0.0）

## 简介

`Type2Speech3`，又名 `我是你的嘴` 是一个运行在 Windows 上的桌面文本转语音（TTS）工具，基于 **PyQt5** 构建 UI，并使用 **qdarktheme** 提供现代化主题。项目支持：

- 文本一键合成语音并播放，播放到扬声器，结合voiceMeeter banana 播放到麦克风
- 文本预设、音频预设（本地音频快捷播放）
- 全局系统快捷键（Windows API `RegisterHotKey` 监听）
- 多种 TTS 引擎：本地 `pyttsx3` / 在线 `edge-tts`（另含在线 API 骨架）
- 记忆上次选择的输出设备、引擎、音色、语速、音量等

应用入口为 `main.py`，主窗口实现位于 `ui/main_window.py`。


## 典型用法
- 本应用界面的输出设备选voicemeeter banana 的 voicemeeter aux input。
- 然后在voicemeeter banana把对应通道输出到B1。
- 在需要接收音频的应用（一般来说系统的麦克风与扬声器设置，以及游戏或其他应用内的麦克风与扬声器设置），将麦克风选择对应的B1虚拟设备即可
- 本应用界面里设置好游戏内的开麦快捷键或保持开麦
- 游戏内按快捷键播放预设音频

## 目录结构（关键部分）

- `main.py`: 程序入口，创建 `QApplication` 并显示主窗口
- `ui/`: UI 层（`ui/main_window.py` 为主窗口，只负责界面与信号绑定）
- `app/`: 应用服务层
  - `app/paths.py`: 数据目录解析与旧数据迁移
  - `app/config.py`: 配置读写（原子写入、默认值校正）
  - `app/history.py`: 历史记录模型与存储
  - `app/presets.py`: 文本/音频预设管理
  - `app/hotkeys.py`: 热键注册表与监听线程生命周期
  - `app/playback.py`: 合成/播放任务调度
- `core/`: TTS 引擎、后台 worker、音频设备管理等
  - `core/engines/pyttsx3_engine.py`: 本地 TTS
  - `core/engines/edge_tts_engine.py`: Edge 在线 TTS
  - `core/engines/api_engine.py`: 在线 API 引擎骨架（未实现，供二次开发）
  - `core/audio_manager.py`: 输出设备枚举（PyAudio）
- `utils/`: Windows 底层工具
  - `utils/hotkey_manager.py`: Windows 全局热键监听
  - `utils/keyboard_injector.py`: 游戏内开麦按键注入
  - `utils/window_manager.py`: 游戏窗口聚焦
- `tests/`: 服务层单元测试（`python -m unittest discover -s tests`）
- `resources/`: 图标等资源（`resources/icon.png`）

## 用户数据目录

自 v3.0.0 起，配置、历史、生成音频和预设音频统一存放在：

```
%APPDATA%\Type2Speech3\
├── conf\config.json
├── conf\history.json
├── audios\
└── preset_audio\
```

- 首次运行会自动从旧的 `conf/`、`preset_audio/` 位置迁移一次，不影响原文件。
- 可通过环境变量 `TYPE2SPEECH_DATA_DIR` 指定其它目录。
- 数据与程序目录分离，重新打包/覆盖安装不会清空配置。

## 运行环境

- **操作系统**：Windows 10/11
- **Python**：建议 3.10+（若你使用更高版本也通常可行）

## 安装依赖

安装 `requirements.txt`：

```bash
python -m pip install -r requirements.txt
```


或可先按需安装核心依赖。在 PowerShell 中执行：

```bash
python -m pip install -U pip
python -m pip install PyQt5 qdarktheme pyttsx3 edge-tts pyaudio
```

### 关于 `pyaudio`（常见安装问题）

`pyaudio` 在 Windows 上可能需要匹配的预编译 wheel。若 `pip install pyaudio` 失败，可尝试：

- 先安装 Microsoft C++ Build Tools 后重试
- 或改用可用的预编译 wheel（根据你的 Python 版本/系统架构选择）

（具体报错与解决方式取决于你的 Python 版本与环境；优先以错误信息为准。）

## 运行项目

在项目根目录执行：

```bash
python main.py
```

## 配置文件说明

配置文件默认为 `%APPDATA%\Type2Speech3\conf\config.json`，部分常用字段示例（以实际文件为准）：

- `last_device_name`: 上次选择的输出设备名（用于回显）
- `last_engine`: 上次使用的引擎（如 `EdgeTTS` / `PyTTSX3`）
- `last_voice_id`: 上次使用的音色 ID
- `rate`: 语速（如 `+50%`）
- `tts_volume`: TTS 播放音量
- `preset_audio_volume`: 预设音频播放音量
- `presets_text`: 文本预设列表
- `audio_hotkeys`: 预设音频 → 快捷键映射
- `text_hotkeys`: 文本预设 → 快捷键映射
- `sys_hotkeys`: 系统级功能快捷键映射（见下）
- `auto_clear_history`: 启动时是否自动清理历史记录

历史记录文件为 `%APPDATA%\Type2Speech3\conf\history.json`，记录文本、生成音频路径、语速、引擎、音色等信息。

## 全局快捷键（Windows）

项目使用 Windows API 全局监听快捷键（`utils/hotkey_manager.py`）。默认配置通常位于用户配置文件的 `sys_hotkeys` 中，例如：

- `sys_toggle_window`: 显示/隐藏窗口
- `sys_stop_play`: 停止播放
- `sys_toggle_mic`: 切换“开麦/说话”状态（具体行为以 UI 为准）
- `sys_repeat_play`: 重复播放上一次内容

另外还有：

- `audio_hotkeys`: 触发播放某个预设音频
- `text_hotkeys`: 触发朗读某条预设文本

快捷键字符串格式示例：`ctrl+num1`、`alt+num2`、`ctrl+enter`、`pagedown` 等。

## TTS 引擎说明

- **PyTTSX3（本地）**：`core/engines/pyttsx3_engine.py`
  - 优点：离线可用
  - 注意：音色取决于系统已安装的语音/引擎能力
- **EdgeTTS（在线）**：`core/engines/edge_tts_engine.py`
  - 优点：音质更好、音色更丰富（可动态拉取音色列表）
  - 注意：需要网络
- **OnlineAPI（骨架）**：`core/engines/api_engine.py`
  - 当前为占位实现，运行时会抛出 `NotImplementedError`，用于你自行接入第三方 API

## 打包（可选）

项目包含 `main.spec`，可用 PyInstaller 打包为 Windows 可执行文件。

安装 PyInstaller：

```bash
python -m pip install pyinstaller
```

在根目录执行（示例）：

```bash
pyinstaller main.spec
```

打包结果通常会输出到 `dist/` 目录中（具体以 PyInstaller 输出为准）。用户数据在 `%APPDATA%\Type2Speech3`，重新打包不会清除配置。

## 常见问题排查

- **打开即报错/缺少模块**：先确认依赖已安装（尤其是 `PyQt5`、`qdarktheme`、`edge-tts`、`pyttsx3`、`pyaudio`）
- **没有声音/设备选择异常**：检查系统输出设备与配置文件中的 `last_device_name` 是否与当前设备匹配
- **全局快捷键无效**：
  - 可能被其它软件占用（尤其是 `ctrl+num*` 等）
  - 以管理员权限运行可能更稳定（视系统策略而定）
- **EdgeTTS 报 403 / `Invalid response status`**：通常是 edge-tts 版本落后于微软服务端校验，升级到最新版即可：
  ```bash
  python -m pip install -U edge-tts
  ```
- **EdgeTTS 音色列表加载失败**：检查网络环境；失败时会回退到默认音色

