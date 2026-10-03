from __future__ import annotations
from pathlib import Path
import queue
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import webbrowser
from .media import youtube_url
from .pipeline import Pipeline
from .settings import Settings, get_keys, save_keys
from .state import Job, TaskError, app_root


class Application:
    def __init__(self, root):
        self.root, self.running = root, False
        self.stop, self.events = threading.Event(), queue.Queue()
        self.pending, self.last_url = {}, ""
        root.title("영어듣기 · 영상에서 Notion까지")
        root.geometry("820x650")
        root.minsize(720, 600)
        body = ttk.Frame(root, padding=24)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="영어 영상 → 한국어 번역 → Notion", font=("맑은 고딕", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text="large-v3-turbo · NVIDIA CUDA 전용 · 영어 원문 보존").grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 22))
        self.file, self.url = tk.StringVar(), tk.StringVar()
        self.kind = tk.StringVar(value="file")
        self.file_radio = ttk.Radiobutton(body, text="영상 파일", variable=self.kind, value="file")
        self.file_radio.grid(row=2, column=0, sticky="w")
        self.file_entry = ttk.Entry(body, textvariable=self.file)
        self.file_entry.grid(row=2, column=1, sticky="ew", padx=8)
        self.browse = ttk.Button(body, text="선택", command=self.choose_file)
        self.browse.grid(row=2, column=2)
        self.url_radio = ttk.Radiobutton(body, text="YouTube URL", variable=self.kind, value="youtube")
        self.url_radio.grid(row=3, column=0, sticky="w", pady=12)
        self.url_entry = ttk.Entry(body, textvariable=self.url)
        self.url_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        ttk.Separator(body).grid(row=4, column=0, columnspan=3, sticky="ew", pady=15)
        ttk.Label(body, text="작업 선택").grid(row=5, column=0, sticky="w")
        self.selection = ttk.Combobox(body, state="readonly")
        self.selection.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        ttk.Label(body, text="실패·중단된 작업을 선택하면 완료된 전사와 번역을 재사용합니다.").grid(row=6, column=0, columnspan=3, sticky="w", pady=8)
        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 18))
        self.start = ttk.Button(buttons, text="전사 및 저장 시작 / 재시도", command=self.begin)
        self.start.pack(side="left")
        self.cancel = ttk.Button(buttons, text="중단", command=self.cancel_work, state="disabled")
        self.cancel.pack(side="left", padx=8)
        self.settings_button = ttk.Button(buttons, text="설정", command=self.settings)
        self.settings_button.pack(side="left")
        self.status = tk.StringVar(value="최초 실행이라면 설정에서 OpenAI·Notion 인증정보를 입력하세요.")
        ttk.Label(body, textvariable=self.status, wraplength=730, font=("맑은 고딕", 11)).grid(row=8, column=0, columnspan=3, sticky="w", pady=12)
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew")
        ttk.Label(body, text="GPU 사용 불가 시 중단합니다. CPU로 자동 전환하지 않습니다.\n최종 결과는 Notion에만 보관하며, 성공한 작업의 임시 파일은 정리합니다.", wraplength=730).grid(row=10, column=0, columnspan=3, sticky="w", pady=18)
        recovery = ttk.Frame(body)
        recovery.grid(row=11, column=0, columnspan=3, sticky="w")
        self.attach = ttk.Button(recovery, text="Notion 페이지 연결", command=lambda: self.begin(attach=True))
        self.attach.pack(side="left")
        self.delete = ttk.Button(recovery, text="선택한 임시 작업 삭제", command=self.delete_job)
        self.delete.pack(side="left", padx=8)
        self.open = ttk.Button(recovery, text="완료 페이지 열기", command=self.open_page, state="disabled")
        self.open.pack(side="left")
        self.refresh()
        root.after(150, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def refresh(self):
        self.pending = {}
        jobs = app_root() / "jobs"
        if jobs.exists():
            for directory in sorted(jobs.iterdir()):
                if not directory.is_dir():
                    continue
                try:
                    job = Job.load(directory)
                    self.pending[f"{job.id[:8]} · {job.title or job.source} · {job.stage}"] = directory
                except (OSError, ValueError, TypeError, KeyError):
                    self.status.set("일부 복구 파일을 읽지 못했습니다. 임시 파일은 삭제하지 않았습니다.")
        self.selection["values"] = ["새 작업", *self.pending]
        self.selection.set("새 작업")

    def choose_file(self):
        value = filedialog.askopenfilename(filetypes=[("영상", "*.mp4 *.mkv *.mov *.webm"), ("모든 파일", "*.*")])
        if value:
            self.file.set(value)
            self.kind.set("file")

    def settings(self):
        try:
            settings = Settings.load()
            api, token = get_keys()
        except Exception as exc:
            messagebox.showerror("설정", str(exc))
            return
        window = tk.Toplevel(self.root)
        window.title("API와 Notion 설정")
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill="both", expand=True)
        entries = []
        for row, (label, value, secret) in enumerate([
            ("OpenAI API Key", api, True), ("GPT 모델명", settings.model, False),
            ("Notion Integration Token", token, True), ("영어듣기 Page ID / URL", settings.parent_id, False),
        ]):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=8)
            entry = ttk.Entry(frame, width=48, show="*" if secret else "")
            entry.insert(0, value)
            entry.grid(row=row, column=1, padx=12)
            entries.append(entry)
        ttk.Label(frame, text="키는 Windows 자격 증명 관리자에 저장됩니다.\nNotion 영어듣기 페이지의 Connections에 해당 Integration을 연결하세요.\n번역 API 비용은 사용자의 OpenAI 계정에 청구됩니다.", wraplength=610).grid(row=4, column=0, columnspan=2, sticky="w", pady=12)

        def save():
            try:
                new = Settings(model=entries[1].get(), parent_id=entries[3].get())
                new.save()
                save_keys(entries[0].get(), entries[2].get())
                window.destroy()
                self.status.set("설정을 저장했습니다. 작업 시작 시 Notion 접근 권한을 확인합니다.")
            except Exception as exc:
                messagebox.showerror("설정 저장 실패", str(exc), parent=window)

        ttk.Button(frame, text="저장", command=save).grid(row=5, column=1, sticky="e")

    def set_running(self, value):
        self.running = value
        for widget in (self.start, self.settings_button, self.browse, self.file_entry,
                       self.url_entry, self.file_radio, self.url_radio, self.attach, self.delete):
            widget.configure(state="disabled" if value else "normal")
        self.selection.configure(state="disabled" if value else "readonly")
        self.cancel.configure(state="normal" if value else "disabled")
        self.progress.start(15) if value else self.progress.stop()

    def begin(self, attach=False):
        if self.running:
            return
        try:
            settings = Settings.load()
            api, token = get_keys()
            if not api or not token or not settings.parent_id:
                raise TaskError("settings", "먼저 설정에서 두 API 인증정보와 Notion Page ID를 입력하세요.")
            directory = self.pending.get(self.selection.get())
            if directory:
                job = Job.load(directory)
                job.translation_model = settings.model
            else:
                if attach:
                    raise TaskError("settings", "먼저 복구할 작업을 선택하세요.")
                source = self.file.get().strip() if self.kind.get() == "file" else youtube_url(self.url.get())
                if self.kind.get() == "file" and not Path(source).is_file():
                    raise TaskError("media", "영상 파일을 선택하세요.")
                job = Job.new(self.kind.get(), source, settings.parent_id, settings.model)
                directory = app_root() / "jobs" / job.id
            identifier = None
            if attach:
                identifier = simpledialog.askstring("Notion 페이지 복구", "이 영상 제목으로 영어듣기 아래에 생성된 페이지 URL을 입력하세요.\n생성되지 않았다면 Notion에서 같은 제목의 빈 하위 페이지를 만든 후 연결할 수 있습니다.", parent=self.root)
                if not identifier:
                    return
            job.save(directory)
        except Exception as exc:
            messagebox.showerror("시작할 수 없음", str(exc))
            return
        self.stop.clear()
        self.set_running(True)
        self.status.set("작업을 준비합니다.")

        def worker():
            pipeline = Pipeline(api, token, lambda text: self.events.put(("status", text)), self.stop)
            try:
                if identifier:
                    pipeline.attach_page(job, directory, identifier)
                url = pipeline.run(job, directory)
                self.events.put(("done", url))
            except TaskError as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:
                self.events.put(("error", f"작업을 완료하지 못했습니다 ({type(exc).__name__}). 복구 데이터를 확인하세요."))

        threading.Thread(target=worker, daemon=True).start()

    def cancel_work(self):
        self.stop.set()
        self.status.set("현재 요청이 끝나면 중단합니다. 복구 데이터는 보존됩니다.")

    def delete_job(self):
        directory = self.pending.get(self.selection.get())
        if directory and messagebox.askyesno("임시 작업 삭제", "이 작업의 임시 오디오·전사·번역을 삭제할까요? 원본 영상과 Notion 페이지는 삭제하지 않습니다."):
            try:
                shutil.rmtree(directory)
                self.refresh()
            except OSError:
                messagebox.showerror("삭제 실패", "임시 작업 파일을 삭제하지 못했습니다.")

    def open_page(self):
        if self.last_url:
            webbrowser.open(self.last_url)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    self.status.set(value)
                else:
                    self.set_running(False)
                    self.refresh()
                    if kind == "done":
                        self.last_url = value
                        self.open.configure(state="normal")
                        self.status.set("완료 · Notion 저장과 전체 내용 검증을 마쳤습니다. 임시 파일을 정리했습니다.")
                        messagebox.showinfo("완료", "Notion에 영어·한국어 전사문을 저장했습니다.")
                    else:
                        self.status.set(value)
                        messagebox.showerror("작업 중단 · 재시도 가능", value)
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    def close(self):
        if self.running:
            self.cancel_work()
            messagebox.showinfo("중단 요청", "현재 처리 단계가 끝날 때까지 기다린 후 창을 닫아 주세요. 복구 데이터를 보존합니다.")
            return
        self.root.destroy()


def main():
    from filelock import FileLock, Timeout
    root = tk.Tk()
    app_root().mkdir(parents=True, exist_ok=True)
    lock = FileLock(app_root() / "application.lock")
    try:
        lock.acquire(timeout=0)
    except Timeout:
        root.withdraw()
        messagebox.showinfo("이미 실행 중", "영어듣기 프로그램이 이미 실행 중입니다.")
        root.destroy()
        return
    try:
        Application(root)
        root.mainloop()
    finally:
        lock.release()
