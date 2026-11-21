import inspect
import unittest

from core.engines.api_engine import OnlineAPIEngine
from core.engines.edge_tts_engine import EdgeTTSEngine
from core.engines.pyttsx3_engine import PyTTSX3Engine
from core.engines.tts_engine import TTSEngine, parse_rate_multiplier


class RateParsingTests(unittest.TestCase):
    def test_percent_and_multiplier(self):
        self.assertAlmostEqual(parse_rate_multiplier("+50%"), 1.5)
        self.assertAlmostEqual(parse_rate_multiplier("-20%"), 0.8)
        self.assertAlmostEqual(parse_rate_multiplier("1.25"), 1.25)
        self.assertAlmostEqual(parse_rate_multiplier(None), 1.0)
        self.assertAlmostEqual(parse_rate_multiplier("bad"), 1.0)
        self.assertAlmostEqual(parse_rate_multiplier("-200%"), 0.1)


class EngineContractTests(unittest.TestCase):
    def test_all_engines_implement_common_signature(self):
        base_params = list(inspect.signature(TTSEngine.generate_speech).parameters)
        for engine in (PyTTSX3Engine, EdgeTTSEngine, OnlineAPIEngine):
            self.assertEqual(list(inspect.signature(engine.generate_speech).parameters), base_params)

    def test_engine_metadata(self):
        self.assertEqual(EdgeTTSEngine.file_suffix, ".mp3")
        self.assertEqual(PyTTSX3Engine.file_suffix, ".wav")
        self.assertTrue(PyTTSX3Engine.supports_rate)
        self.assertTrue(EdgeTTSEngine.supports_rate)
        self.assertFalse(OnlineAPIEngine.supports_rate)

    def test_spawn_isolates_voice(self):
        engine = PyTTSX3Engine("voice-a")
        clone = engine.spawn("voice-b")
        self.assertIsNot(clone, engine)
        self.assertEqual(clone.voice_id, "voice-b")
        self.assertEqual(engine.voice_id, "voice-a")


if __name__ == "__main__":
    unittest.main()
