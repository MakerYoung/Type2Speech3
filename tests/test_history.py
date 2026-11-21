import json
import tempfile
import unittest
from pathlib import Path

from app.history import HistoryRecord, HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = HistoryStore(self.root / "conf" / "history.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip_uses_legacy_field_name(self):
        record = HistoryRecord(text="你好", path="a.wav", rate="+10%",
                               engine="EdgeTTS", voice_id="voice")
        self.store.add(record)

        raw = json.loads((self.root / "conf" / "history.json").read_text(encoding="utf-8"))
        self.assertEqual(raw[0]["voice_engine"], "EdgeTTS")
        self.assertNotIn("engine", raw[0])

        reloaded = HistoryStore(self.root / "conf" / "history.json")
        reloaded.load()
        self.assertEqual(reloaded.records[0].engine, "EdgeTTS")
        self.assertEqual(reloaded.records[0].text, "你好")

    def test_find(self):
        record = HistoryRecord(text="abc", path="a.wav", rate="+10%",
                               engine="EdgeTTS", voice_id="v")
        self.store.add(record)
        self.assertIs(self.store.find("abc", "+10%", "EdgeTTS", "v"), record)
        self.assertIsNone(self.store.find("abc", "+20%", "EdgeTTS", "v"))

    def test_clear_non_presets_deletes_files(self):
        keep_file = self.root / "keep.wav"
        drop_file = self.root / "drop.wav"
        keep_file.write_bytes(b"1")
        drop_file.write_bytes(b"2")
        self.store.add(HistoryRecord(text="keep", path=str(keep_file)))
        self.store.add(HistoryRecord(text="drop", path=str(drop_file)))

        removed, deleted = self.store.clear_non_presets({"keep"})

        self.assertEqual((removed, deleted), (1, 1))
        self.assertTrue(keep_file.exists())
        self.assertFalse(drop_file.exists())
        self.assertEqual([r.text for r in self.store.records], ["keep"])


if __name__ == "__main__":
    unittest.main()
