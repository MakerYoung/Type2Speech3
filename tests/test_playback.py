import unittest
from unittest.mock import Mock

from app.playback import PlaybackController


class PlaybackControllerTests(unittest.TestCase):
    def test_stop_clears_busy_immediately(self):
        controller = PlaybackController()
        worker = Mock()
        controller._current_id = 1
        controller._worker = worker
        controller._busy = True

        busy = []
        controller.busy_changed.connect(busy.append)

        controller.stop()

        worker.stop.assert_called_once()
        self.assertFalse(controller.is_busy())
        self.assertEqual(busy, [False])

        # 旧任务迟到的完成信号必须被丢弃
        controller._on_finished(1, {"text": "x", "path": "p"}, "x", "p")
        self.assertEqual(busy, [False])
        self.assertFalse(controller.is_busy())

    def test_finished_emits_history_record(self):
        controller = PlaybackController()
        controller._current_id = 2
        controller._busy = True

        records = []
        controller.converted.connect(records.append)

        controller._on_finished(
            2,
            {"text": "你好", "path": "a.mp3", "rate": "+10%",
             "engine": "EdgeTTS", "voice_id": "v"},
            "你好",
            "a.mp3",
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].text, "你好")
        self.assertEqual(records[0].engine, "EdgeTTS")
        self.assertFalse(controller.is_busy())

    def test_error_for_stale_task_is_ignored(self):
        controller = PlaybackController()
        controller._current_id = 3
        controller._busy = True

        errors = []
        controller.error.connect(errors.append)
        controller._on_error(99, "旧错误")
        self.assertEqual(errors, [])
        self.assertTrue(controller.is_busy())

        controller._on_error(3, "当前错误")
        self.assertEqual(errors, ["当前错误"])
        self.assertFalse(controller.is_busy())


if __name__ == "__main__":
    unittest.main()
