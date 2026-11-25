
import os
import json
import requests
import truststore

from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pprint import pprint


# ==========================================
# 1. 基本環境設定
# ==========================================

# 使用作業系統的 SSL 憑證
truststore.inject_into_ssl()

# 專案根目錄
BASE_DIR = Path(__file__).resolve().parent.parent

# 讀取專案根目錄的 .env
load_dotenv(BASE_DIR / ".env")

# 台灣時區 UTC+8
TAIWAN_TZ = timezone(timedelta(hours=8))

# 中央氣象署 API 網址
CWA_URL = (
    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/"
    "F-D0047-093"
)

# JSON 資料儲存位置
SAVE_DIR = BASE_DIR / "data" / "weather"


# ==========================================
# 2. 縣市與資料集編號對照表
# ==========================================

COUNTY_IDS = {
    "宜蘭縣": "F-D0047-001",
    "桃園市": "F-D0047-005",
    "新竹縣": "F-D0047-009",
    "苗栗縣": "F-D0047-013",
    "彰化縣": "F-D0047-017",
    "南投縣": "F-D0047-021",
    "雲林縣": "F-D0047-025",
    "嘉義縣": "F-D0047-029",
    "屏東縣": "F-D0047-033",
    "臺東縣": "F-D0047-037",
    "花蓮縣": "F-D0047-041",
    "澎湖縣": "F-D0047-045",
    "基隆市": "F-D0047-049",
    "新竹市": "F-D0047-053",
    "嘉義市": "F-D0047-057",
    "臺北市": "F-D0047-061",
    "高雄市": "F-D0047-065",
    "新北市": "F-D0047-069",
    "臺中市": "F-D0047-073",
    "臺南市": "F-D0047-077",
    "連江縣": "F-D0047-081",
    "金門縣": "F-D0047-085"
}


# ==========================================
# 3. 地區名稱正規化
# ==========================================

def normalize_name(name):
    return name.strip().replace("台", "臺")


# ==========================================
# 4. 取得 API Key
# ==========================================

def get_api_key():

    api_key = os.getenv("CWA_API_KEY")

    if not api_key:
        raise RuntimeError(
            "找不到 CWA_API_KEY，請確認專案根目錄的 .env"
        )

    return api_key


# ==========================================
# 5. 時間格式轉換
# ==========================================

def parse_datetime(value):

    if isinstance(value, datetime):
        dt = value

    elif isinstance(value, str):
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    else:
        raise ValueError("時間必須為字串或 datetime")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TAIWAN_TZ)

    return dt.astimezone(TAIWAN_TZ)


# ==========================================
# 6. 降雨風險初步判斷
# ==========================================

def analyze_rain(description):

    # 注意：這是文字規則判斷，
    # 並非中央氣象署提供的正式風險等級。

    high_risk = [
        "豪雨",
        "大雨",
        "雷雨",
        "雷陣雨"
    ]

    medium_risk = [
        "陣雨",
        "短暫雨",
        "小雨",
        "有雨",
        "降雨"
    ]

    if any(word in description for word in high_risk):
        return "HIGH"

    if any(word in description for word in medium_risk):
        return "MEDIUM"

    return "UNKNOWN"


# ==========================================
# 7. 向中央氣象署發送 API 請求
# ==========================================

def fetch_weather(county_name, district_name):

    county_name = normalize_name(county_name)
    district_name = normalize_name(district_name)

    if county_name not in COUNTY_IDS:
        raise ValueError(
            f"不支援的縣市：{county_name}"
        )

    if not district_name:
        raise ValueError("行政區名稱不可為空")

    params = {
        "Authorization": get_api_key(),
        "format": "JSON",
        "locationId": COUNTY_IDS[county_name],
        "LocationName": district_name,
        "ElementName": "天氣預報綜合描述",
        "sort": "time"
    }

    try:

        response = requests.get(
            CWA_URL,
            params=params,
            timeout=(10, 60)
        )

        response.raise_for_status()

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "中央氣象署 API 查詢逾時"
        ) from None

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "無法連線至中央氣象署 API"
        ) from None

    except requests.exceptions.HTTPError:
        raise RuntimeError(
            f"中央氣象署 HTTP 錯誤："
            f"{response.status_code}"
        ) from None

    except requests.exceptions.RequestException:
        raise RuntimeError(
            "中央氣象署 API 請求失敗"
        ) from None

    try:
        data = response.json()

    except ValueError:
        raise RuntimeError(
            "中央氣象署回傳的資料不是有效 JSON"
        ) from None

    if str(data.get("success")).lower() != "true":
        raise RuntimeError(
            "中央氣象署 API 回傳失敗"
        )

    return data


# ==========================================
# 8. 解析天氣預報資料
# ==========================================

