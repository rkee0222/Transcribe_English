from __future__ import annotations

from pathlib import Path
import shutil

from . import media
from .notion import Notion, build_blocks
from .state import Cancelled, Job, TaskError, app_root, atomic_json, page_id
from .translation import Translator, translate_job


def cleanup_success(job, directory):
    if not job.verified:
        raise TaskError("cleanup", "Notion 검증 전에는 임시 데이터를 삭제할 수 없습니다.")
    shutil.rmtree(directory)


class Pipeline:
    def __init__(self, openai_key, notion_token, notify, stop, root=None):
        self.openai_key = openai_key
        self.notion_token = notion_token
        self.notify = notify
        self.stop = stop
        self.root = root or app_root()

    def check(self):
        if self.stop.is_set():
            raise Cancelled()

    def stage(self, job, directory, stage):
        self.check()
        job.stage = stage
        job.error = ""
        job.error_code = ""
        job.save(directory)
        self.notify(stage)

    def attach_page(self, job, directory, identifier):
        notion = Notion(self.notion_token)
        try:
            identifier = page_id(identifier)
            notion.validate_page(identifier, job)
            job.notion_id = identifier
            job.creation_pending = False
            job.save(directory)
        finally:
            notion.close()

    def run(self, job: Job, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        notion = Notion(self.notion_token)
        translator = Translator(self.openai_key, job.translation_model)
        try:
            if job.verified:
                cleanup_success(job, directory)
                return "https://www.notion.so/" + job.notion_id.replace("-", "")
            self.stage(job, directory, "설정 및 Notion 접근 확인")
            notion.validate_page(job.parent_id)
            if not job.transcribed:
                media.prepare_cuda()
            self.stage(job, directory, "영상 준비")
            if not job.prepared:
                if job.kind == "youtube":
                    download = directory / "download"
                    download.mkdir(exist_ok=True)
                    try:
                        source, metadata = media.download_youtube(job.source, download, self.notify, self.check)
                    except TaskError:
                        raise
                    except Exception as exc:
                        self.check()
                        raise TaskError("youtube", "YouTube 음성을 다운로드하지 못했습니다. 공개 영상인지, 로그인·지역 제한이 있는지, 인터넷 연결이 정상인지 확인하세요.") from exc
                    job.title = metadata["title"]
                else:
                    source = Path(job.source)
                    if not source.is_file():
                        raise TaskError("media", "선택한 영상 파일이 존재하지 않습니다.")
                    job.title = source.stem
                atomic_json(directory / "input.json", {"path": str(source)})
                job.prepared = True
                job.save(directory)
            if not job.extracted:
                self.stage(job, directory, "오디오 추출")
                import json
                source = Path(json.loads((directory / "input.json").read_text(encoding="utf-8"))["path"])
                job.duration, job.offset = media.extract_audio(source, directory / "audio.wav", self.notify, self.check)
                job.extracted = True
                job.save(directory)
            if not job.transcribed:
                self.stage(job, directory, "Whisper 전사")
                job.segments = media.whisper_transcribe(directory / "audio.wav", job.offset,
                                                        self.root / "models", self.notify, self.check)
                job.transcribed = True
                job.save(directory)
            self.stage(job, directory, "GPT 번역")
            translate_job(job, directory, translator, self.notify, self.check)
            self.stage(job, directory, "전사문 구성")
            blocks = build_blocks(job.segments, job.translations, job.duration)
            self.stage(job, directory, "Notion 업로드")
            notion.upload(job, directory, blocks, self.notify, self.check)
            url = "https://www.notion.so/" + job.notion_id.replace("-", "")
            cleanup_success(job, directory)
            self.notify("완료: Notion 전체 내용 확인 및 임시 파일 정리 완료")
            return url
        except TaskError as exc:
            job.error_code, job.error = exc.code, str(exc)
            job.save(directory)
            raise
        except Exception as exc:
            job.error_code = "unexpected"
            job.error = f"{job.stage} 단계에서 처리하지 못했습니다 ({type(exc).__name__}). 복구 데이터를 유지했습니다."
            job.save(directory)
            raise TaskError(job.error_code, job.error) from exc
        finally:
            translator.close()
            notion.close()
