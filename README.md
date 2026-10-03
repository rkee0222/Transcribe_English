# 영어듣기 — Windows GPU 전사·한국어 번역·Notion 저장

원본 요구사항: [docs/ORIGINAL_REQUIREMENTS.txt](docs/ORIGINAL_REQUIREMENTS.txt) · 설계: [docs/DESIGN.md](docs/DESIGN.md)

영상 파일 또는 YouTube 링크 → 로컬 large-v3-turbo CUDA 전사 → GPT 한국어 번역 → Notion 영어듣기 아래 새 페이지 저장.
이 버전은 초기 CPU/TXT 프로그램을 원본 요구사항에 맞춰 개편한 버전입니다.

## 현재 검증 상태

자동 테스트로 원문 불변·ID 대응·중복 발화·번역 재시도·2분 경계·Notion 제한과 복구·성공 후 정리를 검증합니다. MP4/MKV/MOV/WEBM에서 오디오 추출도 검증합니다.
**RTX 4060 실기기, large-v3-turbo GPU 추론, 실제 OpenAI 번역, 실제 Notion 계정 저장, YouTube 다운로드는 아직 통합 검증하지 않았습니다.** Windows EXE는 Windows 빌드가 성공한 뒤 사용할 수 있습니다. 워크플로 파일을 올린 사실만으로 빌드 성공을 의미하지 않습니다.

