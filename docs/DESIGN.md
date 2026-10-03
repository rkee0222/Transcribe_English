# 원본 요구사항 기준 설계

## 범위와 실행 환경

Windows 10/11 x64 데스크톱 앱이다. 서버와 Kiro가 필요 없다. 사용자의 RTX 4060 8GB에서 faster-whisper large-v3-turbo를 CUDA / float16으로 실행한다. CUDA가 없거나 메모리가 부족하면 명시적으로 실패하고 CPU로 자동 전환하지 않는다. 클라우드 개발 머신은 GPU 실기기 검증을 대신할 수 없다.

입력은 영상 파일(MP4/MKV/MOV/WEBM 등) 또는 개별 YouTube URL이다. Whisper 모델 최초 다운로드, YouTube 다운로드, OpenAI 번역, Notion 업로드에 인터넷이 필요하다. 최종 전사문의 영구 저장소는 Notion 하나이며 TXT/SRT 내보내기는 기본 워크플로에서 제거한다.

## 기술

- tkinter/ttk: Windows GUI. 작업은 worker thread, UI 갱신은 queue로 전달한다.
- PyAV: 영상에서 16 kHz mono WAV를 스트리밍 추출하여 긴 영상의 전체 오디오를 RAM에 중복 적재하지 않는다.
- yt-dlp + Deno + yt-dlp-ejs: YouTube 오디오 다운로드. 쿠키·로그인은 자동 수집하지 않는다.
- faster-whisper / CTranslate2: large-v3-turbo, CUDA float16, beam_size 5, batch 추론 없이 메모리 사용을 제한한다.
- httpx: OpenAI 및 Notion REST API. 번역 모델은 설정값이며 초기 제안은 gpt-4.1-mini이다. 특정 계정에서의 모델 접근 가능 여부는 실제 설정 후 검증한다.
- Windows Credential Manager(keyring): API 키 저장. JSON 설정에는 모델명과 Notion parent page ID만 저장한다.
- JSON checkpoint: 작업별 임시 디렉터리에 원문·번역·Notion page ID·진행 상태를 원자적으로 기록한다. API 키는 포함하지 않는다.
- PyInstaller Windows onedir: 일반 EXE와 CUDA/cuDNN/Deno DLL을 ZIP으로 배포한다. Python 설치 없이 EXE를 실행한다. NVIDIA 드라이버는 PC에 필요하다.

## 데이터와 흐름

Job: id, input_kind, source, title, stage, duration, segments[], translations{}, translation_model, notion_parent_id, notion_page_id, error_code.

Segment: id(순차 고유 ID), start, end, text. text는 Whisper의 문자열을 그대로 저장하며 이후 단계에서 수정하거나 중복을 제거하지 않는다. 기본 정렬은 Whisper의 반환 순서다.

1. 입력을 확인하고 원본 제목을 확정한다. 로컬 제목은 Path.stem, YouTube 제목은 추출된 메타데이터 그대로다.
2. 오디오를 job/audio.wav로 추출한다. 완료 전에는 .part를 사용한다.
3. GPU와 DLL을 확인하고 영어 전사 결과 전체를 저장한다. 전사가 완료된 checkpoint를 재사용한다.
4. 연속 segment를 개수·문자 수로 제한한 chunk로 묶는다. 인접 원문을 참고 문맥으로 포함하되 번역 대상 ID와 분리한다.
5. GPT에는 id/text를 입력하고 id/ko만 받는다. JSON Schema와 별도 검증으로 누락·중복·다른 ID·빈 번역을 거부한다. 정상 결과만 원자적으로 저장하고 실패 chunk만 재시도한다. 영어는 응답에서 읽지 않는다.
6. 원문과 번역을 원래 ID 순서로 조합한다. 120초 경계를 넘긴 첫 segment 앞에 구분선을 넣는다. 경계를 가로지르는 문장은 자르지 않는다. 말이 없는 구간과 마지막 구간도 duration을 기준으로 구분선을 유지한다.
7. 지정한 parent 바로 아래에 제목 그대로 새 Notion 페이지를 만든다. API 제한에 맞춰 rich text와 block batch를 나눈다.
8. 재시도 시 원격 page의 모든 block을 페이지네이션으로 읽고 예상 본문의 prefix와 비교한 후 미저장 구간을 이어 쓴다. 다른 내용이나 중복이 있으면 덮어쓰지 않고 멈춘다.
9. 전체 원격 본문과 제목·parent를 확인한 뒤에만 작업 임시 디렉터리를 삭제한다. 원본 영상과 공유 모델 캐시는 삭제하지 않는다.

## 실패와 복구

설정과 인증정보는 실행 전 검사한다. 오류는 CUDA/모델/파일/YouTube/OpenAI 인증·할당량·구조/Notion 인증·권한·저장/네트워크로 구분해 표시한다.

일시적인 번역·조회 오류는 제한된 backoff로 재시도한다. 번역 형식 불일치도 chunk 단위 재시도한다. 작업 재개는 완료된 전사 및 검증된 번역을 그대로 재사용한다. 번역 모델을 바꿔도 이미 성공한 번역을 자동 폐기하지 않는다. 기존 job의 Notion 대상은 고정해 잘못된 parent로 이동하지 않는다.

Notion 페이지 생성 응답이 끊기면 자동으로 새 페이지를 반복 생성하지 않는다. 생성 여부 확인 후 페이지 URL/ID를 입력하여 복구할 수 있게 한다. block 추가 실패 후에는 원격 본문을 재조회하여 확인한다. 서버 응답이 불확실한 상황에서는 중복 생성을 막는 쪽을 우선한다.

사용자가 중단하거나 창을 닫으면 checkpoint를 남기고 다음 실행에서 재시도한다. 성공한 작업만 자동 정리하고, 실패한 작업 삭제는 사용자의 명시적 동작으로 제한한다.

## 검증 및 배포

자동 테스트: 원문 불변, 중복 발화 보존, 긴 chunk의 ID 대응, 잘못된 번역 재시도, 2분 경계, Notion 길이·개수 제한, pagination, 중단된 업로드 재개, 성공 후에만 정리, 영상 컨테이너 오디오 추출.

Windows CI: 의존성 설치, 테스트, PyInstaller EXE 패키징, ZIP artifact 업로드. Linux에서 Windows EXE가 실행됐다고 주장하지 않는다. 실제 RTX 4060/large-v3-turbo 및 OpenAI·Notion 계정으로의 통합 검증은 해당 하드웨어와 인증이 있는 Windows PC에서 별도로 실행해야 한다.