def parse_weather(data, county_name, district_name):

    county_name = normalize_name(county_name)
    district_name = normalize_name(district_name)

    forecasts = []

    counties = data.get("records", {}).get(
        "Locations", []
    )

    for county in counties:

        current_county = normalize_name(
            county.get("LocationsName", "")
        )

        if current_county != county_name:
            continue

        for location in county.get("Location", []):

            current_district = normalize_name(
                location.get("LocationName", "")
            )

            if current_district != district_name:
                continue

            for element in location.get(
                "WeatherElement", []
            ):

                if element.get("ElementName") != \
                        "天氣預報綜合描述":
                    continue

                for time_data in element.get("Time", []):

                    values = time_data.get(
                        "ElementValue", []
                    )

                    if not values:
                        continue

                    start_time = time_data.get("StartTime")
                    end_time = time_data.get("EndTime")

                    if not start_time or not end_time:
                        continue

                    description = values[0].get(
                        "WeatherDescription",
                        "未提供"
                    )

                    forecasts.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "description": description,
                        "rain_risk": analyze_rain(description)
                    })

    if not forecasts:
        raise LookupError(
            f"查無 {county_name}{district_name} 的天氣預報"
        )

    forecasts.sort(
        key=lambda item: parse_datetime(item["start_time"])
    )

    return {
        "source": "CWA",
        "county": county_name,
        "district": district_name,
        "timezone": "Asia/Taipei",
        "query_time": datetime.now(TAIWAN_TZ).isoformat(),
        "forecast_count": len(forecasts),
        "forecasts": forecasts
    }


# ==========================================
# 9. 儲存 JSON 資料
# ==========================================

def save_weather_json(data, county_name, district_name):

    SAVE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    file_name = (
        f"weather_{county_name}_{district_name}.json"
    )

    file_path = SAVE_DIR / file_name

    with open(file_path, "w", encoding="utf-8") as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    return str(file_path)


# ==========================================
# 10. 主要天氣查詢函式
# ==========================================

def get_weather(
    county_name,
    district_name,
    save_json=False
):

    county_name = normalize_name(county_name)
    district_name = normalize_name(district_name)

    # 取得原始 API 資料
    raw_data = fetch_weather(
        county_name,
        district_name
    )

    # 解析成統一格式
    result = parse_weather(
        raw_data,
        county_name,
        district_name
    )

    # 選擇是否儲存 JSON
    if save_json:

        result["saved_path"] = save_weather_json(
            raw_data,
            county_name,
            district_name
        )

    return result


# ==========================================
# 11. 從預報結果查詢指定時間的天氣
# ==========================================

def find_weather_at_time(weather_data, target_time):

    target_time = parse_datetime(target_time)

    for forecast in weather_data.get("forecasts", []):

        start_time = parse_datetime(
            forecast["start_time"]
        )

        end_time = parse_datetime(
            forecast["end_time"]
        )

        if start_time <= target_time < end_time:

            return {
                "source": weather_data["source"],
                "county": weather_data["county"],
                "district": weather_data["district"],
                "target_time": target_time.isoformat(),
                **forecast
            }

    raise LookupError(
        "指定時間不在目前的天氣預報範圍內"
    )


# ==========================================
# 12. 查詢指定時間的天氣
# ==========================================

def get_weather_at_time(
    county_name,
    district_name,
    target_time
):

    weather_data = get_weather(
        county_name,
        district_name
    )

    return find_weather_at_time(
        weather_data,
        target_time
    )


# ==========================================
# 13. 查詢目前時段的天氣預報
# ==========================================

def get_current_weather(county_name, district_name):

    return get_weather_at_time(
        county_name,
        district_name,
        datetime.now(TAIWAN_TZ)
    )


# ==========================================
# 14. 顯示天氣預報
# ==========================================

def display_weather(weather_data):

    print("\n========== 天氣預報 ==========\n")

    print("資料來源：", weather_data["source"])
    print("縣市：", weather_data["county"])
    print("行政區：", weather_data["district"])
    print("查詢時間：", weather_data["query_time"])
    print("預報筆數：", weather_data["forecast_count"])

    for forecast in weather_data["forecasts"]:

        print("\n----------------------------")
        print("開始時間：", forecast["start_time"])
        print("結束時間：", forecast["end_time"])
        print("天氣：", forecast["description"])
        print("降雨風險：", forecast["rain_risk"])

    if "saved_path" in weather_data:
        print("\nJSON 儲存位置：")
        print(weather_data["saved_path"])

    print("\n所有天氣資料顯示完成！")


# ==========================================
# 15. 獨立執行測試
# ==========================================

if __name__ == "__main__":

    print("\n========== 天氣預報查詢系統 ==========")

    print("\n可查詢縣市：")
    print("、".join(COUNTY_IDS.keys()))

    county_name = input(
        "\n請輸入縣市："
    ).strip()

    district_name = input(
        "請輸入行政區："
    ).strip()

    try:

        weather = get_weather(
            county_name,
            district_name,
            save_json=True
        )

        display_weather(weather)

        print("\n========== 目前時段預報 ==========\n")

        try:

            current_weather = find_weather_at_time(
                weather,
                datetime.now(TAIWAN_TZ)
            )

            pprint(
                current_weather,
                sort_dicts=False
            )

        except LookupError as error:
            print(error)

    except (ValueError, RuntimeError, LookupError) as error:

        print("\n查詢失敗：", error)
