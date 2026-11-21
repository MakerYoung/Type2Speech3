import unittest
from unittest.mock import patch

from core.workers.tts_worker import TTSWorker


def make_worker(games):
    return TTSWorker(
        rate="",
        text="",
        device_index=0,
        filename="unused.wav",
        tts_engine=None,
        volume=1.0,
        open_game_mic=True,
        speak_key="pagedown",
        game_games=games,
        is_history_play=True,
    )


class GameGuardTests(unittest.TestCase):
    def test_empty_game_list_never_injects(self):
        self.assertFalse(make_worker([])._ensure_game_window())

    @patch("core.workers.tts_worker.WindowManager")
    def test_guard_uses_window_manager(self, manager_cls):
        manager_cls.return_value.focus_game_if_needed.return_value = True
        worker = make_worker(["VALORANT"])

        self.assertTrue(worker._ensure_game_window())
        manager_cls.assert_called_once_with(["VALORANT"])
        manager_cls.return_value.focus_game_if_needed.assert_called_once_with(True)

    @patch("core.workers.tts_worker.WindowManager")
    def test_guard_falls_back_on_error(self, manager_cls):
        manager_cls.return_value.focus_game_if_needed.side_effect = RuntimeError("boom")
        self.assertFalse(make_worker(["VALORANT"])._ensure_game_window())


if __name__ == "__main__":
    unittest.main()
