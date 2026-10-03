# English Transcriber — Windows용 영어 음성 전사

오디오·동영상 파일 또는 YouTube 영상 링크의 영어 음성을 PC에서 전사하고 TXT와 SRT 자막으로 저장합니다.
이 배포본은 Python 프로그램입니다. 독립 실행형 EXE는 아니며 Python 설치가 필요합니다.

## 처음 실행하기

1. Windows 10/11 **64비트** PC에서 [Python 공식 다운로드](https://www.python.org/downloads/windows/)를 열어 **Python 3.12 또는 3.13의 Windows installer (64-bit)**를 설치하세요. Python 3.13.5 64비트가 이미 설치되어 있다면 그대로 사용하세요. 설치 옵션의 Python Launcher와 Tcl/Tk를 포함하세요.
2. ZIP 파일을 다운로드해 **압축을 모두 풀어 주세요**. 다운로드 폴더 등 본인이 쓸 수 있는 위치를 사용하세요.
3. 압축을 푼 폴더의 **실행.bat**를 더블클릭하세요. 최초 실행 때 필요한 패키지가 설치됩니다.
4. **파일 선택**을 누르거나 **YouTube 링크 → 링크 추가**로 영상을 추가한 뒤 **전사 시작**을 누르세요. 첫 전사 때 선택한 모델을 다운로드합니다.
5. 완료 후 **결과 폴더 열기**에서 `transcript.txt`와 `subtitles.srt`를 확인하세요.

첫 설치·모델 다운로드에는 인터넷이 필요합니다. 동일 모델을 다운로드한 뒤에는 오프라인 전사가 가능합니다. 모델은 사용자 계정의 Hugging Face 캐시에 보관됩니다. API 키가 필요 없고, 이 프로그램은 선택한 오디오를 외부 서버로 업로드하지 않습니다.

## YouTube 링크로 전사하기

1. 영상 페이지에서 링크를 복사하세요. 일반 영상 링크, 공유용 `youtu.be` 링크, Shorts 링크를 지원합니다.
2. 프로그램의 **YouTube 링크** 칸에 붙여 넣고 **링크 추가**를 누르세요. 여러 링크를 순서대로 추가할 수 있습니다.
3. **전사 시작**을 누르면 음성을 내려받아 PC에서 전사합니다. 기존 YouTube 자막을 복사하는 방식이 아닙니다.
4. 저장 위치를 지정하지 않으면 사용자 폴더의 `Transcripts`에 저장합니다. 결과 폴더에는 TXT, SRT, 원본 제목·링크를 담은 `source.txt`가 들어갑니다.

인터넷에 공개된 개별 영상 기준입니다. 진행 중인 라이브 방송, 비공개·로그인 필요·지역 제한 영상은 지원하지 않습니다. 재생목록이 붙은 영상 링크는 해당 영상 하나만 처리합니다. 링크의 시작 시간과 관계없이 전체 영상을 전사합니다. 음성은 임시 폴더에 다운로드되고 처리가 끝나면 삭제됩니다.

YouTube가 다운로드를 차단하거나 사이트 구조가 바뀌면 실패할 수 있습니다. 쿠키나 로그인 정보는 요구하지 않습니다. 오류가 생기면 창에 표시된 내용을 확인하세요.

YouTube용 패키지와 JavaScript 실행 도구(Deno)는 처음 실행할 때 자동으로 설치됩니다. 별도의 Node.js 설치는 필요하지 않습니다. 이전 버전 폴더에 덮어써도 새 의존성을 설치하지만, 새 폴더에 압축을 푸는 방법을 권장합니다.

## 사용 방법

- MP3, WAV, M4A, FLAC, MP4 등 여러 파일을 선택할 수 있습니다.
- 기본 모델 `tiny.en`은 가볍고 빠릅니다. `base.en`, `small.en`은 더 많은 메모리와 시간이 필요합니다. 영어 전용이며 한국어 전사·번역은 지원하지 않습니다.
- 저장 위치를 비우면 각 원본 파일 옆에 `파일명_transcript` 폴더를 만듭니다. 같은 이름이 있으면 `_2`, `_3`을 붙여 기존 결과를 보존합니다.
- TXT/SRT는 Windows에서 열기 쉬운 UTF-8 형식입니다. 자동 전사에는 오류가 있을 수 있으니 내용을 검토하세요.
- CPU 모드로 작동하며 GPU와 별도의 FFmpeg 설치는 필요하지 않습니다. 긴 녹음은 처리 시간이 오래 걸릴 수 있습니다.

## 문제가 생기면

- `Please install Python 3.12 or 3.13`이 나오면 Python 3.12 또는 3.13 **64비트**, Tcl/Tk 설치 여부를 확인하세요. 실행 파일은 Python Launcher를 우선 사용하고, 없으면 PATH의 python을 확인합니다.
- 모델 다운로드가 실패하면 인터넷 연결과 조직의 다운로드 정책을 확인하세요. 사용하는 주소는 `huggingface.co`, `us.aws.cdn.hf.co`, 경우에 따라 `cas-bridge.xethub.hf.co`입니다.
- `DLL load failed` 오류가 나면 [Microsoft의 최신 Visual C++ Redistributable 안내](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)를 통해 x64 런타임을 설치하고 다시 실행하세요.
- 패키지 설치를 다시 하려면 프로그램을 종료한 뒤 이 프로그램 폴더의 `.venv`만 삭제하고 `실행.bat`를 실행하세요. 오디오와 전사 결과는 삭제하지 마세요.
- Windows 보안 기능을 끄지 마세요. 다운로드 출처와 파일을 확인한 뒤 사용하세요.

## 명령줄 실행

설치 후 프로그램 폴더에서:

```bat
.venv\Scripts\python.exe app.py "C:\Audio\lecture.mp3" --output "C:\Transcripts" --model tiny.en
```

YouTube 링크:

```bat
.venv\Scripts\python.exe app.py --youtube "https://www.youtube.com/watch?v=영상ID" --output "C:\Transcripts"
```

## 검증 범위

클라우드 Linux 환경에서 실제 영어 음성 전사와 TXT/SRT 저장을 검증했습니다. Windows x64 / Python 3.13용 모든 의존성의 바이너리 패키지를 사용할 수 있음을 확인했습니다. URL 입력 검사와 임시 다운로드 → 실제 전사 → 결과 저장 연결은 로컬 HTTP 테스트로 검증했습니다. 클라우드 네트워크 정책으로 YouTube 접속이 차단돼 실제 YouTube 다운로드는 미검증입니다. Windows용 배치 실행과 화면 조작도 Windows 실기기에서 검증하지 않았습니다.
