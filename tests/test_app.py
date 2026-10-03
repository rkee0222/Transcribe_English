import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import youtube_url, transcribe_youtube


class YouTubeTests(unittest.TestCase):
    def test_video_variants_drop_playlist_and_tracking(self):
        canonical = "https://www.youtube.com/watch?v=BaW_jenozKc"
        for url in (
            canonical + "&list=PL123&index=2",
            "https://youtu.be/BaW_jenozKc?si=tracking&t=30",
            "https://m.youtube.com/watch?v=BaW_jenozKc",
            "youtube.com/shorts/BaW_jenozKc",
            "https://www.youtube.com/live/BaW_jenozKc",
        ):
            with self.subTest(url=url):
                self.assertEqual(youtube_url(url), canonical)

    def test_reject_non_video_and_unrelated_hosts(self):
        for url in (
            "", "https://www.youtube.com/playlist?list=PL123",
            "https://www.youtube.com/@channel", "https://example.com/watch?v=BaW_jenozKc",
            "https://www.youtube.com.evil.test/watch?v=BaW_jenozKc",
            "https://youtube.com@evil.test/watch?v=BaW_jenozKc",
            "file:///etc/passwd", "https://youtube.com/watch?v=bad",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                youtube_url(url)

    def test_download_failure_cleans_temporary_files(self):
        visited = []

        def fail(url, temporary, notify):
            visited.append(temporary)
            (temporary / "partial.audio").write_bytes(b"partial")
            raise RuntimeError("download failed")

        with tempfile.TemporaryDirectory() as output:
            with patch("app.download_youtube", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "download failed"):
                    transcribe_youtube(None, "https://youtu.be/BaW_jenozKc", Path(output))
            self.assertFalse(visited[0].exists())
            self.assertEqual(list(Path(output).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
