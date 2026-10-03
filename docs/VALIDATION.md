# 검증 기록

현재 프로그램을 '실사용 통합 검증 완료'로 간주하지 않는다. 아래에서 자동 테스트와 실제 외부 시스템 검증을 구분한다.

## 자동 검증

Linux 개발 환경에서 `python -m unittest discover -s tests -v`: **16개 통과, 실패 0, 건너뜀 0**.

| 항목 | 확인한 범위 |
| --- | --- |
| MP4/MKV/MOV/WEBM | 실제 생성한 각 컨테이너를 PyAV로 읽어 16kHz mono WAV 추출 |
| 손상 영상 | 명확한 오류와 불완전 오디오 파일 정리 |
| 영어 원문·반복 발화 | 공백·문자열·반복·순서 보존 |
| 번역 | 모의 OpenAI API 응답의 ID·개수·빈 값·추가 필드 검사 및 재시도 |
| 긴 영상 | 5,000초 분량 500개 segment에서 완료 chunk 재사용, 누락·순서 검사 |
| 2분 구분선 | 경계를 가로지르는 문장과 마지막 무음 구간 처리 |
| Notion API 제한 | UTF-16 길이, rich_text 개수, 100 block/500KB 요청 제한 |
| Notion 업로드 | 모의 API에서 페이지네이션, 응답 유실 후 이어쓰기, 생성 응답 불확실 시 중복 생성 방지 |
| 복구·정리 | 번역 실패 후 전사 재실행 없이 복구, 원본 파일 보존, Notion 검증 후에만 작업 파일 삭제 |
| GPU 오류 | CUDA 장치가 없으면 명시적 실패; CPU 대체 없음 |

Windows x64 / Python 3.13용 의존성은 바이너리 배포본만으로 해석 가능함을 확인했다. 이는 해당 PC에서의 GPU 작동 검증과 다르다.

## Windows 빌드

GitHub Actions에서 Windows x64 EXE 패키징 및 GUI 창 생성 검사를 수행한다. 코드 커밋 `daac8b3d53c6373766e0f0bb0b8cbfb32b83a8e3`의 [Windows 빌드 #3](https://github.com/rkee0222/Transcribe_English/actions/runs/37118067291)이 **Success**로 완료되었다.

- Windows 의존성 설치, 테스트 명령, PyInstaller 패키징 단계 통과
- EXE 프로세스가 유지되고 예상 제목의 실제 GUI 창이 생성되는 smoke check 통과
- `EnglishListening-Windows-x64` artifact 1개 생성, 표시 용량 1.47GB
- artifact digest: `sha256:808603f58b16f7c4fe18524d51792c008eb554cdf13ce582f8eb1b63ba31a05f`

GPU가 없는 Windows runner의 창 실행 검사는 RTX 4060 추론이나 실제 OpenAI·Notion 연동 검증을 대신하지 않는다.

## 실제 PC에서 남은 통합 검증

1. RTX 4060 PC에서 최신 배포 ZIP 전체를 풀고 `EnglishListening.exe`를 실행한다.
2. 설정에 OpenAI Key, 사용 가능한 GPT 모델, Notion Token, 영어듣기 parent page ID를 저장한다. 키를 이슈·로그·대화에 붙여넣지 않는다.
3. Notion 영어듣기 페이지에 Integration을 연결한 뒤 3분 이상 MP4로 전체 과정을 확인한다. 제목은 확장자를 제거한 원래 이름이어야 한다.
4. 모델이 large-v3-turbo이고 CUDA float16 추론이 성공하는지 확인한다. CPU 자동 대체는 구현하지 않았으므로 GPU 실패 시 작업이 멈춰야 한다. NVIDIA 드라이버의 `nvidia-smi`로 장치 이름과 실행 중 GPU 사용도 확인할 수 있다.
5. 실제 GPT 결과의 한국어 품질, 반복 발화 보존, 원문 1:1 대응, 2:00 구분선을 확인한다.
6. Notion 페이지의 첫 부분과 마지막 부분까지 저장되었는지 확인한다. 성공한 job 폴더는 `%LOCALAPPDATA%/EnglishListening/jobs`에서 삭제되어야 한다.
7. MKV/MOV/WEBM 및 공개 YouTube 영상을 각각 처리한다. YouTube 페이지 제목은 영상 제목이어야 한다.
8. 번역·업로드 중 인터넷 연결 실패 후 작업을 재선택하여 이미 처리한 전사·번역을 재사용하는지 확인한다.
9. 작은 영상의 검증 후 1시간 이상 영상으로 전체 저장을 확인한다. 실제 번역 테스트는 사용자 OpenAI 계정의 API 사용량이 발생한다.

이 목록은 앞으로 수행할 검증이며, 이미 실행했다는 뜻이 아니다. 현재 개발 환경에는 RTX 4060과 사용자 OpenAI·Notion 인증정보가 없다.
