"""English transcription for Windows; GUI by default, CLI for automation."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

MODELS = ("tiny.en", "base.en", "small.en")


def youtube_url(value: str) -> str:
    """Accept one video, dropping playlist and tracking parameters."""
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    video_id = ""
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        raise ValueError("YouTube 영상 링크를 입력하세요.")
    if host in ("youtu.be", "www.youtu.be") and len(parts) == 1:
        video_id = parts[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in ("shorts", "live", "embed"):
            video_id = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("채널이나 재생목록이 아닌 개별 YouTube 영상 링크를 입력하세요.")
    return "https://www.youtube.com/watch?v=" + video_id


def download_youtube(url: str, temporary: Path, notify=print) -> tuple[Path, dict]:
    import yt_dlp
    from deno import find_deno_bin

    url = youtube_url(url)
    last_percent = -1

    def progress(info):
        nonlocal last_percent
        total = info.get("total_bytes") or info.get("total_bytes_estimate")
        if info.get("status") == "downloading" and total:
            percent = int(info.get("downloaded_bytes", 0) * 100 / total)
            if percent != last_percent:
                last_percent = percent
                notify(f"YouTube 음성 다운로드: {min(percent, 100)}%")
        elif info.get("status") == "finished":
            notify("다운로드 완료. 영어 음성을 전사합니다.")

    def reject_live(info, *, incomplete):
        if info.get("is_live") or info.get("live_status") == "is_upcoming":
            return "진행 중이거나 시작 전인 라이브 방송은 지원하지 않습니다."
        return None

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(temporary / "%(title).80B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "progress_hooks": [progress],
        "match_filter": reject_live,
        "js_runtimes": {"deno": {"path": find_deno_bin()}},
    }
    notify("YouTube 영상 정보를 확인하고 음성을 다운로드합니다.")
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        if not info:
            raise ValueError("다운로드 가능한 영상이 없습니다.")
        downloaded = info.get("requested_downloads") or []
        filename = downloaded[0].get("filepath") if downloaded else None
        audio = Path(filename or downloader.prepare_filename(info))
        if not audio.is_file():
            raise ValueError("음성을 다운로드하지 못했습니다. 공개된 일반 영상인지 확인하세요.")
        return audio, {"title": info.get("title", ""), "url": url}


def transcribe_youtube(model, url: str, output: Path, notify=print) -> Path:
    with tempfile.TemporaryDirectory(prefix="english-transcriber-") as temporary:
        audio, metadata = download_youtube(url, Path(temporary), notify)
        target = transcribe(model, audio, output, notify)
        (target / "source.txt").write_text(
            f"{metadata['title']}\n{metadata['url']}\n", encoding="utf-8-sig")
        return target


def srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def load_model(name: str, notify=print):
    from faster_whisper import WhisperModel
    from huggingface_hub.errors import LocalEntryNotFoundError

    options = dict(device="cpu", compute_type="int8",
                   cpu_threads=max(1, min(4, os.cpu_count() or 1)))
    notify("모델을 준비합니다. 최초 실행 시 인터넷에서 다운로드합니다.")
    try:
        return WhisperModel(name, local_files_only=True, **options)
    except LocalEntryNotFoundError:
        return WhisperModel(name, **options)


def create_result_dir(parent: Path, stem: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for index in range(1, 10000):
        suffix = "" if index == 1 else f"_{index}"
        target = parent / f"{stem}_transcript{suffix}"
        try:
            target.mkdir()
            return target
        except FileExistsError:
            continue
    raise RuntimeError("결과 폴더가 너무 많습니다. 다른 저장 위치를 선택하세요.")


def transcribe(model, source: Path, output: Path, notify=print) -> Path:
    segments, info = model.transcribe(str(source), language="en", beam_size=5,
                                      vad_filter=True)
    # Consume the lazy iterator fully before publishing any result files.
    rows = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            rows.append((segment.start, segment.end, text))
        notify(f"{source.name}: {segment.end:.0f} / {info.duration:.0f}초 처리")
    if not rows:
        raise ValueError("인식 가능한 영어 음성을 찾지 못했습니다.")
    target = create_result_dir(output, source.stem)
    transcript = "\n".join(text for _, _, text in rows) + "\n"
    subtitles = "\n\n".join(
        f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{text}"
        for index, (start, end, text) in enumerate(rows, 1)
    ) + "\n"
    (target / "transcript.txt").write_text(transcript, encoding="utf-8-sig")
    (target / "subtitles.srt").write_text(subtitles, encoding="utf-8-sig")
    return target


def gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("English Transcriber · 영어 음성 전사")
    root.geometry("760x660")
    root.minsize(680, 600)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    body = ttk.Frame(root, padding=22)
    body.grid(sticky="nsew")
    body.columnconfigure(0, weight=1)
    body.rowconfigure(2, weight=1)
    ttk.Label(body, text="영어 음성을 텍스트와 자막으로", font=("맑은 고딕", 18, "bold")).grid(sticky="w")
    ttk.Label(body, text="오디오·동영상 파일 · YouTube 링크  |  PC에서 전사 · API 키 불필요").grid(sticky="w", pady=(6, 16))
    files_box = tk.Listbox(body, height=8, selectmode=tk.EXTENDED)
    files_box.grid(sticky="nsew")
    sources: list[Path | str] = []
    events: queue.Queue = queue.Queue()
    running = False
    last_result: Path | None = None

    def choose_files():
        paths = filedialog.askopenfilenames(title="전사할 오디오 또는 동영상 선택",
            filetypes=[("오디오 및 동영상", "*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.mp4 *.mkv *.webm"), ("모든 파일", "*.*")])
        for item in paths:
            path = Path(item)
            if path not in sources:
                sources.append(path)
                files_box.insert(tk.END, str(path))

    def clear_files():
        sources.clear()
        files_box.delete(0, tk.END)

    buttons = ttk.Frame(body)
    buttons.grid(sticky="w", pady=8)
    add = ttk.Button(buttons, text="파일 선택", command=choose_files)
    add.pack(side="left")
    clear = ttk.Button(buttons, text="목록 비우기", command=clear_files)
    clear.pack(side="left", padx=8)
    links = ttk.Frame(body)
    links.grid(sticky="ew", pady=(4, 8))
    links.columnconfigure(1, weight=1)
    ttk.Label(links, text="YouTube 링크").grid(row=0, column=0, padx=(0, 10))
    url_var = tk.StringVar()
    url_entry = ttk.Entry(links, textvariable=url_var)
    url_entry.grid(row=0, column=1, sticky="ew")

    def add_link():
        try:
            url = youtube_url(url_var.get())
        except ValueError as exc:
            messagebox.showerror("링크 확인", str(exc))
            return False
        if url not in sources:
            sources.append(url)
            files_box.insert(tk.END, url)
        url_var.set("")
        return True

    link_button = ttk.Button(links, text="링크 추가", command=add_link)
    link_button.grid(row=0, column=2, padx=(8, 0))
    settings = ttk.Frame(body)
    settings.grid(sticky="ew", pady=8)
    settings.columnconfigure(1, weight=1)
    ttk.Label(settings, text="모델").grid(row=0, column=0, sticky="w", padx=(0, 12))
    model_choice = ttk.Combobox(settings, values=MODELS, state="readonly", width=16)
    model_choice.set("tiny.en")
    model_choice.grid(row=0, column=1, sticky="w")
    ttk.Label(settings, text="tiny: 빠름 / base·small: 더 크고 느림").grid(row=1, column=1, sticky="w", pady=(4, 10))
    output_var = tk.StringVar()
    ttk.Label(settings, text="저장 위치").grid(row=2, column=0, sticky="w", padx=(0, 12))
    output_entry = ttk.Entry(settings, textvariable=output_var)
    output_entry.grid(row=2, column=1, sticky="ew")

    def choose_output():
        folder = filedialog.askdirectory(title="결과 저장 위치")
        if folder:
            output_var.set(folder)

    browse = ttk.Button(settings, text="찾아보기", command=choose_output)
    browse.grid(row=2, column=2, padx=(8, 0))
    ttk.Label(settings, text="비워 두면 파일은 원본 옆, YouTube는 사용자 폴더의 Transcripts에 저장합니다.", wraplength=510).grid(row=3, column=1, sticky="w", pady=(4, 0))
    status = tk.StringVar(value="파일을 선택하거나 링크를 추가한 뒤 전사 시작을 누르세요.")
    ttk.Label(body, textvariable=status, wraplength=650).grid(sticky="w", pady=(12, 6))
    progress = ttk.Progressbar(body, mode="indeterminate")
    progress.grid(sticky="ew", pady=6)

    def open_result():
        if last_result is not None:
            try:
                os.startfile(str(last_result))
            except OSError as exc:
                messagebox.showerror("폴더 열기 실패", str(exc))

    def set_running(value: bool):
        nonlocal running
        running = value
        for widget in (add, clear, browse, output_entry, start, url_entry, link_button):
            widget.configure(state="disabled" if value else "normal")
        model_choice.configure(state="disabled" if value else "readonly")
        if value:
            progress.start(12)
        else:
            progress.stop()

    def start_work():
        if url_var.get().strip() and not add_link():
            return
        if not sources:
            messagebox.showinfo("전사 대상 선택", "파일을 선택하거나 YouTube 링크를 추가하세요.")
            return
        selected = list(sources)
        destination = Path(output_var.get().strip()) if output_var.get().strip() else None
        model_name = model_choice.get()
        set_running(True)
        status.set("전사를 준비합니다. 긴 파일은 시간이 걸릴 수 있습니다.")

        def worker():
            failures, completed = [], []
            report = lambda text: events.put(("status", text))
            try:
                model = load_model(model_name, report)
                for source in selected:
                    try:
                        if isinstance(source, str):
                            folder = transcribe_youtube(model, source, destination or Path.home() / "Transcripts", report)
                        else:
                            folder = transcribe(model, source, destination or source.parent, report)
                        completed.append(folder)
                    except Exception as exc:
                        label = source.name if isinstance(source, Path) else source
                        failures.append(f"{label}: {exc}")
                events.put(("done", (completed, failures)))
            except Exception as exc:
                events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    actions = ttk.Frame(body)
    actions.grid(sticky="w", pady=(10, 0))
    start = ttk.Button(actions, text="전사 시작", command=start_work)
    start.pack(side="left")
    open_button = ttk.Button(actions, text="결과 폴더 열기", command=open_result, state="disabled")
    open_button.pack(side="left", padx=8)

    def poll():
        nonlocal last_result
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "status":
                    status.set(payload)
                elif kind == "error":
                    set_running(False)
                    status.set("전사를 시작하지 못했습니다.")
                    messagebox.showerror("실행 실패", payload + "\n\n첫 실행이라면 인터넷 연결을 확인하세요.")
                elif kind == "done":
                    set_running(False)
                    completed, failures = payload
                    status.set(f"완료: {len(completed)}개 · 실패: {len(failures)}개")
                    if completed:
                        last_result = completed[-1]
                        open_button.configure(state="normal")
                    if failures:
                        messagebox.showwarning("일부 파일 처리 실패", "\n\n".join(failures))
                    else:
                        messagebox.showinfo("전사 완료", "TXT와 SRT 파일을 저장했습니다.\n결과 폴더 열기를 눌러 확인하세요.")
        except queue.Empty:
            pass
        root.after(150, poll)

    def close():
        if not running or messagebox.askyesno("종료", "전사 중입니다. 중단하고 종료할까요?"):
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(150, poll)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="영어 음성을 TXT/SRT로 전사합니다.")
    parser.add_argument("audio", nargs="?", type=Path)
    parser.add_argument("--youtube", help="개별 YouTube 영상 링크")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="tiny.en", help="tiny.en, base.en, small.en 또는 로컬 모델 폴더")
    args = parser.parse_args()
    if args.audio is not None and args.youtube is not None:
        parser.error("파일과 --youtube 링크 중 하나만 지정하세요.")
    if args.audio is None and args.youtube is None:
        gui()
        return 0
    if args.audio is not None and not args.audio.is_file():
        parser.error(f"파일이 없습니다: {args.audio}")
    try:
        if args.youtube is not None:
            args.youtube = youtube_url(args.youtube)
        model = load_model(args.model)
        if args.youtube is not None:
            result = transcribe_youtube(model, args.youtube, args.output or Path.home() / "Transcripts")
        else:
            result = transcribe(model, args.audio.resolve(), args.output or args.audio.resolve().parent)
        print(f"결과: {result}")
        return 0
    except Exception as exc:
        print(f"전사 실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
