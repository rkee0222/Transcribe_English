import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx

from transcriber.media import youtube_url, prepare_cuda
from transcriber.notion import Notion, batch_blocks, block_text, build_blocks, paragraphs
from transcriber.pipeline import cleanup_success
from transcriber.state import Job, Segment, TaskError, page_id
from transcriber.translation import Translator, chunks, translate_job, validate_translation

PARENT = "11111111-1111-1111-1111-111111111111"
PAGE = "22222222-2222-2222-2222-222222222222"


class TranslationTests(unittest.TestCase):
    def test_duplicates_and_original_characters_preserved(self):
        rows = [Segment(0, 0, 1, " Yes."), Segment(1, 1, 2, " Yes.")]
        result = validate_translation({"translations": [{"id": 1, "ko": "네."}, {"id": 0, "ko": "네."}]}, rows)
        blocks = build_blocks(rows, result, 2)
        self.assertEqual([block_text(x) for x in blocks], [" Yes.", "네.", "", " Yes.", "네.", ""])

    def test_missing_duplicate_extra_and_empty_rejected(self):
        rows = [Segment(0, 0, 1, "a"), Segment(1, 1, 2, "b")]
        for data in [
            {"translations": [{"id": 0, "ko": "가"}]},
            {"translations": [{"id": 0, "ko": "가"}, {"id": 0, "ko": "나"}]},
            {"translations": [{"id": 0, "ko": "가"}, {"id": 8, "ko": "나"}]},
            {"translations": [{"id": 0, "ko": ""}, {"id": 1, "ko": "나"}]},
            {"translations": [{"id": 0, "ko": "가", "en": "changed"}, {"id": 1, "ko": "나"}]},
        ]:
            with self.subTest(data=data), self.assertRaises(TaskError):
                validate_translation(data, rows)

    def test_long_transcript_resume_keeps_verified_chunks(self):
        job = Job.new("file", "x.mp4", PARENT, "configurable-model")
        job.segments = [Segment(i, i * 10, i * 10 + 1, f" English {i}.") for i in range(500)]
        original = copy.deepcopy(job.segments)

        class Fake:
            calls = 0
            fail = True
            def translate(self, batch, context, check):
                self.calls += 1
                if self.fail and self.calls == 3:
                    raise TaskError("network", "offline")
                return {str(row.id): f"번역 {row.id}" for row in batch}

        fake = Fake()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaises(TaskError):
                translate_job(job, folder, fake, lambda _: None, lambda: None)
            saved = Job.load(folder)
            self.assertEqual(len(saved.translations), 70)
            fake.calls, fake.fail = 0, False
            translate_job(saved, folder, fake, lambda _: None, lambda: None)
            self.assertEqual(fake.calls, len(list(chunks(saved.segments))) - 2)
            self.assertEqual(saved.segments, original)
            self.assertEqual(set(saved.translations), {str(i) for i in range(500)})

    def test_bad_response_is_retried_but_auth_is_not(self):
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            content = '{}' if len(calls) == 1 else '{"translations":[{"id":0,"ko":"안녕"}]}'
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        translator = Translator("test-key", "model-from-settings", client, lambda _: None)
        source = Segment(0, 0, 1, " Hello.")
        self.assertEqual(translator.translate([source], []), {"0": "안녕"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["model"], "model-from-settings")
        self.assertIn('"text": " Hello."', calls[0]["messages"][1]["content"])
        translator.close()
        auth_calls = []
        def denied(request):
            auth_calls.append(1)
            return httpx.Response(401, json={})
        translator = Translator("test", "model", httpx.Client(transport=httpx.MockTransport(denied)), lambda _: None)
        with self.assertRaises(TaskError) as error:
            translator.translate([source], [])
        self.assertEqual(error.exception.code, "openai_auth")
        self.assertEqual(len(auth_calls), 1)
        translator.close()


class FormattingTests(unittest.TestCase):
    def test_two_minute_boundaries_do_not_split_utterances(self):
        rows = [Segment(0, 119, 122, "Crosses boundary."), Segment(1, 125, 126, "Next.")]
        texts = [block_text(x) for x in build_blocks(rows, {"0": "경계", "1": "다음"}, 360)]
        self.assertEqual(texts[:7], ["Crosses boundary.", "경계", "", "────────── 2:00 ──────────", "Next.", "다음", ""])
        self.assertEqual(texts[-2:], ["────────── 4:00 ──────────", "────────── 6:00 ──────────"])

    def test_unicode_and_notion_limits_preserve_all_text(self):
        original = "A😀한" * 50000
        blocks = list(paragraphs(original))
        self.assertEqual("".join(block_text(x) for x in blocks), original)
        for block in blocks:
            self.assertLessEqual(len(block["paragraph"]["rich_text"]), 100)
            for value in block["paragraph"]["rich_text"]:
                self.assertLessEqual(len(value["text"]["content"].encode("utf-16-le")) // 2, 2000)
        pending = blocks * 20
        while pending:
            batch = batch_blocks(pending)
            self.assertTrue(batch)
            self.assertLessEqual(len(batch), 100)
            self.assertLess(len(json.dumps({"children": batch}, ensure_ascii=False).encode()), 500000)
            pending = pending[len(batch):]


class NotionTests(unittest.TestCase):
    def test_lost_append_response_resumes_without_duplication(self):
        stored, writes = [], []
        fail = [True]
        def handler(request):
            if "/pages/" in request.url.path:
                identifier = request.url.path.rsplit("/", 1)[-1]
                data = {"id": identifier, "parent": {"page_id": PARENT}, "properties": {"title": {"title": [{"plain_text": "Exact title"}]}}}
                return httpx.Response(200, json=data)
            if request.method == "PATCH":
                rows = json.loads(request.content)["children"]
                writes.append(len(rows))
                stored.extend(rows)
                if fail[0]:
                    fail[0] = False
                    raise httpx.ReadTimeout("lost response", request=request)
                return httpx.Response(200, json={"results": rows})
            offset = int(request.url.params.get("start_cursor", "0"))
            end = min(offset + 100, len(stored))
            return httpx.Response(200, json={"results": stored[offset:end], "has_more": end < len(stored), "next_cursor": str(end) if end < len(stored) else None})
        notion = Notion("test-token", httpx.Client(transport=httpx.MockTransport(handler)), lambda _: None)
        job = Job.new("file", "input.mp4", PARENT, "model")
        job.title, job.notion_id = "Exact title", PAGE
        rows = [Segment(i, i, i + 1, f" Source {i}") for i in range(200)]
        blocks = build_blocks(rows, {str(i): f"번역 {i}" for i in range(200)}, 200)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaises(TaskError):
                notion.upload(job, folder, blocks, lambda _: None, lambda: None)
            self.assertEqual(len(stored), 100)
            self.assertFalse(job.verified)
            notion.upload(job, folder, blocks, lambda _: None, lambda: None)
            self.assertTrue(job.verified)
            self.assertEqual([block_text(x) for x in stored], [block_text(x) for x in blocks])
            self.assertEqual(sum(writes), len(blocks))
        notion.close()

    def test_ambiguous_page_creation_does_not_create_again(self):
        writes = []
        def handler(request):
            if request.method == "POST":
                writes.append(1)
                raise httpx.ReadTimeout("lost response", request=request)
            return httpx.Response(200, json={"id": PARENT})
        notion = Notion("test", httpx.Client(transport=httpx.MockTransport(handler)), lambda _: None)
        job = Job.new("file", "test.mp4", PARENT, "model")
        job.title = "test"
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for _ in range(2):
                with self.assertRaises(TaskError) as error:
                    notion.upload(job, folder, [], lambda _: None, lambda: None)
                self.assertEqual(error.exception.code, "notion_creation_uncertain")
            self.assertTrue(Job.load(folder).creation_pending)
        self.assertEqual(len(writes), 1)
        notion.close()


class SafetyTests(unittest.TestCase):
    def test_cleanup_only_after_remote_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Job.new("file", "original.mp4", PARENT, "model")
            folder = Path(tmp) / "job"
            folder.mkdir()
            (folder / "audio.wav").write_bytes(b"audio")
            with self.assertRaises(TaskError):
                cleanup_success(job, folder)
            self.assertTrue(folder.exists())
            job.verified = True
            cleanup_success(job, folder)
            self.assertFalse(folder.exists())

    def test_no_gpu_is_explicit_error(self):
        with patch("ctranslate2.get_cuda_device_count", return_value=0):
            with self.assertRaises(TaskError) as error:
                prepare_cuda()
        self.assertEqual(error.exception.code, "cuda")
        self.assertIn("CPU로 전환하지", str(error.exception))

    def test_url_validation(self):
        self.assertEqual(youtube_url("https://youtu.be/BaW_jenozKc?list=abc"), "https://www.youtube.com/watch?v=BaW_jenozKc")
        self.assertEqual(page_id("https://www.notion.so/title-" + PARENT.replace("-", "")), PARENT)
        for url in ("https://youtube.com.evil.test/watch?v=BaW_jenozKc", "file:///etc/passwd", "https://youtube.com/playlist?list=x"):
            with self.assertRaises(ValueError):
                youtube_url(url)


if __name__ == "__main__":
    unittest.main()
