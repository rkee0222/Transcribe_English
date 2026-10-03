from __future__ import annotations

import json
import time
import httpx

from .state import page_id, TaskError


def text_parts(value, limit=1800):
    part, size = [], 0
    for char in value:
        width = 2 if ord(char) > 0xFFFF else 1
        if size + width > limit:
            yield "".join(part)
            part, size = [], 0
        part.append(char)
        size += width
    if part:
        yield "".join(part)


def paragraphs(text):
    parts = list(text_parts(text))
    if not parts:
        yield {"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}
        return
    for index in range(0, len(parts), 16):
        yield {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
            {"type": "text", "text": {"content": value}} for value in parts[index:index + 16]
        ]}}


def build_blocks(segments, translations, duration):
    marker = 120
    blocks = []
    if set(translations) != {str(segment.id) for segment in segments}:
        raise TaskError("translation_structure", "본문 구성 전 원문과 번역의 대응 검증에 실패했습니다.")
    for segment in segments:
        while marker <= segment.start:
            blocks.extend(paragraphs(f"────────── {marker // 60}:{marker % 60:02} ──────────"))
            marker += 120
        blocks.extend(paragraphs(segment.text))
        blocks.extend(paragraphs(translations[str(segment.id)]))
        blocks.extend(paragraphs(""))
    while marker <= duration:
        blocks.extend(paragraphs(f"────────── {marker // 60}:{marker % 60:02} ──────────"))
        marker += 120
    return blocks


def block_text(block):
    if block.get("type") != "paragraph" or block.get("has_children"):
        raise TaskError("notion_conflict", "Notion 본문에 예상하지 않은 블록이 있습니다. 내용을 확인하세요.")
    return "".join(item.get("plain_text", item.get("text", {}).get("content", ""))
                   for item in block["paragraph"].get("rich_text", []))


def batch_blocks(blocks):
    result = []
    size = 32
    for block in blocks:
        block_size = len(json.dumps(block, ensure_ascii=False).encode("utf-8")) + 2
        if result and (len(result) >= 100 or size + block_size > 450_000):
            break
        result.append(block)
        size += block_size
    return result


class Notion:
    def __init__(self, token, client=None, sleep=time.sleep):
        self.client = client or httpx.Client(timeout=httpx.Timeout(60, connect=20))
        self.headers = {"Authorization": "Bearer " + token,
                        "Notion-Version": "2022-06-28"}
        self.sleep = sleep

    def close(self):
        self.client.close()

    def request(self, method, path, body=None):
        # Never blindly retry writes: their response may have been lost after commit.
        for attempt in range(3 if method == "GET" else 1):
            try:
                response = self.client.request(method, "https://api.notion.com/v1/" + path,
                                               headers=self.headers, json=body)
                if response.status_code == 401:
                    raise TaskError("notion_auth", "Notion Integration Token 인증에 실패했습니다.")
                if response.status_code in (403, 404):
                    raise TaskError("notion_access", "Notion 페이지에 접근할 수 없습니다. Page ID와 영어듣기 페이지의 연결(Connections)을 확인하세요.")
                if response.status_code == 429:
                    raise TaskError("notion_rate", "Notion 요청 한도에 도달했습니다. 잠시 후 재시도하세요.")
                if response.status_code >= 500:
                    raise TaskError("notion_temporary", "Notion 요청 한도 또는 서버 오류입니다. 잠시 후 재시도하세요.")
                if not response.is_success:
                    raise TaskError("notion_save", "Notion 요청이 거절되었습니다. 페이지 권한과 데이터 제한을 확인하세요.")
                return response.json()
            except httpx.RequestError:
                error = TaskError("network", "Notion 연결 응답을 받지 못했습니다. 인터넷 연결을 확인하세요.")
            except ValueError:
                error = TaskError("notion_response", "Notion 응답을 해석할 수 없습니다. 저장 여부 확인이 필요합니다.")
            except TaskError as exc:
                if exc.code not in ("notion_temporary", "notion_rate"):
                    raise
                error = exc
            if method != "GET" or attempt == 2:
                raise error
            self.sleep(2 ** attempt)

    def validate_page(self, identifier, job=None):
        page = self.request("GET", "pages/" + page_id(identifier))
        if page.get("archived") or page.get("in_trash"):
            raise TaskError("notion_access", "Notion 페이지가 휴지통에 있습니다.")
        if job:
            parent = page.get("parent", {}).get("page_id", "")
            title = "".join(item.get("plain_text", item.get("text", {}).get("content", ""))
                            for item in page.get("properties", {}).get("title", {}).get("title", []))
            if not parent or page_id(parent) != job.parent_id or title != job.title:
                raise TaskError("notion_conflict", "복구할 Notion 페이지의 부모 또는 제목이 현재 작업과 다릅니다.")
        return page

    def children(self, identifier, check=lambda: None):
        result, cursor = [], None
        while True:
            check()
            path = f"blocks/{identifier}/children?page_size=100"
            if cursor:
                path += "&start_cursor=" + cursor
            data = self.request("GET", path)
            result.extend(data["results"])
            if not data.get("has_more"):
                return result
            cursor = data.get("next_cursor")
            if not cursor:
                raise TaskError("notion_save", "Notion 페이지네이션 응답이 올바르지 않습니다.")

    def upload(self, job, directory, blocks, notify, check):
        self.validate_page(job.parent_id)
        if not job.notion_id:
            if job.creation_pending:
                raise TaskError("notion_creation_uncertain", "페이지 생성 응답을 확인하지 못했습니다. Notion에서 생성 여부를 확인하고 'Notion 페이지 연결'로 해당 페이지 URL을 입력하세요. 새 페이지를 자동으로 중복 생성하지 않습니다.")
            job.creation_pending = True
            job.save(directory)
            try:
                page = self.request("POST", "pages", {
                    "parent": {"type": "page_id", "page_id": job.parent_id},
                    "properties": {"title": {"type": "title", "title": [
                        {"type": "text", "text": {"content": part}} for part in text_parts(job.title)
                    ]}},
                })
                job.notion_id = page_id(page["id"])
            except TaskError as exc:
                if exc.code in ("notion_auth", "notion_access", "notion_save", "notion_rate"):
                    job.creation_pending = False
                    job.save(directory)
                    raise
                raise TaskError("notion_creation_uncertain", "Notion 페이지 생성 결과가 불확실합니다. Notion을 확인한 뒤 'Notion 페이지 연결'로 복구하세요.") from exc
            job.creation_pending = False
            job.save(directory)
        self.validate_page(job.notion_id, job)
        expected = [block_text(block) for block in blocks]
        current = [block_text(block) for block in self.children(job.notion_id, check)]
        if current != expected[:len(current)]:
            raise TaskError("notion_conflict", "Notion의 기존 본문이 작업 내용과 다릅니다. 임의로 덮어쓰지 않았습니다.")
        position = len(current)
        while position < len(blocks):
            check()
            batch = batch_blocks(blocks[position:])
            self.request("PATCH", f"blocks/{job.notion_id}/children", {"children": batch})
            position += len(batch)
            notify(f"Notion 업로드: {position}/{len(blocks)} 블록")
            self.sleep(0.35)
        check()
        final = [block_text(block) for block in self.children(job.notion_id, check)]
        self.validate_page(job.notion_id, job)
        if final != expected:
            raise TaskError("notion_verify", "Notion 전체 본문 검증에 실패했습니다. 임시 데이터를 유지했습니다.")
        job.verified = True
        job.save(directory)
