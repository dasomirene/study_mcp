# AI 날씨와 달

OpenAI, WeatherAPI, FastAPI WebSocket, MCP 서버를 사용해서 지역별 날씨와 달 정보를 대화형으로 조회하는 웹 앱입니다.

브라우저에서는 채팅처럼 질문을 보내고, 서버는 OpenAI로 질문 의도를 분석한 뒤 WeatherAPI 또는 MCP tool을 통해 날씨/천문 정보를 가져옵니다. 답변은 WebSocket으로 스트리밍되며, 오른쪽 패널에는 날씨 또는 달 모양 정보가 카드 형태로 표시됩니다.

## 주요 기능

- 자연어 채팅으로 날씨와 달 정보 조회
- 한국어 지역명, 영어 도시명, 날짜 표현 처리
- OpenAI를 이용한 장소 검증, 날짜/의도 분석, 한국어 답변 생성
- WeatherAPI를 이용한 현재 날씨, 날짜별 날씨, 천문 정보 조회
- MCP 서버를 통한 `get_weather`, `get_astronomy` tool 제공
- WebSocket 기반 답변 스트리밍
- 세션 UUID 기반 대화 히스토리 유지
- 대화 지우기
- Markdown 표, 목록, 줄바꿈 렌더링
- 통신 로그 카드 표시

## 현재 디렉토리 구성

```text
weather/
├── frontend/
│   ├── index.html          # 프론트엔드 HTML
│   ├── styles.css          # UI 스타일
│   └── app.js              # 브라우저 로직, WebSocket, Markdown 렌더링
├── backend/
│   ├── __init__.py
│   ├── host_app.py         # Host FastAPI 앱, MCP client, 정적 파일 제공
│   ├── main_weather.py     # 핵심 날씨/천문/OpenAI/WebSocket 로직
│   └── client_gateway.py   # host_app app 재노출용 진입점
├── mcp_server/
│   ├── __init__.py
│   └── weather_mcp_server.py # MCP tool 서버
├── my_project.py           # 초기 실습/보조 파일
├── requirements.txt        # Python 의존성
├── .env.example            # 환경변수 예시
└── README.md               # 프로젝트 요약 문서
```

프론트엔드, 백엔드, MCP 서버를 폴더로 분리했습니다. 실행 명령도 이 구조를 기준으로 작성되어 있습니다.

## 서버 구성

이 프로젝트는 MCP 실습 구조라서 서버를 최대 3개 띄웁니다.

```text
브라우저
  ↓ WebSocket / HTTP
Host 앱 FastAPI, port 8000
  ↓ MCP tool 호출
Weather MCP 서버, port 9000
  ↓ 외부 API
WeatherAPI / OpenAI
```

### 1. MCP 서버

`mcp_server/weather_mcp_server.py`는 MCP tool 서버입니다.

제공 tool:

- `get_weather(location, date)`
- `get_astronomy(location, date)`

기본 주소:

```text
http://127.0.0.1:9000/mcp
```

### 2. Host 앱

`backend/host_app.py`는 브라우저와 통신하는 FastAPI 앱입니다.

역할:

- `/ws` WebSocket 채팅 처리
- `/status` 연결 상태 확인
- `/weather`, `/astronomy` HTTP API 제공
- MCP client로 MCP 서버의 tool 호출
- `index.html`, `styles.css`, `app.js` 정적 파일 제공

기본 주소:

```text
http://127.0.0.1:8000
```

### 3. 정적 HTML 서버

정적 서버는 선택 사항입니다. `index.html`을 `5500`에서 띄우고 싶을 때 사용합니다.

```text
http://127.0.0.1:5500/index.html
```

현재 `app.js`는 `5500`에서 열렸을 때 Host 앱을 `http://127.0.0.1:8000`으로 바라보도록 되어 있습니다.

## 환경변수

`.env.example`을 복사해서 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

필수 값:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
WEATHER_API_KEY=your_weatherapi_key_here
```

선택 값:

```env
MCP_URL=http://127.0.0.1:9000/mcp
MCP_HOST=0.0.0.0
MCP_PORT=9000
MCP_TRANSPORT=streamable-http
```

`.env`를 수정했다면 Host 앱을 재시작해야 반영됩니다.

## Quickstart

### 1. 필요한 패키지

이 프로젝트는 Python 3.11 이상을 권장합니다.

Python 패키지는 `requirements.txt`로 관리합니다.

```text
fastapi
uvicorn[standard]
requests
mcp
langchain-mcp-adapters
```

패키지 역할:

| 패키지 | 용도 |
|---|---|
| `fastapi` | Host 앱과 WebSocket API |
| `uvicorn[standard]` | FastAPI 실행 서버, WebSocket 지원 |
| `requests` | OpenAI, WeatherAPI HTTP 요청 |
| `mcp` | MCP 서버 구현 |
| `langchain-mcp-adapters` | Host 앱에서 MCP tool 호출 |

### 2. 가상환경 만들기

```bash
cd ~/weather
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

이미 `.venv`가 있다면 활성화만 하면 됩니다.

```bash
cd ~/weather
source .venv/bin/activate
```

### 3. 환경변수 설정 확인

