
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = ",".join((
    "routes.duration", "routes.distanceMeters",
    "routes.legs.steps.travelMode", "routes.legs.steps.staticDuration",
    "routes.legs.steps.distanceMeters", "routes.legs.steps.navigationInstruction",
    "routes.legs.steps.transitDetails",
))
UTC = timezone.utc
MODES = {"TRANSIT", "DRIVE", "WALK", "BICYCLE", "TWO_WHEELER"}
TRANSIT_MODES = {"BUS", "SUBWAY", "TRAIN", "LIGHT_RAIL", "RAIL"}


class GoogleRoutesError(RuntimeError):
    """連線、API 或回應格式錯誤；不包含 API key 或原始請求。"""


class GoogleRoutesAPIError(GoogleRoutesError):
    def __init__(self, status_code: int, api_status: str = "UNKNOWN"):
        self.status_code = status_code
        self.api_status = api_status
        hints = {400: "請檢查參數與 FieldMask", 401: "請檢查 API key",
                 403: "請檢查 API 啟用、帳單與金鑰限制",
                 429: "配額或速率限制，請稍後再試"}
        super().__init__(f"Google Routes API HTTP {status_code} ({api_status})；"
                         f"{hints.get(status_code, '服務暫時異常，請稍後再試')}")


def aware_datetime(value: datetime | str, name: str = "time") -> datetime:
    """接受 aware datetime 或含 Z/UTC offset 的 ISO 字串；不猜測時區。"""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} 必須是 ISO 8601 日期時間") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 必須包含時區，例如 2026-11-21T10:00:00+08:00")
    return value.astimezone(UTC)


def _seconds(value: Any) -> float:
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,9})?s", value):
        raise GoogleRoutesError("API 回應含無效的 duration")
    result = float(value[:-1])
    if not math.isfinite(result):
        raise GoogleRoutesError("API duration 超出範圍")
    return result


def seconds_to_minutes(duration: str | None) -> float:
    return round(_seconds(duration or "0s") / 60, 1)


