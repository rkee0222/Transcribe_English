from dataclasses import asdict, dataclass
import json
import sys

from .state import app_root, atomic_json, page_id, TaskError


@dataclass
class Settings:
    model: str = "gpt-4.1-mini"
    parent_id: str = ""

    @classmethod
    def load(cls):
        path = app_root() / "settings.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(model=data.get("model", "gpt-4.1-mini"), parent_id=data.get("parent_id", ""))
        except (ValueError, OSError) as exc:
            raise TaskError("settings", "설정 파일을 읽지 못했습니다. 설정을 다시 저장하세요.") from exc

    def save(self):
        self.model = self.model.strip()
        self.parent_id = page_id(self.parent_id)
        if not self.model:
            raise TaskError("settings", "번역에 사용할 GPT 모델명을 입력하세요.")
        atomic_json(app_root() / "settings.json", asdict(self))


def credential_store():
    if sys.platform != "win32":
        raise TaskError("settings", "인증정보 저장은 Windows Credential Manager를 사용합니다. Windows에서 설정하세요.")
    from keyring.backends.Windows import WinVaultKeyring
    return WinVaultKeyring()


def get_keys():
    store = credential_store()
    return (store.get_password("EnglishListening", "openai") or "",
            store.get_password("EnglishListening", "notion") or "")


def save_keys(openai: str, notion: str):
    if not openai.strip() or not notion.strip():
        raise TaskError("settings", "OpenAI API Key와 Notion Integration Token을 모두 입력하세요.")
    store = credential_store()
    store.set_password("EnglishListening", "openai", openai.strip())
    store.set_password("EnglishListening", "notion", notion.strip())
