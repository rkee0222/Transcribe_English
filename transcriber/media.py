from __future__ import annotations
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit
from .state import Segment, TaskError

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


def download_youtube(url: str, temporary: Path, notify=print, check=lambda: None) -> tuple[Path, dict]:
    import yt_dlp
    from deno import find_deno_bin

    url = youtube_url(url)
    last_percent = -1

    def progress(info):
        nonlocal last_percent
        check()
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
        "js_runtimes": {"deno": {"path": str(Path(sys._MEIPASS) / "deno.exe") if getattr(sys, "frozen", False) else find_deno_bin()}},
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


def extract_audio(source: Path, destination: Path, notify, check):
    import av
    temporary = destination.with_suffix(".part")
    try:
        with av.open(str(source)) as container:
            if not container.streams.audio:
                raise TaskError("media", "입력 영상에 오디오 스트림이 없습니다.")
            audio = container.streams.audio[0]
            duration = (container.duration or 0) / av.time_base
            origin = (container.start_time or 0) / av.time_base
            offset = max(0, float((audio.start_time or 0) * audio.time_base) - origin)
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            samples = 0
            last_progress = -1
            with av.open(str(temporary), mode="w", format="wav") as output:
                stream = output.add_stream("pcm_s16le", rate=16000)
                stream.layout = "mono"
                for frame in container.decode(audio=0):
                    check()
                    for converted in resampler.resample(frame):
                        samples += converted.samples
                        converted.pts = None
                        for packet in stream.encode(converted):
                            output.mux(packet)
                    elapsed = int(samples / 16000)
                    if elapsed != last_progress:
                        last_progress = elapsed
                        notify(f"오디오 추출: {elapsed} / {duration:.0f}초")
                for converted in resampler.resample(None):
                    samples += converted.samples
                    converted.pts = None
                    for packet in stream.encode(converted):
                        output.mux(packet)
                for packet in stream.encode(None):
                    output.mux(packet)
            if samples == 0:
                raise TaskError("media", "입력 파일에서 음성을 읽지 못했습니다.")
        temporary.replace(destination)
        return max(duration, samples / 16000 + offset), offset
    except TaskError:
        raise
    except Exception as exc:
        raise TaskError("media", "영상 파일을 읽거나 오디오를 추출하지 못했습니다. 파일 형식과 손상 여부를 확인하세요.") from exc
    finally:
        temporary.unlink(missing_ok=True)


_DLL_HANDLES = []


def prepare_cuda():
    if os.name == "nt":
        roots = [Path(value) for value in sys.path if value]
        if getattr(sys, "frozen", False):
            roots.insert(0, Path(sys._MEIPASS))
        for root in roots:
            for component in ("cublas", "cudnn", "cuda_nvrtc"):
                folder = root / "nvidia" / component / "bin"
                if folder.is_dir():
                    _DLL_HANDLES.append(os.add_dll_directory(str(folder)))
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            raise RuntimeError("No CUDA device")
        if "float16" not in ctranslate2.get_supported_compute_types("cuda", device_index=0):
            raise RuntimeError("No float16 support")
    except Exception as exc:
        raise TaskError("cuda", "CUDA/GPU를 사용할 수 없습니다. RTX 4060의 NVIDIA 드라이버와 CUDA 12/cuDNN 9 DLL을 확인하세요. CPU로 전환하지 않았습니다.") from exc


def whisper_transcribe(audio: Path, offset, model_cache: Path, notify, check):
    prepare_cuda()
    notify("Whisper 전사: CUDA GPU · large-v3-turbo · float16 모델 로딩")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("large-v3-turbo", device="cuda", device_index=0,
                             compute_type="float16", download_root=str(model_cache))
    except Exception as exc:
        raise TaskError("whisper_model", "large-v3-turbo 모델 로딩에 실패했습니다. 인터넷, GPU 메모리, CUDA DLL을 확인하세요. CPU로 전환하지 않았습니다.") from exc
    try:
        rows, info = model.transcribe(str(audio), language="en", beam_size=5, vad_filter=True)
        segments = []
        for index, row in enumerate(rows):
            check()
            segments.append(Segment(index, row.start + offset, row.end + offset, row.text))
            notify(f"Whisper 전사: GPU 사용 · {row.end:.0f}/{info.duration:.0f}초")
        if not segments:
            raise TaskError("whisper_empty", "인식 가능한 영어 음성이 없습니다.")
        return segments
    except TaskError:
        raise
    except Exception as exc:
        raise TaskError("whisper", "GPU 영어 전사에 실패했습니다. VRAM 사용량과 CUDA DLL을 확인하세요. 완료된 이전 단계는 유지됩니다.") from exc
    finally:
        del model