def _meters(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoogleRoutesError("API 回應含無效的 distanceMeters")
    return value


def _object(value: Any) -> dict:
    if not isinstance(value, dict):
        raise GoogleRoutesError("API 回應物件格式錯誤")
    return value


def _array(value: Any) -> list:
    if not isinstance(value, list):
        raise GoogleRoutesError("API 回應陣列格式錯誤")
    return value


def _stamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return aware_datetime(value, "API timestamp")
    except (ValueError, TypeError) as exc:
        raise GoogleRoutesError("API 回應含無效的 timestamp") from exc


def _iso(value: datetime | None, zone: ZoneInfo) -> str | None:
    return value.astimezone(zone).isoformat() if value is not None else None


def parse_route(route: dict, origin: str, destination: str, travel_mode: str,
                *, departure_time: datetime | str | None = None,
                arrival_time: datetime | str | None = None,
                buffer_minutes: float = 0, output_timezone: str = "Asia/Taipei",
                now: datetime | None = None) -> dict:
    """純解析函式，無網路。arrival_time 是原始期限，緩衝由 get_routes 送入 API。

    大眾運輸出發 = 第一班發車時間 − 前置步行；抵達 = 最後班到站 + 後置步行。
    缺少端點班次或步行時間時，不產生看似精確的出門建議。
    """
    route = _object(route)
    zone = ZoneInfo(output_timezone)
    now = aware_datetime(now if now is not None else datetime.now(UTC))
    dep = aware_datetime(departure_time) if departure_time is not None else None
    arr = aware_datetime(arrival_time) if arrival_time is not None else None
    if dep is not None and arr is not None:
        raise ValueError("departure_time 與 arrival_time 只能擇一")
    buffer = _nonnegative(buffer_minutes, "buffer_minutes")
    duration = _seconds(route["duration"]) if "duration" in route else None
    distance = _meters(route.get("distanceMeters", 0))
    warnings: list[str] = []
    if duration is None:
        warnings.append("MISSING_ROUTE_DURATION")
    steps = []
    raw_seconds: list[float | None] = []
    transit_indices: list[int] = []
    transit_times: dict[int, tuple[datetime | None, datetime | None]] = {}
    walk_seconds = 0.0
    walk_complete = True
    walk_distance = 0
    modes: set[str] = set()
    for leg in _array(route.get("legs", [])):
        for raw in _array(_object(leg).get("steps", [])):
            raw = _object(raw)
            mode = raw.get("travelMode", "UNKNOWN")
            if not isinstance(mode, str):
                raise GoogleRoutesError("API travelMode 格式錯誤")
            modes.add(mode)
            secs = _seconds(raw["staticDuration"]) if "staticDuration" in raw else None
            meters = _meters(raw.get("distanceMeters", 0))
            index = len(steps)
            raw_seconds.append(secs)
            item = {"mode": mode, "duration_seconds": secs,
                    "duration_minutes": round(secs / 60, 1) if secs is not None else None,
                    "distance_m": meters,
                    "instructions": _object(raw.get("navigationInstruction", {})).get("instructions")}
            if mode == "WALK":
                walk_distance += meters
                walk_complete &= secs is not None
                walk_seconds += secs or 0
                if meters > 0 and secs is not None and (secs == 0 or meters / secs > 3):
                    warnings.append(f"WALK_SPEED_ANOMALY:step={index + 1}")
            if secs is None:
                warnings.append(f"MISSING_STEP_DURATION:step={index + 1}")
            if mode == "TRANSIT":
                transit_indices.append(index)
                details = _object(raw.get("transitDetails", {}))
                stop = _object(details.get("stopDetails", {}))
                line = _object(details.get("transitLine", {}))
                start = _stamp(stop.get("departureTime"))
                end = _stamp(stop.get("arrivalTime"))
                transit_times[index] = (start, end)
                if start is not None and end is not None and end < start:
                    raise GoogleRoutesError("API 班次抵達時間早於出發時間")
                item.update({
                    "line_name": line.get("nameShort") or line.get("name") or "未知路線",
                    "vehicle": _object(line.get("vehicle", {})).get("type", "UNKNOWN"),
                    "departure_stop": _object(stop.get("departureStop", {})).get("name", "未知站點"),
                    "arrival_stop": _object(stop.get("arrivalStop", {})).get("name", "未知站點"),
                    "stop_count": details.get("stopCount", 0),
                    "headsign": details.get("headsign"),
                    "departure_time": _iso(start, zone), "arrival_time": _iso(end, zone),
                })
            steps.append(item)

    start_time = end_time = None
    basis = "unavailable"
    if transit_indices:
        first, last = transit_indices[0], transit_indices[-1]
        prefix, suffix = raw_seconds[:first], raw_seconds[last + 1:]
        first_dep = transit_times[first][0]
        last_arr = transit_times[last][1]
        if first_dep is not None and all(x is not None for x in prefix):
            start_time = first_dep - timedelta(seconds=sum(x for x in prefix if x is not None))
        if last_arr is not None and all(x is not None for x in suffix):
            end_time = last_arr + timedelta(seconds=sum(x for x in suffix if x is not None))
        basis = "transit_schedule_and_access_steps"
        if start_time is None or end_time is None:
            warnings.append("INCOMPLETE_TRANSIT_TIMING")
    elif duration is not None:
        if arr is not None:
            end_time = arr - timedelta(minutes=buffer)
            start_time = end_time - timedelta(seconds=duration)
        else:
            start_time = dep if dep is not None else now
            end_time = start_time + timedelta(seconds=duration)
        basis = "route_duration_estimate"
    if not steps:
        warnings.append("MISSING_STEPS")
        start_time = end_time = None
        basis = "unavailable"
    recommended = start_time
    # 抵達查詢已把緩衝用於提早抵達，這裡不再扣一次。
    if recommended is not None and arr is None:
        recommended -= timedelta(minutes=buffer)
    if start_time is not None and end_time is not None and end_time < start_time:
        raise GoogleRoutesError("API 路線抵達時間早於出發時間")
    if arr is not None and end_time is not None and end_time > arr - timedelta(minutes=buffer):
        warnings.append("ARRIVAL_BUFFER_NOT_MET")
    if dep is not None and start_time is not None and start_time < dep:
        warnings.append("ROUTE_STARTS_BEFORE_REQUESTED_DEPARTURE")
    if recommended is not None and recommended < now:
        warnings.append("RECOMMENDED_DEPARTURE_IN_PAST")
    count = len(transit_indices)
    return {
        "origin": origin, "destination": destination, "travel_mode": travel_mode,
        "duration_seconds": duration,
        "duration_minutes": round(duration / 60, 1) if duration is not None else None,
        "distance_km": round(distance / 1000, 2), "steps": steps,
        "transfer_count": max(0, count - 1), "transit_segment_count": count,
        "walking_distance_m": walk_distance,
        "walking_seconds": walk_seconds if walk_complete else None,
        "walking_minutes": round(walk_seconds / 60, 1) if walk_complete else None,
        "actual_modes": sorted(modes), "uses_transit": count > 0,
        "requested_departure_time": _iso(dep, zone),
        "requested_arrival_time": _iso(arr, zone),
        "effective_arrival_time": _iso(arr - timedelta(minutes=buffer), zone) if arr is not None else None,
        "estimated_departure_time": _iso(start_time, zone),
        "estimated_arrival_time": _iso(end_time, zone),
        "recommended_departure_time": _iso(recommended, zone),
        "buffer_minutes": buffer,
        "buffer_policy": "arrive_early" if arr is not None else "leave_early",
        "time_basis": basis, "timezone": output_timezone,
        "warnings": warnings,
    }


def _nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} 必須是有限的非負數字")
    return float(value)


