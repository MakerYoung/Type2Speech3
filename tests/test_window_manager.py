import unittest

from utils.window_manager import is_non_game_process, match_game


class GameMatchTests(unittest.TestCase):
    def test_title_match(self):
        self.assertEqual(
            match_game(["Counter-Strike 2"], "Counter-Strike 2", ""),
            "Counter-Strike 2",
        )

    def test_first_keyword_wins(self):
        games = ["Counter-Strike 2", "Counter-Strike"]
        self.assertEqual(match_game(games, "Counter-Strike 2", ""), "Counter-Strike 2")

    def test_exe_alias(self):
        self.assertEqual(match_game(["Counter-Strike 2"], "任意标题", "cs2.exe"),
                         "Counter-Strike 2")

    def test_exe_compact_name(self):
        self.assertEqual(
            match_game(["VALORANT"], "", "VALORANT-Win64-Shipping.exe"),
            "VALORANT",
        )

    def test_exe_alias_with_path(self):
        self.assertEqual(
            match_game(["Counter-Strike 2"], "", r"C:\Games\CS2\cs2.exe"),
            "Counter-Strike 2",
        )

    def test_short_alias_requires_exact_match(self):
        # Call of Duty 的别名 cod 不能误命中 Code.exe
        self.assertIsNone(match_game(["Call of Duty"], "Visual Studio Code", "Code.exe"))
        self.assertEqual(match_game(["Call of Duty"], "", "cod.exe"), "Call of Duty")

    def test_chinese_title(self):
        self.assertEqual(match_game(["永劫无间"], "永劫无间 - 游戏", ""), "永劫无间")

    def test_chinese_alias(self):
        self.assertEqual(
            match_game(["暗区突围"], "", "ArenaBreakout-Win64-Shipping.exe"),
            "暗区突围",
        )

    def test_process_aliases(self):
        cases = {
            "PUBG": "TslGame.exe",
            "Apex Legends": "r5apex.exe",
            "League of Legends": "LeagueClientUx.exe",
            "Delta Force": "DeltaForceClient-Win64-Shipping.exe",
        }
        for keyword, exe in cases.items():
            with self.subTest(keyword=keyword):
                self.assertEqual(match_game([keyword], "", exe), keyword)

    def test_no_false_positive(self):
        self.assertIsNone(match_game(["VALORANT"], "记事本", "notepad.exe"))
        self.assertIsNone(match_game([], "VALORANT", "VALORANT.exe"))

    def test_non_game_process_guard(self):
        self.assertTrue(is_non_game_process("chrome.exe"))
        self.assertTrue(is_non_game_process(r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
        self.assertFalse(is_non_game_process("cs2.exe"))
        self.assertFalse(is_non_game_process(""))


if __name__ == "__main__":
    unittest.main()
