from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from datetime import date as date_class
from pathlib import Path
import requests
import json
import re
import os
import uuid
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

def clean_api_key(value: str | None):
    cleaned = (value or "").strip().strip("\"'")
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:]
    return re.sub(r"\s+", "", cleaned)

WEATHER_API_KEY = clean_api_key(os.getenv("WEATHER_API_KEY", "e975fa35dbd747ec98002358261704"))  # 발급받은 키로 교체
OPENAI_API_KEY = clean_api_key(os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LOCATION_ALIASES = {
    "서울": "Seoul",
    "서울시": "Seoul",
    "부산": "Busan",
    "부산시": "Busan",
    "인천": "Incheon",
    "인천시": "Incheon",
    "대구": "Daegu",
    "대구시": "Daegu",
    "대전": "Daejeon",
    "대전시": "Daejeon",
    "광주": "Gwangju",
    "광주시": "Gwangju",
    "울산": "Ulsan",
    "울산시": "Ulsan",
    "세종": "Sejong",
    "세종시": "Sejong",
    "제주": "Jeju",
    "제주도": "Jeju",
    "제주시": "Jeju",
    "수원": "Suwon",
    "수원시": "Suwon",
    "춘천": "Chuncheon",
    "춘천시": "Chuncheon",
    "강릉": "Gangneung",
    "강릉시": "Gangneung",
    "청주": "Cheongju",
    "청주시": "Cheongju",
    "전주": "Jeonju",
    "전주시": "Jeonju",
    "포항": "Pohang",
    "포항시": "Pohang",
    "창원": "Changwon",
    "창원시": "Changwon",
    "런던": "London",
    "도쿄": "Tokyo",
    "오사카": "Osaka",
    "뉴욕": "New York",
    "파리": "Paris",
    "방콕": "Bangkok",
    "싱가포르": "Singapore",
}
LOCATION_STOPWORDS = (
    "현재",
    "오늘",
    "지금",
    "날씨",
    "기온",
    "온도",
    "알려줘",
    "조회",
    "검색",
    "어때",
    "몇도",
)
MOON_PHASE_LABELS = {
    "new moon": "삭",
    "waxing crescent": "초승달",
    "first quarter": "상현달",
    "waxing gibbous": "차가는 볼록달",
    "full moon": "보름달",
    "waning gibbous": "기우는 볼록달",
    "last quarter": "하현달",
    "waning crescent": "그믐달",
}
MOON_PHASE_DESCRIPTIONS = {
    "new moon": "달의 밝은 면이 거의 보이지 않는 시기입니다.",
    "waxing crescent": "오른쪽이 가늘게 밝아지는 초승달 모양입니다.",
    "first quarter": "오른쪽 절반이 밝게 보이는 반달입니다.",
    "waxing gibbous": "보름달을 향해 둥글게 차오르는 모양입니다.",
    "full moon": "달의 밝은 면이 거의 둥글게 보이는 보름달입니다.",
    "waning gibbous": "보름 이후 밝은 면이 조금씩 줄어드는 둥근 달입니다.",
    "last quarter": "왼쪽 절반이 밝게 보이는 반달입니다.",
    "waning crescent": "왼쪽이 가늘게 남은 그믐달 모양입니다.",
}

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

@app.get("/")
@app.get("/index.html")
async def read_index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/weather")
async def read_weather(
    location: str = Query(..., min_length=1),
    selected_date: str | None = Query(None, alias="date"),
):
    return get_weather(location, selected_date)

@app.get("/astronomy")
async def read_astronomy(
    location: str = Query(..., min_length=1),
    selected_date: str | None = Query(None, alias="date"),
):
    return get_astronomy(location, selected_date)

@app.get("/status")
async def read_status():
    return {
        "openai": check_openai_status(),
        "weatherapi": check_weatherapi_status(),
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    chat_history = []
    await websocket.send_text(json.dumps({
        "type": "session",
        "session_id": session_id,
    }, ensure_ascii=False))
    try:
        while True:
            message = await websocket.receive_text()
            try:
                request_data = json.loads(message)
                request_type = request_data.get("type", "weather")
                chat_message = request_data.get("message", "")
                location = request_data.get("location", "")
                selected_date = request_data.get("date")

                if request_type == "chat":
                    await stream_weather_chat(websocket, chat_message, session_id, chat_history)
                    continue
                elif request_type == "clear_history":
                    chat_history.clear()
                    response = {
                        "type": "clear_history",
                        "session_id": session_id,
                        "logs": [],
                    }
                elif not location.strip():
                    response = {"error": "지역명을 입력해주세요.", "logs": []}
                elif request_type == "astronomy":
                    response = get_astronomy(location, selected_date)
                else:
                    response = get_weather(location, selected_date)

                response["type"] = request_type
                response["session_id"] = session_id
                await websocket.send_text(json.dumps(response, ensure_ascii=False))
            except Exception as error:
                await websocket.send_text(json.dumps({
                    "error": "WebSocket 요청을 처리하지 못했습니다.",
                    "detail": str(error),
                    "logs": [],
                }, ensure_ascii=False))
    except WebSocketDisconnect:
        return

def check_openai_status():
    if not OPENAI_API_KEY:
        return {
            "connected": False,
            "message": "OPENAI_API_KEY 없음",
        }

    logs = []
    output = call_openai_response(
        "Return only the word ok.",
        "health check",
        logs,
        "OpenAI 상태 확인",
        16,
    )
    if output:
        return {
            "connected": True,
            "message": "연결됨",
            "model": OPENAI_MODEL,
        }

    http_log = next(
        (log for log in reversed(logs) if log.get("response", {}).get("status_code") is not None),
        None,
    )
    last_log = logs[-1] if logs else {}
    response = (http_log or last_log).get("response", {})
    fallback_response = last_log.get("response", {})
    try:
        return {
            "connected": False,
            "status_code": response.get("status_code"),
            "message": (
                response.get("error")
                or response.get("message")
                or response.get("output")
                or fallback_response.get("detail")
                or fallback_response.get("message")
                or "응답 오류"
            ),
            "error_type": fallback_response.get("error_type"),
            "model": OPENAI_MODEL,
        }
    except Exception:
        return {
            "connected": False,
            "message": "상태 확인 실패",
            "model": OPENAI_MODEL,
        }

def check_weatherapi_status():
    try:
        response = requests.get(
            "https://api.weatherapi.com/v1/search.json",
            params={
                "key": WEATHER_API_KEY,
                "q": "Seoul",
            },
            timeout=5,
        )
        return {
            "connected": response.ok,
            "status_code": response.status_code,
            "message": "연결됨" if response.ok else "응답 오류",
        }
    except requests.exceptions.RequestException:
        return {
            "connected": False,
            "message": "연결 실패",
        }

def normalize_location(location: str):
    return normalize_location_with_trace(location, None)

def normalize_location_with_trace(location: str, logs):
    cleaned = location.strip()
    for word in LOCATION_STOPWORDS:
        cleaned = cleaned.replace(word, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,./")

    if cleaned in LOCATION_ALIASES:
        translated = LOCATION_ALIASES[cleaned]
        add_log(logs, "local", "지역명 매핑", "complete", {"input": location}, {"query": translated})
        return translated

    suffix_removed = re.sub(r"(특별시|광역시|특별자치시|특별자치도|시|도)$", "", cleaned).strip()
    if suffix_removed in LOCATION_ALIASES:
        translated = LOCATION_ALIASES[suffix_removed]
        add_log(logs, "local", "지역명 매핑", "complete", {"input": location}, {"query": translated})
        return translated

    translated_location = translate_location_with_openai(cleaned, logs)
    query = translated_location or cleaned
    add_log(logs, "local", "최종 검색어", "complete", {"input": location}, {"query": query})
    return query

def add_log(logs, service, title, status, request=None, response=None):
    if logs is None:
        return
    logs.append({
        "service": service,
        "title": title,
        "status": status,
        "request": request or {},
        "response": response or {},
    })

def redacted_params(params):
    safe_params = dict(params)
    if "key" in safe_params:
        safe_params["key"] = "***"
    return safe_params

def compact_weather_response(data):
    if not isinstance(data, dict):
        return {"body": data}

    location = data.get("location", {})
    current = data.get("current", {})
    forecast_days = data.get("forecast", {}).get("forecastday", [])
    astronomy = data.get("astronomy", {}).get("astro", {})
    summary = {}

    if location:
        summary["location"] = {
            "name": location.get("name"),
            "country": location.get("country"),
            "localtime": location.get("localtime"),
        }
    if current:
        condition = current.get("condition", {})
        summary["current"] = {
            "temp_c": current.get("temp_c"),
            "condition": condition.get("text"),
        }
    if forecast_days:
        day = forecast_days[0].get("day", {})
        condition = day.get("condition", {})
        summary["forecastday"] = {
            "date": forecast_days[0].get("date"),
            "avgtemp_c": day.get("avgtemp_c"),
            "condition": condition.get("text"),
        }
    if astronomy:
        summary["astronomy"] = {
            "sunrise": astronomy.get("sunrise"),
            "sunset": astronomy.get("sunset"),
            "moonrise": astronomy.get("moonrise"),
            "moonset": astronomy.get("moonset"),
            "moon_phase": astronomy.get("moon_phase"),
        }
    return summary or {"keys": list(data.keys())}

def should_skip_openai_location(location: str):
    value = location.strip().lower()
    if not value:
        return True
    if value == "auto:ip":
        return True
    if value.startswith(("id:", "iata:", "metar:")):
        return True
    if re.fullmatch(r"-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?", value):
        return True
    if re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", value):
        return True
    return False

def parse_openai_text(response_data):
    output_text = response_data.get("output_text")
    if output_text:
        return output_text

    for item in response_data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")
    return ""

def openai_error_message(response_data):
    if not isinstance(response_data, dict):
        return ""

    error = response_data.get("error")
    if isinstance(error, dict):
        return error.get("message") or error.get("code") or ""
    if isinstance(error, str):
        return error
    return ""

def post_openai_response(url, headers, payload, timeout):
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response_data = response.json() if response.content else {}
    error_message = openai_error_message(response_data).lower()

    if response.status_code == 400 and "temperature" in error_message and "temperature" in payload:
        fallback_payload = dict(payload)
        fallback_payload.pop("temperature", None)
        response = requests.post(url, headers=headers, json=fallback_payload, timeout=timeout)
        response_data = response.json() if response.content else {}
        return response, response_data, True

    return response, response_data, False

def call_openai_response(instructions: str, input_text: str, logs, title: str, max_output_tokens=400):
    if not OPENAI_API_KEY:
        add_log(
            logs,
            "ai",
            title,
            "skipped",
            {"model": OPENAI_MODEL, "input": input_text},
            {"reason": "OPENAI_API_KEY가 설정되지 않았습니다."},
        )
        return None

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": input_text,
        "temperature": 0,
        "max_output_tokens": max_output_tokens,
    }
    try:
        response, response_data, retried_without_temperature = post_openai_response(url, headers, payload, 10)
        output_text = parse_openai_text(response_data).strip()
        error_message = openai_error_message(response_data)
        add_log(
            logs,
            "ai",
            title,
            "complete" if response.ok else "error",
            {"method": "POST", "url": url, "model": OPENAI_MODEL, "input": input_text},
            {
                "status_code": response.status_code,
                "output": output_text,
                "error": error_message,
                "retried_without_temperature": retried_without_temperature,
            },
        )
        response.raise_for_status()
        return output_text
    except requests.exceptions.RequestException as error:
        add_log(
            logs,
            "ai",
            f"{title} 실패",
            "error",
            {"method": "POST", "url": url, "model": OPENAI_MODEL, "input": input_text},
            {
                "message": "OpenAI 요청 실패",
                "detail": str(error),
                "error_type": type(error).__name__,
            },
        )
        return None

def parse_json_text(text: str):
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def clean_translated_location(value: str):
    cleaned = value.strip().strip("\"'` ,./")
    cleaned = re.sub(r"^(location|query|city)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.splitlines()[0].strip(" ,./") if cleaned else ""
    if not cleaned or len(cleaned) > 80:
        return None
    return cleaned

def translate_location_with_openai(location: str, logs=None):
    if not OPENAI_API_KEY or should_skip_openai_location(location):
        add_log(
            logs,
            "ai",
            "OpenAI 지역명 변환",
            "skipped",
            {"input": location, "model": OPENAI_MODEL},
            {"reason": "OPENAI_API_KEY 없음 또는 변환 불필요"},
        )
        return None

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "instructions": (
            "You convert user location text into one concise English location query "
            "for WeatherAPI.com. Return only the location name. No explanation. "
            "Examples: '부산 날씨' -> 'Busan', '뉴욕' -> 'New York', "
            "'강남구' -> 'Gangnam-gu, Seoul', 'ny' -> 'New York'."
        ),
        "input": location,
        "temperature": 0,
        "max_output_tokens": 32,
    }
    try:
        response, response_data, retried_without_temperature = post_openai_response(url, headers, payload, 8)
        translated = clean_translated_location(parse_openai_text(response_data))
        error_message = openai_error_message(response_data)
        add_log(
            logs,
            "ai",
            "OpenAI 지역명 변환 응답",
            "complete" if response.ok else "error",
            {"method": "POST", "url": url, "model": OPENAI_MODEL, "input": location},
            {
                "status_code": response.status_code,
                "output": translated or parse_openai_text(response_data),
                "error": error_message,
                "retried_without_temperature": retried_without_temperature,
            },
        )
        response.raise_for_status()
        return translated
    except requests.exceptions.RequestException as error:
        add_log(
            logs,
            "ai",
            "OpenAI 지역명 변환 실패",
            "error",
            {"method": "POST", "url": url, "model": OPENAI_MODEL, "input": location},
            {
                "message": "OpenAI 요청 실패, 원본 검색어로 진행",
                "detail": str(error),
                "error_type": type(error).__name__,
            },
        )
        return None

def normalize_date(selected_date: str | None):
    if not selected_date:
        return date_class.today()
    try:
        return date_class.fromisoformat(selected_date)
    except ValueError:
        return date_class.today()

def fetch_current_weather(query_location: str, logs=None):
    url = "https://api.weatherapi.com/v1/current.json"
    params = {
        "key": WEATHER_API_KEY,
        "q": query_location,
        "aqi": "no",
        "lang": "ko",
    }
    response = requests.get(url, params=params, timeout=8)
    response_data = response.json() if response.content else {}
    add_log(
        logs,
        "api",
        "WeatherAPI 현재 날씨 응답",
        "complete" if response.ok else "error",
        {"method": "GET", "url": url, "params": redacted_params(params)},
        {"status_code": response.status_code, "body": compact_weather_response(response_data)},
    )
    response.raise_for_status()
    return response_data

def fetch_dated_weather(query_location: str, target_date, logs=None):
    today = date_class.today()
    days_from_today = (target_date - today).days
    if days_from_today < 0:
        method = "history.json"
    elif days_from_today <= 14:
        method = "forecast.json"
    else:
        method = "future.json"

    url = f"https://api.weatherapi.com/v1/{method}"
    params = {
        "key": WEATHER_API_KEY,
        "q": query_location,
        "dt": target_date.isoformat(),
        "aqi": "no",
        "lang": "ko",
    }
    if method == "forecast.json":
        params["days"] = "1"
        params["alerts"] = "no"

    response = requests.get(url, params=params, timeout=8)
    response_data = response.json() if response.content else {}
    add_log(
        logs,
        "api",
        "WeatherAPI 날짜별 날씨 응답",
        "complete" if response.ok else "error",
        {"method": "GET", "url": url, "params": redacted_params(params)},
        {"status_code": response.status_code, "body": compact_weather_response(response_data)},
    )
    response.raise_for_status()
    return response_data

def fetch_astronomy(query_location: str, target_date, logs=None):
    url = "https://api.weatherapi.com/v1/astronomy.json"
    params = {
        "key": WEATHER_API_KEY,
        "q": query_location,
        "dt": target_date.isoformat(),
    }
    response = requests.get(url, params=params, timeout=8)
    response_data = response.json() if response.content else {}
    add_log(
        logs,
        "api",
        "WeatherAPI 천문 응답",
        "complete" if response.ok else "error",
        {"method": "GET", "url": url, "params": redacted_params(params)},
        {"status_code": response.status_code, "body": compact_weather_response(response_data)},
    )
    response.raise_for_status()
    return response_data

def search_weather_location(query_location: str, logs=None):
    url = "https://api.weatherapi.com/v1/search.json"
    params = {
        "key": WEATHER_API_KEY,
        "q": query_location,
    }
    response = requests.get(url, params=params, timeout=8)
    results = response.json() if response.content else []
    add_log(
        logs,
        "api",
        "WeatherAPI 지역 검색 응답",
        "complete" if response.ok else "error",
        {"method": "GET", "url": url, "params": redacted_params(params)},
        {"status_code": response.status_code, "count": len(results) if isinstance(results, list) else None, "first": results[0] if isinstance(results, list) and results else None},
    )
    response.raise_for_status()
    if not results:
        return None
    return results[0]

def build_weather_result(data, query_location: str):
    location_data = data.get("location", {})
    current = data.get("current", {})
    condition = current.get("condition", {})
    icon = condition.get("icon", "")
    if icon.startswith("//"):
        icon = f"https:{icon}"

    return {
        "location": location_data.get("name", query_location),
        "country": location_data.get("country", ""),
        "localtime": location_data.get("localtime", ""),
        "weather": condition.get("text", "정보 없음"),
        "icon": icon,
        "temp": current.get("temp_c"),
        "feelslike": current.get("feelslike_c"),
        "humidity": current.get("humidity"),
        "wind": current.get("wind_kph"),
        "query": query_location,
        "date": date_class.today().isoformat(),
    }

def build_dated_weather_result(data, query_location: str, target_date):
    location_data = data.get("location", {})
    forecast = data.get("forecast", {})
    forecast_days = forecast.get("forecastday", [])
    forecast_day = forecast_days[0] if forecast_days else {}
    day = forecast_day.get("day", {})
    condition = day.get("condition", {})
    icon = condition.get("icon", "")
    if icon.startswith("//"):
        icon = f"https:{icon}"

    return {
        "location": location_data.get("name", query_location),
        "country": location_data.get("country", ""),
        "localtime": forecast_day.get("date", target_date.isoformat()),
        "weather": condition.get("text", "정보 없음"),
        "icon": icon,
        "temp": day.get("avgtemp_c"),
        "feelslike": day.get("avgtemp_c"),
        "humidity": day.get("avghumidity"),
        "wind": day.get("maxwind_kph"),
        "query": query_location,
        "date": target_date.isoformat(),
    }

def normalize_moon_phase(phase: str | None):
    return re.sub(r"\s+", " ", str(phase or "").strip().lower().replace("_", " ").replace("-", " "))

def get_moon_phase_ko(phase: str | None):
    return MOON_PHASE_LABELS.get(normalize_moon_phase(phase), phase or "알 수 없음")

def get_moon_shape_description(phase: str | None):
    return MOON_PHASE_DESCRIPTIONS.get(
        normalize_moon_phase(phase),
        "달의 모양 정보는 위상 이름을 기준으로 확인할 수 있습니다.",
    )

def build_astronomy_result(data, query_location: str, target_date):
    location_data = data.get("location", {})
    astronomy = data.get("astronomy", {})
    astro = astronomy.get("astro", {})
    localtime = location_data.get("localtime", "")
    sunrise = astro.get("sunrise", "-")
    sunset = astro.get("sunset", "-")
    moonrise = astro.get("moonrise", "-")
    moonset = astro.get("moonset", "-")
    moon_phase = astro.get("moon_phase", "Unknown")

    return {
        "location": location_data.get("name", query_location),
        "country": location_data.get("country", ""),
        "localtime": localtime,
        "sunrise": sunrise,
        "sunset": sunset,
        "moonrise": moonrise,
        "moonset": moonset,
        "moon_phase": moon_phase,
        "moon_phase_ko": get_moon_phase_ko(moon_phase),
        "moon_shape_description": get_moon_shape_description(moon_phase),
        "query": query_location,
        "date": target_date.isoformat(),
    }

def get_weather(location: str, selected_date: str | None = None):
    logs = []
    query_location = normalize_location_with_trace(location, logs)
    target_date = normalize_date(selected_date)
    today = date_class.today()
    try:
        if target_date == today:
            data = fetch_current_weather(query_location, logs)
            result = build_weather_result(data, query_location)
        else:
            data = fetch_dated_weather(query_location, target_date, logs)
            result = build_dated_weather_result(data, query_location, target_date)
        result["logs"] = logs
        return result
    except requests.exceptions.HTTPError:
        try:
            matched_location = search_weather_location(query_location, logs)
            if not matched_location:
                raise ValueError("No search result")

            matched_query = f"id:{matched_location['id']}"
            if target_date == today:
                data = fetch_current_weather(matched_query, logs)
                result = build_weather_result(data, matched_location.get("name", query_location))
            else:
                data = fetch_dated_weather(matched_query, target_date, logs)
                result = build_dated_weather_result(data, matched_location.get("name", query_location), target_date)
            result["query"] = matched_location.get("name", query_location)
            result["logs"] = logs
            return result
        except Exception:
            return {
                "location": location,
                "weather": "정보를 가져올 수 없음",
                "temp": None,
                "query": query_location,
                "error": "지역명을 찾지 못했습니다. 영문 도시명, 공항코드, 우편번호, 위도/경도를 입력해보세요.",
                "logs": logs,
            }
    except requests.exceptions.RequestException:
        return {
            "location": location,
            "weather": "정보를 가져올 수 없음",
            "temp": None,
            "query": query_location,
            "error": "날씨 서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.",
            "logs": logs,
        }
    except Exception as e:
        return {
            "location": location,
            "weather": "정보를 가져올 수 없음",
            "temp": None,
            "query": query_location,
            "error": "날씨 정보를 처리하지 못했습니다.",
            "logs": logs,
        }

def get_astronomy(location: str, selected_date: str | None = None):
    logs = []
    query_location = normalize_location_with_trace(location, logs)
    target_date = normalize_date(selected_date)
    try:
        data = fetch_astronomy(query_location, target_date, logs)
        result = build_astronomy_result(data, query_location, target_date)
        result["logs"] = logs
        return result
    except requests.exceptions.HTTPError:
        try:
            matched_location = search_weather_location(query_location, logs)
            if not matched_location:
                raise ValueError("No search result")

            matched_query = f"id:{matched_location['id']}"
            data = fetch_astronomy(matched_query, target_date, logs)
            result = build_astronomy_result(data, matched_location.get("name", query_location), target_date)
            result["query"] = matched_location.get("name", query_location)
            result["logs"] = logs
            return result
        except Exception:
            return {
                "location": location,
                "query": query_location,
                "error": "지역명을 찾지 못했습니다. 영문 도시명, 공항코드, 우편번호, 위도/경도를 입력해보세요.",
                "logs": logs,
            }
    except requests.exceptions.RequestException:
        return {
            "location": location,
            "query": query_location,
            "error": "천문 서버에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.",
            "logs": logs,
        }
    except Exception:
        return {
            "location": location,
            "query": query_location,
            "error": "천문 정보를 처리하지 못했습니다.",
            "logs": logs,
        }

def recent_history_for_prompt(chat_history, limit=8):
    return chat_history[-limit:] if chat_history else []

def append_chat_history(chat_history, user_message, answer, intent=None, result=None):
    if chat_history is None:
        return

    chat_history.append({
        "user": user_message,
        "assistant": answer,
        "intent": intent or {},
        "result": compact_chat_result(result or {}) if result else {},
    })
    del chat_history[:-20]

def location_issue_fallback_answer():
    return "장소를 정확히 확인하지 못했어요. 도시명, 지역명, 공항코드, 우편번호, 또는 위도/경도처럼 날씨 조회가 가능한 실제 위치로 다시 알려주세요."

def location_issue_answer(intent):
    return intent.get("user_answer") or location_issue_fallback_answer()

def validate_intent_location(intent, logs):
    if intent.get("type") not in ("weather", "astronomy"):
        return intent

    location = intent.get("location")
    if not location:
        intent["type"] = "invalid_location"
        intent["location_status"] = "omitted"
        intent["location_reason"] = "장소가 명확하지 않음"
        return intent

    if should_skip_openai_location(location):
        intent["location_status"] = "valid"
        return intent

    try:
        matched_location = search_weather_location(location, logs)
    except requests.exceptions.RequestException:
        intent["type"] = "invalid_location"
        intent["location_status"] = "uncertain"
        intent["location_reason"] = "장소 검증 요청 실패"
        return intent

    if not matched_location:
        intent["type"] = "invalid_location"
        intent["location_status"] = "invalid"
        intent["location_reason"] = "WeatherAPI 검색 결과 없음"
        return intent

    intent["location"] = f"id:{matched_location['id']}"
    intent["resolved_location"] = matched_location.get("name", location)
    intent["resolved_country"] = matched_location.get("country", "")
    intent["location_status"] = "valid"
    return intent

def classify_weather_chat(message: str, logs, chat_history=None):
    today = date_class.today().isoformat()
    instructions = (
        "You are the first gatekeeper for a weather app request. "
        "In one step, decide the user's intent, judge whether the requested place is a real weather-searchable geographic location, and if valid convert it to a WeatherAPI query. "
        "Return only valid JSON with keys: type, location, date, location_status, location_reason, user_answer. "
        "type must be one of: weather, astronomy, chit_chat, invalid_location. "
        "Use chit_chat for greetings, thanks, jokes, app capability questions, or casual conversation that does not ask for weather, temperature, forecast, rain, wind, humidity, moon, sun, sunrise, sunset, moonrise, moonset, or moon phase information. "
        "For chit_chat, set location and date to null, location_status to omitted, and user_answer to null. "
        "For weather or astronomy questions, inspect the place in current_message before using history. "
        "If current_message contains an explicit place that is not a real geographic location or cannot reasonably be searched by WeatherAPI, set type to invalid_location. "
        "Examples of invalid places include private rooms, objects, vague facilities, or concepts like bathroom, restroom, bedroom, desk, my house, company, and similar phrases. Do not translate these into a city. "
        "For invalid_location, keep location as the user's original place text, set date to null, set location_status to invalid or uncertain, and write a polite Korean user_answer asking the user to provide a city, region, airport code, postal code, or coordinates. "
        "Use astronomy only for moon, sun, sunrise, sunset, moonrise, moonset, moon phase questions. "
        "Use weather for temperature, forecast, rain, wind, humidity, general weather questions. "
        f"Today's date is {today}. Resolve relative dates like today, tomorrow, yesterday, this weekend, next Friday, or Korean relative dates to YYYY-MM-DD. "
        "The current_message is always more important than recent_history. "
        "Use recent_history only to fill an omitted location or date for follow-up references like 'there', 'that city', 'same place', 'tomorrow there', or Korean phrases like '거기', '그곳', '같은 곳'. "
        "Never replace an explicit invalid, uncertain, or non-geographic location in current_message with a location from recent_history. "
        "If current_message explicitly includes a location, validate that location first and do not override it from history. "
        "If the place is a real geographic place, translate it to one concise English WeatherAPI query in location. "
        "Set location_status to valid only when the current or history-resolved place is a real searchable geographic place and location contains the English WeatherAPI query. "
        "Set location_status to uncertain when you cannot confidently decide or convert the user's place into an English WeatherAPI query; then type must be invalid_location and user_answer must ask the user to clarify the place. "
        "Set location_status to omitted when no location exists in the current message and history cannot safely fill it. "
        "For weather and astronomy only: if no date is mentioned, use today's date. Do not default missing locations to Seoul. "
        "For valid weather or astronomy, user_answer must be null."
    )
    input_text = json.dumps({
        "current_message": message,
        "recent_history": recent_history_for_prompt(chat_history),
    }, ensure_ascii=False)
    output = call_openai_response(instructions, input_text, logs, "OpenAI 대화 의도 분석", 180)
    parsed = parse_json_text(output)
    if not parsed:
        return {
            "type": "invalid_location",
            "location": None,
            "date": None,
            "location_status": "uncertain",
            "location_reason": "OpenAI 의도 분석 실패",
            "user_answer": "",
        }

    request_type = parsed.get("type", "weather")
    if request_type not in ("weather", "astronomy", "chit_chat", "invalid_location"):
        request_type = "weather"

    if request_type == "chit_chat":
        return {
            "type": "chit_chat",
            "location": None,
            "date": None,
            "location_status": "omitted",
            "user_answer": None,
        }

    location_status = parsed.get("location_status") or "valid"
    if (
        request_type == "invalid_location"
        or location_status in ("invalid", "uncertain", "omitted")
    ):
        return {
            "type": "invalid_location",
            "location": parsed.get("location"),
            "date": None,
            "location_status": location_status,
            "location_reason": parsed.get("location_reason") or "",
            "user_answer": parsed.get("user_answer") or "",
        }

    return {
        "type": request_type,
        "location": parsed.get("location"),
        "date": parsed.get("date") or today,
        "location_status": location_status,
        "location_reason": parsed.get("location_reason") or "",
        "user_answer": None,
    }

def build_chit_chat_answer(user_message: str, logs, chat_history=None):
    instructions = (
        "You are a warm Korean assistant inside a weather and moon app. "
        "Reply in natural Korean only. Keep it friendly and concise. "
        "For casual conversation, answer normally. "
        "Use recent_history so the conversation feels continuous while this WebSocket session is connected. "
        "If helpful, briefly mention that the user can ask about weather, temperature, forecast, rain, wind, humidity, moon phase, sunrise, or sunset by city and date. "
        "Do not invent weather facts unless the user asks for a weather lookup."
    )
    input_text = json.dumps({
        "current_message": user_message,
        "recent_history": recent_history_for_prompt(chat_history),
    }, ensure_ascii=False)
    output = call_openai_response(instructions, input_text, logs, "OpenAI 가벼운 대화 답변", 300)
    cleaned_output = clean_chat_answer(output)
    if cleaned_output and looks_non_korean(cleaned_output):
        translated_output = call_openai_response(
            "Translate the following assistant answer into natural Korean only. Return only Korean text.",
            cleaned_output,
            logs,
            "OpenAI 잡담 한국어 변환",
            300,
        )
        cleaned_output = clean_chat_answer(translated_output) or cleaned_output
    return cleaned_output or "좋아요. 가볍게 이야기해도 되고, 도시와 날짜를 말해주면 날씨나 달 정보도 바로 찾아드릴게요."

def build_chat_answer(user_message: str, intent, data, logs, chat_history=None):
    if data.get("error"):
        return data["error"]

    instructions = (
        "You are a friendly Korean weather assistant. "
        "Always answer in Korean only, regardless of the user's language or the API result language. "
        "Use natural Korean sentences, not English. "
        "Answer the user's question naturally and concisely using only the provided API result. "
        "Use recent_history only for conversational continuity, but do not override the provided API result. "
        "Mention location and date. If astronomy data is provided, explain the moon/sun information. "
        "If weather data is provided, explain temperature, condition, humidity, and wind when available. "
        "Use Markdown. When listing two or more label-value facts, use a compact Markdown table with Korean headers like 항목 and 내용 instead of bullets. "
        "Use bullets only for short advice or notes that are not label-value facts. "
        "For astronomy, focus on moon_phase_ko, moon_shape_description, moonrise, moonset, sunrise, and sunset. "
        "Describe the moon shape, not whether the moon or sun is currently up. "
        "Do not translate First Quarter as 첫째 보름; use 상현달. "
        "Do not write any sentence that says the moon is up, the moon is not up, the sun is up, the sun is down, or the sun never sets. "
        "Never mention image URLs, icon URLs, raw API field names, JSON keys, or internal request logs. "
        "Do not say phrases like weather icon, image URL, icon field, or API response."
    )
    input_text = json.dumps({
        "user_message": user_message,
        "interpreted_request": intent,
        "api_result": compact_chat_result(data),
        "recent_history": recent_history_for_prompt(chat_history),
    }, ensure_ascii=False)
    output = call_openai_response(instructions, input_text, logs, "OpenAI 자연어 답변 생성", 500)
    cleaned_output = clean_chat_answer(output)
    if cleaned_output and looks_non_korean(cleaned_output):
        translated_output = call_openai_response(
            "Translate the following weather assistant answer into natural Korean only. Return only Korean text.",
            cleaned_output,
            logs,
            "OpenAI 한국어 답변 변환",
            500,
        )
        cleaned_output = clean_chat_answer(translated_output) or cleaned_output
    return cleaned_output or "요청한 정보를 가져왔지만 답변 문장을 만들지 못했습니다."

def build_chit_chat_stream_payload(user_message: str, chat_history=None):
    instructions = (
        "You are a warm Korean assistant inside a weather and moon app. "
        "Reply in natural Korean only. Keep it friendly and concise. "
        "Use recent_history so the conversation feels continuous while this WebSocket session is connected. "
        "You may use Markdown. If a table would make the answer clearer, use a compact Markdown table. "
        "Do not invent weather facts unless the user asks for a weather lookup."
    )
    input_text = json.dumps({
        "current_message": user_message,
        "recent_history": recent_history_for_prompt(chat_history),
    }, ensure_ascii=False)
    return instructions, input_text, "OpenAI 잡담 스트리밍 답변", 500

def build_location_issue_stream_payload(user_message: str, intent, chat_history=None):
    instructions = (
        "You are a Korean weather app assistant. "
        "The user's request cannot be answered because the requested place is not confirmed as a real weather-searchable geographic location. "
        "Answer in natural Korean only. "
        "Do not use a fixed template. "
        "Briefly explain why the current place is not enough, then ask the user to provide a city, region, airport code, postal code, or coordinates. "
        "Use the user's original wording when helpful. "
        "Do not invent or substitute a city from history."
    )
    input_text = json.dumps({
        "current_message": user_message,
        "interpreted_request": intent,
        "recent_history": recent_history_for_prompt(chat_history),
    }, ensure_ascii=False)
    return instructions, input_text, "OpenAI 장소 재설정 답변", 300

def build_location_issue_answer(user_message: str, intent, logs, chat_history=None):
    if intent.get("user_answer"):
        return intent["user_answer"]

    instructions, input_text, title, max_tokens = build_location_issue_stream_payload(user_message, intent, chat_history)
    output = call_openai_response(instructions, input_text, logs, title, max_tokens)
    cleaned_output = clean_chat_answer(output)
    return cleaned_output or location_issue_fallback_answer()

def build_weather_stream_payload(user_message: str, intent, data, chat_history=None):
    instructions = (
        "You are a friendly Korean weather assistant. "
        "Always answer in Korean only, regardless of the user's language or the API result language. "
        "Answer naturally and concisely using only the provided API result. "
        "Use recent_history only for conversational continuity, but do not override the provided API result. "
        "Mention location and date. If astronomy data is provided, explain the moon/sun information. "
        "If weather data is provided, explain temperature, condition, humidity, and wind when available. "
        "Use Markdown. When listing two or more label-value facts, use a compact Markdown table with Korean headers like 항목 and 내용 instead of bullets. "
        "Use bullets only for short advice or notes that are not label-value facts. "
        "For astronomy, focus on moon_phase_ko, moon_shape_description, moonrise, moonset, sunrise, and sunset. "
        "Describe the moon shape, not whether the moon or sun is currently up. "
        "Do not translate First Quarter as 첫째 보름; use 상현달. "
        "Do not write any sentence that says the moon is up, the moon is not up, the sun is up, the sun is down, or the sun never sets. "
        "Never mention image URLs, icon URLs, raw API field names, JSON keys, or internal request logs. "
        "Do not say phrases like weather icon, image URL, icon field, or API response."
    )
    input_text = json.dumps({
        "user_message": user_message,
        "interpreted_request": intent,
        "api_result": compact_chat_result(data),
        "recent_history": recent_history_for_prompt(chat_history),
    }, ensure_ascii=False)
    return instructions, input_text, "OpenAI 자연어 스트리밍 답변", 700

def stream_openai_response_chunks(instructions: str, input_text: str, logs, title: str, max_output_tokens=700):
    if not OPENAI_API_KEY:
        add_log(
            logs,
            "ai",
            title,
            "skipped",
            {"model": OPENAI_MODEL, "input": input_text, "stream": True},
            {"reason": "OPENAI_API_KEY가 설정되지 않았습니다."},
        )
        return

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": input_text,
        "max_output_tokens": max_output_tokens,
        "stream": True,
    }
    collected = []
    try:
        with requests.post(url, headers=headers, json=payload, timeout=30, stream=True) as response:
            if not response.ok:
                response_data = response.json() if response.content else {}
                add_log(
                    logs,
                    "ai",
                    title,
                    "error",
                    {"method": "POST", "url": url, "model": OPENAI_MODEL, "stream": True},
                    {
                        "status_code": response.status_code,
                        "error": openai_error_message(response_data),
                    },
                )
                response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue

                data_text = line.removeprefix("data:").strip()
                if data_text == "[DONE]":
                    break

                try:
                    event_data = json.loads(data_text)
                except json.JSONDecodeError:
                    continue

                if event_data.get("type") == "response.output_text.delta":
                    delta = event_data.get("delta", "")
                    if delta:
                        collected.append(delta)
                        yield delta
                elif event_data.get("type") == "error":
                    raise RuntimeError(event_data.get("message") or "OpenAI stream error")

        add_log(
            logs,
            "ai",
            title,
            "complete",
            {"method": "POST", "url": url, "model": OPENAI_MODEL, "stream": True},
            {"output_length": len("".join(collected))},
        )
    except Exception as error:
        add_log(
            logs,
            "ai",
            f"{title} 실패",
            "error",
            {"method": "POST", "url": url, "model": OPENAI_MODEL, "stream": True},
            {"message": str(error), "error_type": type(error).__name__},
        )

async def stream_text_to_websocket(websocket: WebSocket, instructions: str, input_text: str, logs, title: str, max_output_tokens=700):
    chunks = []
    for chunk in stream_openai_response_chunks(instructions, input_text, logs, title, max_output_tokens):
        chunks.append(chunk)
        await websocket.send_text(json.dumps({
            "type": "chat_delta",
            "delta": chunk,
        }, ensure_ascii=False))
    return clean_chat_answer("".join(chunks))

async def stream_weather_chat(websocket: WebSocket, message: str, session_id=None, chat_history=None):
    logs = []
    if not message.strip():
        await websocket.send_text(json.dumps({
            "type": "chat",
            "session_id": session_id,
            "answer": "궁금한 지역과 날짜를 함께 물어봐 주세요. 예: 내일 서울 날씨 어때?",
            "logs": logs,
        }, ensure_ascii=False))
        return

    intent = validate_intent_location(classify_weather_chat(message, logs, chat_history), logs)
    result = None
    data = None

    if intent["type"] not in ("chit_chat", "invalid_location"):
        if intent["type"] == "astronomy":
            data = get_astronomy(intent["location"], intent["date"])
        else:
            data = get_weather(intent["location"], intent["date"])
        if intent.get("resolved_location"):
            data["query"] = intent["resolved_location"]
        logs.extend(data.get("logs", []))
        result = {key: value for key, value in data.items() if key != "logs"}

    await websocket.send_text(json.dumps({
        "type": "chat_start",
        "session_id": session_id,
        "intent": intent,
        "result": result,
        "logs": logs,
    }, ensure_ascii=False))

    if data and data.get("error"):
        answer = data["error"]
    else:
        if intent["type"] == "invalid_location":
            if intent.get("user_answer"):
                answer = intent["user_answer"]
            else:
                instructions, input_text, title, max_tokens = build_location_issue_stream_payload(message, intent, chat_history)
                answer = await stream_text_to_websocket(websocket, instructions, input_text, logs, title, max_tokens)
        elif intent["type"] == "chit_chat":
            instructions, input_text, title, max_tokens = build_chit_chat_stream_payload(message, chat_history)
            answer = await stream_text_to_websocket(websocket, instructions, input_text, logs, title, max_tokens)
        else:
            instructions, input_text, title, max_tokens = build_weather_stream_payload(message, intent, data, chat_history)
            answer = await stream_text_to_websocket(websocket, instructions, input_text, logs, title, max_tokens)

    if not answer:
        answer = "요청한 정보를 가져왔지만 답변 문장을 만들지 못했습니다."

    append_chat_history(chat_history, message, answer, intent, result)
    await websocket.send_text(json.dumps({
        "type": "chat_done",
        "session_id": session_id,
        "answer": answer,
        "intent": intent,
        "result": result,
        "logs": logs,
    }, ensure_ascii=False))

def clean_chat_answer(answer: str | None):
    if not answer:
        return None
    cleaned = re.sub(r"https?://\S+", "", answer)
    cleaned = re.sub(r"//\S+", "", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned

def looks_non_korean(text: str):
    korean_chars = len(re.findall(r"[가-힣]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    return latin_chars > korean_chars * 2

def compact_chat_result(data):
    excluded_keys = {"logs", "icon", "moon_illumination", "is_moon_up", "is_sun_up", "moon_status", "sun_status"}
    result = {}
    for key, value in data.items():
        if key in excluded_keys:
            continue
        if isinstance(value, str) and value.startswith(("http://", "https://", "//")):
            continue
        result[key] = value
    return result

def answer_weather_chat(message: str, session_id=None, chat_history=None):
    logs = []
    if not message.strip():
        return {
            "type": "chat",
            "session_id": session_id,
            "answer": "궁금한 지역과 날짜를 함께 물어봐 주세요. 예: 내일 서울 날씨 어때?",
            "logs": logs,
        }

    intent = validate_intent_location(classify_weather_chat(message, logs, chat_history), logs)
    if intent["type"] == "chit_chat":
        answer = build_chit_chat_answer(message, logs, chat_history)
        append_chat_history(chat_history, message, answer, intent)
        return {
            "type": "chat",
            "session_id": session_id,
            "answer": answer,
            "intent": intent,
            "logs": logs,
        }
    if intent["type"] == "invalid_location":
        answer = build_location_issue_answer(message, intent, logs, chat_history)
        append_chat_history(chat_history, message, answer, intent)
        return {
            "type": "chat",
            "session_id": session_id,
            "answer": answer,
            "intent": intent,
            "logs": logs,
        }

    if intent["type"] == "astronomy":
        data = get_astronomy(intent["location"], intent["date"])
    else:
        data = get_weather(intent["location"], intent["date"])
    if intent.get("resolved_location"):
        data["query"] = intent["resolved_location"]

    logs.extend(data.get("logs", []))
    answer = build_chat_answer(message, intent, data, logs, chat_history)
    result = {key: value for key, value in data.items() if key != "logs"}
    append_chat_history(chat_history, message, answer, intent, result)
    return {
        "type": "chat",
        "session_id": session_id,
        "answer": answer,
        "intent": intent,
        "result": result,
        "logs": logs,
    }
