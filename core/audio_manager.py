# core/audio_manager.py
import pyaudio
import logging


class AudioManager:
    """音频设备管理器，负责与底层 pyaudio 交互 (已优化 Windows 兼容性)"""

    @staticmethod
    def _fix_windows_encoding(raw_name: str) -> str:
        """
        【魔法方法】：修复 PyAudio 在 Windows 下读取中文设备名的乱码问题。
        原理：PyAudio 常把 GBK 字节错误解析为 cp1252/latin-1
        """
        try:
            # 尝试把错误解码的字符串重新编码为字节，再用 gbk 正确解码
            return raw_name.encode('cp1252').decode('gbk')
        except Exception:
            # 如果失败（比如已经是正确的 utf-8 或是纯英文），则原样返回
            return raw_name

    @staticmethod
    def get_output_devices() -> list[dict]:
        """
        获取所有可用的音频输出设备。
        返回包含设备名称、底层 API 和 PyAudio 索引的字典列表。
        """
        p = pyaudio.PyAudio()
        devices = []

        try:
            device_count = p.get_device_count()
            for i in range(device_count):
                info = p.get_device_info_by_index(i)

                # 只获取有输出声道的设备
                if info.get('maxOutputChannels', 0) > 0:
                    raw_name = info.get('name', 'Unknown Device')
                    clean_name = AudioManager._fix_windows_encoding(raw_name)

                    # 获取底层音频 API 的名字 (如 MME, Windows WASAPI, Windows DirectSound)
                    # 这能帮用户区分为什么会有多个同名设备 (WASAPI 延迟最低)
                    host_api_info = p.get_host_api_info_by_index(info.get('hostApi', 0))
                    host_api_name = host_api_info.get('name', 'Unknown API')

                    # 组装展示名称，例如："CABLE Input (VB-Audio) [Windows WASAPI]"
                    display_name = f"{clean_name} [{host_api_name}]"

                    devices.append({
                        'name': display_name,
                        'clean_name': clean_name,  # 保留干净的名字用于底层比对
                        'index': info['index'],
                        'api': host_api_name
                    })

        except Exception as e:
            # 异常日志必须带上 exc_info=True，否则排错时连哪行报错都不知道
            logging.error(f"获取音频设备时发生严重错误: {e}", exc_info=True)
        finally:
            p.terminate()

        return devices

    @staticmethod
    def find_device_row_by_name(devices: list[dict], target_name: str) -> int:
        """
        基于智能模糊匹配查找设备行号（用于 UI 下拉框回显）。
        抗截断、抗大小写敏感、抗 Host API 后缀干扰。

        :param devices: get_output_devices() 返回的设备列表
        :param target_name: 上次保存的设备名称 (如 "CABLE Input")
        :return: 匹配到的列表索引 (行号)，未找到则返回 -1
        """
        if not target_name:
            return -1

        target_lower = target_name.lower().strip()

        for row, device in enumerate(devices):
            device_name_lower = device['name'].lower()
            clean_name_lower = device['clean_name'].lower()

            # 策略 1：完全包含 (抗前后缀截断)
            if target_lower in device_name_lower or target_lower in clean_name_lower:
                return row

            # 策略 2：反向包含 (如果保存的名字比当前读取的名字长)
            if clean_name_lower in target_lower:
                return row

        return -1