# core/engines/edge_tts_engine.py
"""Microsoft Edge 在线 TTS 引擎。"""

import asyncio
import logging

import edge_tts

from core.engines.tts_engine import TTSEngine, TTSEngineError


def _run_async(coro):
    """在 QThreadPool 线程中安全运行协程，结束后彻底关闭事件循环。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        for task in asyncio.all_tasks(loop):
            task.cancel()
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        try:
            loop.run_until_complete(loop.shutdown_default_executor())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


class EdgeTTSEngine(TTSEngine):
    """高质量在线引擎，需要网络。"""

    file_suffix = ".mp3"
    supports_rate = True

    TARGET_LOCALES = {"zh-CN", "zh-TW"}
    FALLBACK_VOICE = {"id": "zh-CN-XiaoxiaoNeural", "name": "默认音色 (加载失败)"}

    @property
    def name(self):
        return 'EdgeTTS (在线)'

    def get_supported_voices(self) -> list[dict]:
        async def _list():
            return await edge_tts.list_voices()

        try:
            all_voices = _run_async(_list())
        except Exception as exc:
            logging.error("Edge TTS 获取音色失败: %s", exc)
            return [dict(self.FALLBACK_VOICE)]

        voices = []
        for voice in all_voices:
            locale = voice.get("Locale")
            name = voice.get("Name")
            if not locale or not name or locale not in self.TARGET_LOCALES:
                continue
            friendly = voice.get("FriendlyName")
            base_name = friendly or name.split('-')[-1]
            voices.append({"id": name, "name": f"{base_name} ({locale})"})
        logging.info("EdgeTTS 加载 %d 个音色", len(voices))
        return voices or [dict(self.FALLBACK_VOICE)]

    def generate_speech(self, text: str, output_path: str, rate: str):
        voice = self.voice_id or "zh-CN-XiaoxiaoNeural"

        async def _generate():
            communicate = edge_tts.Communicate(text, voice, rate=rate, proxy=None)
            await communicate.save(output_path)

        try:
            logging.info("EdgeTTS 合成: voice=%s rate=%s", voice, rate)
            _run_async(_generate())
        except Exception as exc:
            # 常见原因：网络/代理问题，或 edge-tts 版本过旧导致 403
            raise TTSEngineError(f"Edge TTS 合成失败: {exc}") from exc