Windows EXE 빌드와 창 실행 검사는 [빌드 #3](https://github.com/rkee0222/Transcribe_English/actions/runs/37118067291)에서 성공했습니다. 배포 artifact는 약 1.47GB이며, 실제 GPU·API 연동은 미검증입니다. 상세 결과는 [검증 기록](docs/VALIDATION.md)을 참고하세요.

## Windows EXE 받기

1. 이 저장소의 **Actions → Build Windows EXE**를 엽니다.
2. 최신 실행이 성공했는지 확인합니다. 실행이 없다면 **Run workflow**로 시작할 수 있습니다.
3. 성공한 실행의 **Artifacts → EnglishListening-Windows-x64**를 다운로드합니다. GitHub 로그인이 필요할 수 있습니다.
4. ZIP을 모두 풀고 **EnglishListening.exe**를 실행합니다. `_internal` 폴더를 포함해 압축 안의 파일을 함께 보관하세요.

**Code → Download ZIP은 소스코드이며 EXE 다운로드가 아닙니다.** EXE에는 Python과 필요한 라이브러리가 포함되므로 사용자 PC에 Python/Kiro를 설치할 필요가 없습니다. GPU 라이브러리 때문에 용량이 큽니다. 배포본은 서명되지 않았으며 Windows 실행 검증 전에는 정식 완성 배포로 간주하지 마세요.

## PC와 최초 설정

- Windows 10/11 x64, NVIDIA RTX 4060 8GB, RAM 16GB를 목표로 합니다.
- NVIDIA 드라이버를 최신 상태로 유지하세요. CUDA 12/cuDNN 9 런타임은 Windows 패키지에 포함하도록 구성했습니다.
- GPU가 없거나 DLL·VRAM 문제가 있으면 원인을 표시하고 중단합니다. CPU 자동 대체 기능은 없습니다.
- Whisper 모델은 첫 전사 때 다운로드해 재사용합니다. 최초 모델 다운로드에도 인터넷과 여유 디스크 공간이 필요합니다.
- 설정에서 OpenAI API Key, GPT 모델명, Notion Integration Token, 영어듣기 페이지 URL 또는 Page ID를 입력합니다.
- 키는 Windows Credential Manager에 저장됩니다. 소스코드·작업 checkpoint·일반 설정 JSON에는 기록하지 않습니다.
- OpenAI 모델의 초기 제안은 `gpt-4.1-mini`입니다. 계정 접근 권한 및 Structured Outputs 지원이 있는 GPT 모델로 바꿀 수 있습니다. API 비용은 사용자 계정에 청구됩니다.
- Notion에서 내부 Integration을 만들고 읽기·콘텐츠 삽입 권한을 설정한 뒤, 영어듣기 페이지의 **Connections/연결**에서 연결하세요. 페이지 ID만 입력하는 것으로 권한이 생기지 않습니다.

## 사용

1. **영상 파일** 또는 **YouTube URL**을 선택합니다.
2. **전사 및 저장 시작 / 재시도**를 누릅니다.
3. 준비 → 오디오 추출 → GPU 전사 → GPT 번역 → 전사문 구성 → Notion 업로드 상태를 확인합니다.
4. 완료 후 **완료 페이지 열기**를 누릅니다.

로컬 영상의 Notion 제목은 확장자만 뺀 파일명이며, YouTube는 영상 제목입니다. 최종 본문은 영어 발화 다음에 한국어 번역을 배치하고 2분 단위 구분선을 넣습니다. Whisper segment를 발화 단위로 사용합니다. 문장이 경계를 가로지르면 문장을 자르지 않고 다음 발화 앞에 구분선을 넣습니다. 영어 문자열과 순서는 GPT에서 가져오지 않고 Whisper 결과 그대로 사용합니다.

YouTube는 공개된 개별 영상 기준이며 로그인·지역 제한·진행 중 라이브는 지원하지 않습니다. 영상을 외부 전사 서버에 보내지 않지만, **영어 전사문은 OpenAI에 번역용으로 전달되고 영어·한국어 최종 본문은 Notion에 저장**됩니다.

## 실패·중단·복구

- 완료된 전사와 번역 chunk는 임시 checkpoint로 보존됩니다. 프로그램을 다시 실행해 **작업 선택**에서 이전 작업을 고르고 재시도하세요.
- 재시도 시 새 GPT 모델 설정은 남은 번역에 적용됩니다. 기존 검증된 번역은 보존합니다. 기존 작업의 Notion parent는 처음 선택한 대상으로 유지합니다.
- Notion 페이지 생성 응답이 끊기면 자동으로 같은 페이지를 계속 만들지 않습니다. Notion을 확인하고 **Notion 페이지 연결**에 생성된 페이지 URL을 입력하세요. 페이지가 전혀 생성되지 않았다면 같은 제목의 빈 하위 페이지를 만들어 연결할 수 있습니다.
- 업로드가 중단되면 원격 페이지의 전체 본문을 읽고 일치하는 저장 구간 뒤부터 이어 씁니다. 외부에서 수정된 내용은 임의로 덮어쓰지 않습니다.
- Notion 전체 본문·제목·부모 검증이 성공한 뒤에만 작업 임시 파일을 삭제합니다. 원본 영상과 재사용 모델 캐시는 남깁니다. TXT/SRT 최종 파일을 영구 저장하지 않습니다.
- 실패 작업을 버리고 싶을 때만 **선택한 임시 작업 삭제**를 사용하세요.
- 임시 상태와 모델은 `%LOCALAPPDATA%/EnglishListening`에 보관됩니다. 처리 중 강제 종료하면 마지막 저장된 단계에서 복구합니다. 정상 종료 시에는 중단을 요청하고 현재 요청이 끝나기를 기다리세요.

## 소스 실행 / 직접 EXE 빌드

Python 3.12 또는 3.13 x64에서 `실행.bat`로 소스 실행이 가능합니다. 첫 설치 때 대용량 CUDA 라이브러리도 설치됩니다.
Windows x64에서 EXE를 직접 빌드하려면:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean EnglishListening.spec
```

결과는 `dist/EnglishListening/EnglishListening.exe`입니다. 폴더 전체를 배포하세요. Linux에서는 Windows EXE를 생성하거나 실행 검증하지 않습니다. 미디어 테스트의 입력 생성에는 FFmpeg가 필요하며, 앱 실행 자체는 PyAV를 사용합니다.
