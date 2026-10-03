from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import uuid


class TaskError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Cancelled(TaskError):
    def __init__(self):
        super().__init__("cancelled", "작업을 중단했습니다. 저장된 단계부터 재시도할 수 있습니다.")


def app_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "EnglishListening"


def page_id(value: str) -> str:
    value = value.strip().split("?")[0].rstrip("/")
    match = re.search(r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$", value)
    if not match:
        raise TaskError("settings", "Notion 페이지 URL 또는 32자리 Page ID를 입력하세요.")
    return str(uuid.UUID(match.group(1)))


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


@dataclass(frozen=True)
class Segment:
    id: int
    start: float
    end: float
    text: str


@dataclass
class Job:
    id: str
    kind: str
    source: str
    parent_id: str
    translation_model: str
    title: str = ""
    stage: str = "영상 준비"
    duration: float = 0
    offset: float = 0
    prepared: bool = False
    extracted: bool = False
    transcribed: bool = False
    segments: list[Segment] = field(default_factory=list)
    translations: dict[str, str] = field(default_factory=dict)
    notion_id: str = ""
    creation_pending: bool = False
    verified: bool = False
    error_code: str = ""
    error: str = ""

    @classmethod
    def new(cls, kind, source, parent, model):
        return cls(uuid.uuid4().hex, kind, source, page_id(parent), model)

    def save(self, directory: Path):
        atomic_json(directory / "job.json", asdict(self))

    @classmethod
    def load(cls, directory: Path):
        data = json.loads((directory / "job.json").read_text(encoding="utf-8"))
        data["segments"] = [Segment(**row) for row in data.get("segments", [])]
        return cls(**data)
