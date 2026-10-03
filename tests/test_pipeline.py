from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from transcriber.pipeline import Pipeline
from transcriber.state import Job, Segment, TaskError

PARENT = "11111111-1111-1111-1111-111111111111"


class PipelineTests(unittest.TestCase):
    def test_translation_failure_preserves_data_then_resumes_without_retranscription(self):
        failure = [True]
        captured = []

        class Translation:
            def __init__(self, *args): pass
            def close(self): pass
            def translate(self, batch, context, check):
                if failure[0]:
                    raise TaskError("network", "offline")
                return {str(row.id): "번역" for row in batch}

        class Notion:
            def __init__(self, *args): pass
            def close(self): pass
            def validate_page(self, *args): pass
            def upload(self, job, directory, blocks, notify, check):
                captured.append((job.title, job.parent_id, blocks))
                job.notion_id = "22222222-2222-2222-2222-222222222222"
                job.verified = True
                job.save(directory)

        def extract(source, target, notify, check):
            target.write_bytes(b"audio")
            return 125, 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "My Exact Title.mp4"
            original.write_bytes(b"original")
            folder = root / "jobs" / "example"
            job = Job.new("file", str(original), PARENT, "model")
            pipe = Pipeline("test-api", "test-token", lambda _: None, threading.Event(), root)
            with patch("transcriber.pipeline.Notion", Notion), patch("transcriber.pipeline.Translator", Translation), patch("transcriber.pipeline.media.prepare_cuda"), patch("transcriber.pipeline.media.extract_audio", side_effect=extract) as extraction, patch("transcriber.pipeline.media.whisper_transcribe", return_value=[Segment(0, 119, 122, " Original, repeated repeated.")]) as whisper:
                with self.assertRaises(TaskError):
                    pipe.run(job, folder)
                self.assertTrue((folder / "audio.wav").exists())
                saved = Job.load(folder)
                self.assertTrue(saved.transcribed)
                self.assertEqual(saved.segments[0].text, " Original, repeated repeated.")
                failure[0] = False
                pipe.run(saved, folder)
                self.assertEqual(extraction.call_count, 1)
                self.assertEqual(whisper.call_count, 1)
            self.assertFalse(folder.exists())
            self.assertTrue(original.exists())
            self.assertEqual(captured[0][:2], ("My Exact Title", PARENT))

    def test_cancel_is_recoverable(self):
        from transcriber.state import Cancelled
        event = threading.Event()
        event.set()
        pipeline = Pipeline("", "", lambda _: None, event)
        with self.assertRaises(Cancelled):
            pipeline.check()