def get_routes(origin: str, destination: str, travel_mode: str = "TRANSIT", *,
               departure_time: datetime | str | None = None,
               arrival_time: datetime | str | None = None,
               buffer_minutes: float = 10, output_timezone: str = "Asia/Taipei",
               compute_alternative_routes: bool = True,
               transit_routing_preference: str | None = None,
               allowed_transit_modes: list[str] | None = None,
               api_key: str | None = None, timeout: float = 20,
               session: Any = None) -> list[dict]:
    """查詢所有候選路線；沒有路線回傳 []，操作失敗則拋 GoogleRoutesError。

    buffer_minutes：抵達模式會提早 API 的抵達期限；其他模式只提早出門建議。
    session 可注入具有 post() 的 requests.Session 或測試替身。無自動重試。
    """
    for name, address in (("origin", origin), ("destination", destination)):
        if not isinstance(address, str) or not address.strip():
            raise ValueError(f"{name} 必須是非空地址字串")
    if not isinstance(travel_mode, str) or travel_mode.upper() not in MODES:
        raise ValueError(f"travel_mode 必須是 {sorted(MODES)}")
    mode = travel_mode.upper()
    buffer = _nonnegative(buffer_minutes, "buffer_minutes")
    timeout = _nonnegative(timeout, "timeout")
    if timeout == 0:
        raise ValueError("timeout 必須大於 0")
    if not isinstance(compute_alternative_routes, bool):
        raise ValueError("compute_alternative_routes 必須是 bool")
    ZoneInfo(output_timezone)  # 請求前檢查，Windows 請安裝 tzdata。
    now = datetime.now(UTC)
    dep = aware_datetime(departure_time, "departure_time") if departure_time is not None else None
    arr = aware_datetime(arrival_time, "arrival_time") if arrival_time is not None else None
    if dep is not None and arr is not None:
        raise ValueError("departure_time 與 arrival_time 只能擇一")
    if arr is not None and mode != "TRANSIT":
        raise ValueError("arrival_time 僅支援 TRANSIT")
    effective_arr = arr - timedelta(minutes=buffer) if arr is not None else None
    if mode == "TRANSIT":
        for value in (dep, arr, effective_arr):
            if value is not None and not now - timedelta(days=7) <= value <= now + timedelta(days=100):
                raise ValueError("TRANSIT 時間（含扣除緩衝後）須在現在前 7 天至後 100 天內")
    elif dep is not None and dep < now:
        raise ValueError("非 TRANSIT 不可指定過去的 departure_time")
    if mode != "TRANSIT" and (transit_routing_preference is not None or allowed_transit_modes is not None):
        raise ValueError("大眾運輸偏好僅支援 TRANSIT")
    prefs = {}
    if transit_routing_preference is not None:
        if transit_routing_preference not in {"LESS_WALKING", "FEWER_TRANSFERS"}:
            raise ValueError("transit_routing_preference 須為 LESS_WALKING 或 FEWER_TRANSFERS")
        prefs["routingPreference"] = transit_routing_preference
    if allowed_transit_modes is not None:
        if (not isinstance(allowed_transit_modes, list) or not allowed_transit_modes
                or any(not isinstance(x, str) or x not in TRANSIT_MODES for x in allowed_transit_modes)):
            raise ValueError(f"allowed_transit_modes 須為非空清單，值限 {sorted(TRANSIT_MODES)}")
        prefs["allowedTravelModes"] = list(dict.fromkeys(allowed_transit_modes))
    key = api_key if api_key is not None else os.getenv("GOOGLE_MAPS_API_KEY")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("找不到 GOOGLE_MAPS_API_KEY，請設定環境變數或傳入 api_key")
    body: dict[str, Any] = {
        "origin": {"address": origin}, "destination": {"address": destination},
        "travelMode": mode, "languageCode": "zh-TW", "regionCode": "tw",
        "units": "METRIC", "computeAlternativeRoutes": compute_alternative_routes,
    }
    if effective_arr is not None:
        body["arrivalTime"] = effective_arr.isoformat().replace("+00:00", "Z")
    else:
        # 固定本次查詢基準；避免依賴伺服器現在時間造成估算與請求不一致。
        body["departureTime"] = (dep if dep is not None else now).isoformat().replace("+00:00", "Z")
    if mode in {"DRIVE", "TWO_WHEELER"}:
        body["routingPreference"] = "TRAFFIC_AWARE"
    if prefs:
        body["transitPreferences"] = prefs
    transport = session if session is not None else requests
    try:
        response = transport.post(ROUTES_URL, json=body, timeout=timeout, headers={
            "Content-Type": "application/json", "X-Goog-Api-Key": key.strip(),
            "X-Goog-FieldMask": FIELD_MASK,
        })
    except requests.exceptions.Timeout:
        raise GoogleRoutesError("Google Routes API 查詢逾時") from None
    except requests.exceptions.RequestException:
        raise GoogleRoutesError("Google Routes API 連線失敗") from None
    if not 200 <= response.status_code < 300:
        status = "UNKNOWN"
        try:
            candidate = response.json().get("error", {}).get("status", "UNKNOWN")
            if isinstance(candidate, str) and re.fullmatch(r"[A-Z_]{1,64}", candidate):
                status = candidate
        except (ValueError, AttributeError, TypeError):
            pass
        raise GoogleRoutesAPIError(response.status_code, status)
    try:
        data = _object(response.json())
    except ValueError:
        raise GoogleRoutesError("Google Routes API 回傳非 JSON 資料") from None
    if "error" in data:
        raise GoogleRoutesError("Google Routes API 回傳錯誤物件")
    return [parse_route(route, origin, destination, mode, departure_time=dep,
                        arrival_time=arr, buffer_minutes=buffer,
                        output_timezone=output_timezone, now=now)
            for route in _array(data.get("routes", []))]