`.env` 파일에 아래 값이 들어 있어야 합니다.

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
WEATHER_API_KEY=your_weatherapi_key_here
```

### 4. 실행 방법

### 터미널 1: MCP 서버

```bash
cd ~/weather
source .venv/bin/activate
python -m mcp_server.weather_mcp_server
```

### 터미널 2: Host 앱

```bash
cd ~/weather
source .venv/bin/activate
uvicorn backend.host_app:app --reload --host 0.0.0.0 --port 8000
```

### 터미널 3: 정적 HTML 서버

```bash
cd ~/weather/frontend
python3 -m http.server 5500 --bind 0.0.0.0
```

브라우저:

```text
http://127.0.0.1:5500/index.html
```

Host 앱만으로도 정적 파일을 제공하므로 아래 주소도 사용할 수 있습니다.

```text
http://127.0.0.1:8000
```

## 주요 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/` | `index.html` 반환 |
| `GET` | `/status` | OpenAI, WeatherAPI 연결 상태 확인 |
| `GET` | `/weather?location=Seoul&date=2026-04-24` | 날씨 조회 |
| `GET` | `/astronomy?location=Seoul&date=2026-04-24` | 달/해 정보 조회 |
| `WS` | `/ws` | 채팅 WebSocket |

## WebSocket 메시지 흐름

브라우저에서 질문을 보내면:

```json
{
  "type": "chat",
  "message": "4월 24일 서울 달 모양 알려줘"
}
```

서버는 다음 이벤트를 순서대로 보낼 수 있습니다.

| type | 설명 |
|---|---|
| `session` | WebSocket 연결 시 세션 UUID 전달 |
| `chat_start` | 의도 분석과 API 조회 결과 전달 |
| `chat_delta` | OpenAI 답변 chunk 스트리밍 |
| `chat_done` | 최종 답변과 통신 로그 전달 |
| `clear_history` | 대화 기록 초기화 |

## 답변 생성 규칙

`backend/main_weather.py`에서 OpenAI에게 다음 규칙을 지시합니다.

- 항상 한국어로 답변
- 사용자의 현재 질문을 히스토리보다 우선
- 날씨/천문 데이터는 API 결과만 사용
- 지역이 실제 조회 가능한 장소인지 1차 검증
- 날씨 정보는 표 형태를 우선 사용
- 달 정보는 “떠 있음/해가 졌음” 같은 상태 판단을 피하고 달 위상과 모양 설명 중심으로 답변
- 이미지 URL, API 필드명, 내부 로그 언급 금지

## 프론트엔드 구성

### `frontend/index.html`

앱의 화면 구조입니다.

- 상단 서비스 상태
- 채팅 패널
- 오른쪽 날씨/달 정보 패널
- 통신 로그 영역

### `frontend/styles.css`

전체 UI 스타일입니다.

- 화이트/라이트 그레이 기반 배경
- 보라색 포인트 컬러
- 채팅 버블
- 날씨/달 카드
- skeleton 로딩
- 통신 로그 카드

### `frontend/app.js`

브라우저 동작을 담당합니다.

- WebSocket 연결
- 채팅 메시지 전송
- 스트리밍 답변 렌더링
- Markdown 표/목록/줄바꿈 렌더링
- 오른쪽 날씨/달 패널 업데이트
- 통신 로그 렌더링

## 백엔드 구성

### `backend/main_weather.py`

핵심 로직입니다.

- WeatherAPI 호출
- OpenAI Responses API 호출
- 지역명 검증과 변환
- 날짜 해석
- 날씨/천문 결과 가공
- WebSocket 채팅 처리
- 세션 히스토리 관리

### `backend/host_app.py`

Host 앱입니다.

- 브라우저 요청 수신
- 정적 파일 제공
- MCP client 관리
- MCP tool 호출
- `backend.main_weather.websocket_endpoint` 연결

### `mcp_server/weather_mcp_server.py`

MCP 서버입니다.

- `get_weather`
- `get_astronomy`

## 자주 나는 문제

### OpenAI 키를 바꿨는데 이전 키로 요청되는 경우

`.env` 변경 후 Host 앱을 재시작해야 합니다.

```bash
Ctrl+C
uvicorn backend.host_app:app --reload --host 0.0.0.0 --port 8000
```

### `No module named 'mcp'`

가상환경을 활성화하고 의존성을 설치합니다.

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### WebSocket 경고가 나는 경우

`uvicorn[standard]`가 설치되어 있어야 합니다.

```bash
pip install "uvicorn[standard]"
```

### `styles.css`, `app.js`가 404인 경우

`backend/host_app.py`에는 `/styles.css`, `/app.js` 라우트가 있습니다. Host 앱 주소로 열거나, 정적 서버를 `frontend/` 디렉토리에서 실행해야 합니다.

```bash
cd ~/weather/frontend
python3 -m http.server 5500 --bind 0.0.0.0
```

## 앞으로 정리하면 좋은 것

- 오래된 실습 파일 정리
- API 호출부와 OpenAI 호출부 모듈 분리
- 테스트 추가
- `.gitignore` 추가
- README의 실행 방식과 실제 구조를 계속 동기화
