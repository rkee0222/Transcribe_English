from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

from transcriber.media import extract_audio
from transcriber.state import TaskError


@unittest.skipUnless(shutil.which("ffmpeg"), "Fixture generation requires ffmpeg")
class ContainerTests(unittest.TestCase):
    def test_mp4_mkv_mov_webm_audio_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for extension in ("mp4", "mkv", "mov", "webm"):
                with self.subTest(extension=extension):
                    source = folder / ("input." + extension)
                    subprocess.run([
                        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=32x32:r=5:d=1",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", "-threads", "1",
                        "-c:v", "libvpx-vp9" if extension == "webm" else "libx264",
                        "-c:a", "libopus" if extension == "webm" else "aac", str(source),
                    ], check=True, capture_output=True)
                    output = folder / (extension + ".wav")
                    duration, offset = extract_audio(source, output, lambda _: None, lambda: None)
                    with wave.open(str(output)) as audio:
                        self.assertEqual(audio.getframerate(), 16000)
                        self.assertEqual(audio.getnchannels(), 1)
                        self.assertGreater(audio.getnframes(), 14000)
                    self.assertGreater(duration, 0.9)
                    self.assertGreaterEqual(offset, 0)
                    self.assertTrue(source.exists())

    def test_corrupt_file_has_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "corrupt.mp4"
            source.write_bytes(b"not a video")
            with self.assertRaises(TaskError) as error:
                extract_audio(source, Path(tmp) / "audio.wav", lambda _: None, lambda: None)
            self.assertEqual(error.exception.code, "media")
            self.assertFalse((Path(tmp) / "audio.part").exists())
