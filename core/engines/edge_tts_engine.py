# edge_tts_engine.py

import asyncio
import edge_tts
import os
from core.engines.tts_engine import TTSEngine
from typing import List, Dict
import logging


# 【重要函数】：确保在 QThreadPool 线程中安全运行 asyncio
def _safe_async_run(coro):
    """
    在 QThreadPool 线程中安全地运行异步协程 (coroutine)。
    总是创建和关闭一个新的事件循环，以避免 asyncio.run() 的清理错误和线程冲突。
    """
    # 1. 强制创建和设置新的事件循环
    if os.name == 'nt':
        # Windows 系统上使用 ProactorEventLoop
        loop = asyncio.ProactorEventLoop()
    else:
        # 非 Windows 系统使用默认事件循环
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)

    result = None

    try:
        # 2. 在循环中运行协程直到完成
        result = loop.run_until_complete(coro)
        return result

    finally:
        # 3. 彻底清理并关闭循环（FIX: 解决 Task.__del__ 错误的关键）

        # 取消所有尚未完成的任务
        for task in asyncio.all_tasks(loop=loop):
            task.cancel()

        # 运行循环直到所有被取消的任务完成
        try:
            # 尝试优雅关闭执行器
            loop.run_until_complete(loop.shutdown_default_executor())
        except Exception:
            pass  # 忽略关闭过程中的任何错误

        # 4. 关闭事件循环并解除绑定
        loop.close()
        asyncio.set_event_loop(None)


class EdgeTTSEngine(TTSEngine):
    """
    使用 edge-tts 库实现高质量的 Edge TTS 转换引擎。
    音色获取和语音合成均通过线程安全的方式运行。
    """

    @property
    def name(self):
        return 'EdgeTTS (在线)'

    def get_supported_voices(self) -> List[Dict[str, str]]:
        """
        动态获取 Edge TTS 音色列表，并过滤中文和美式英文。
        """

        async def _get_voices_async():
            # edge_tts.list_voices() 是一个异步方法
            return await edge_tts.list_voices()

        target_langs = ["zh-CN", "zh-TW"]
        voice_list = []

        try:
            # 使用更安全的异步运行方式
            all_voices = _safe_async_run(_get_voices_async())

            for v in all_voices:
                # FIX: 确保使用字典键访问，并使用 .get() 处理缺失键
                locale = v.get("Locale")
                name = v.get("Name")
                friendly_name = v.get("FriendlyName")  # FriendlyName 经常是 None/空字符串

                if locale and name and (locale in target_langs):

                    # FIX: 添加回退机制。如果 FriendlyName 缺失或为空，使用 Name 替代
                    if friendly_name:
                        base_name = friendly_name
                    else:
                        base_name = name.split('-')[-1]  # 如果友好名为空，截取 Name 的最后部分作为基础名

                    display_name = f"{base_name} ({locale})"

                    voice_list.append({
                        "id": name,  # 例如: zh-CN-XiaoxiaoNeural
                        "name": display_name  # 例如: XiaoxiaoNeural (zh-CN)
                    })

            logging.info(f"EdgeTTS 成功加载 {len(voice_list)} 个音色。")
            return voice_list

        except Exception as e:
            logging.info(f"Edge TTS 动态获取音色失败: {e}")
            # 如果失败，返回一个默认音色
            return [{
                "id": "zh-CN-XiaoxiaoNeural",
                "name": "默认音色 (加载失败)"
            }]


    def generate_speech(self, text: str, output_path: str,rate:str):
        """
        使用 Edge TTS 将文本合成语音并保存。
        """
        voice = self.voice_id if self.voice_id else "zh-CN-XiaoxiaoNeural"

        async def _generate():
            # FIX: 增加 try-except 块来捕获 edge-tts 内部的网络或协议错误
            try:
                logging.info(f'开始生成：text = {text}, voice = {voice},rate = {rate}')
                tts = edge_tts.Communicate(text, voice,rate=rate,proxy=None)
                # 使用内置的 save 方法
                await tts.save(output_path)

            except Exception as e1:
                # 捕获所有其他网络/IO/协议错误
                raise RuntimeError(f"error in edge tts engine: {e1}")

        try:
            # 使用更安全的异步运行方式
            _safe_async_run(_generate())

        except Exception as e:
            # 将错误传递给 TTSWorker，后者将抛出异常并通知主线程
            logging.info(f"Edge TTS 语音合成失败: {e}")
            raise