"""验证频道目录的稳定身份，避免把失效旧 handle 当成频道身份。"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

class CatalogTests(unittest.TestCase):
    def test_every_curated_channel_has_a_unique_stable_youtube_id(self):
        seeds = json.loads((ROOT / "NewsLiveApp/Resources/channels.json").read_text(encoding="utf8"))
        seen = set()
        for seed in seeds:
            with self.subTest(channel=seed["id"]):
                channel_id = seed.get("youtubeChannelID", "")
                self.assertIsNotNone(re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id), "频道必须使用稳定的 YouTube Channel ID")
                self.assertNotIn(channel_id, seen, "同一 YouTube 频道不能重复收录")
                seen.add(channel_id)

if __name__ == "__main__": unittest.main()