def get_route(origin: str, destination: str, travel_mode: str = "TRANSIT", **kwargs: Any) -> dict:
    """保留舊版行為：第一條建議路線；無路線回傳 error dict。"""
    routes = get_routes(origin, destination, travel_mode, **kwargs)
    return routes[0] if routes else {"error": "找不到可用路線"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="台灣新北市淡江大學")
    parser.add_argument("--destination", default="台灣台北市台北車站")
    parser.add_argument("--mode", choices=sorted(MODES), default="TRANSIT")
    times = parser.add_mutually_exclusive_group()
    times.add_argument("--departure-time")
    times.add_argument("--arrival-time")
    parser.add_argument("--buffer-minutes", type=float, default=10)
    parser.add_argument("--timezone", default="Asia/Taipei")
    parser.add_argument("--env-file", help="明確指定 .env 路徑；未指定時由 python-dotenv 尋找")
    parser.add_argument("--preference", choices=["LESS_WALKING", "FEWER_TRANSFERS"])
    parser.add_argument("--transit-modes", nargs="+", choices=sorted(TRANSIT_MODES))
    parser.add_argument("--no-alternatives", action="store_true")
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=args.env_file, override=False)
        routes = get_routes(args.origin, args.destination, args.mode,
                            departure_time=args.departure_time, arrival_time=args.arrival_time,
                            buffer_minutes=args.buffer_minutes, output_timezone=args.timezone,
                            compute_alternative_routes=not args.no_alternatives,
                            transit_routing_preference=args.preference,
                            allowed_transit_modes=args.transit_modes)
        print(json.dumps(routes, ensure_ascii=False, indent=2))
        return 0 if routes else 2
    except (GoogleRoutesError, ValueError, KeyError, OverflowError) as exc:
        print(f"查詢失敗：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
