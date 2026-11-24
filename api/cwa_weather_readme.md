終端呼叫:
python api/cwa_weather.py

程式碼呼叫
所有:
from api.cwa_weather import get_weather
weather = get_weather("新北市", "淡水區")
print(weather)

當前時段:
from api.cwa_weather import get_current_weather

weather = get_current_weather("新北市", "淡水區")

print(weather)

指定時間:
from api.cwa_weather import get_weather_at_time

weather = get_weather_at_time(
    "新北市",
    "淡水區",
    "2026-11-24 14:30:00"
)

print(weather)

下載json:
from api.cwa_weather import get_weather

weather = get_weather(
    "新北市",
    "淡水區",
    save_json=True
)

print(weather["saved_path"])