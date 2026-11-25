"""
資料表定義（對應 ER 圖 v1，共 10 張表）
標記：【不可改】連接或個人化必用｜【先確認】要和組員確認｜【可改】自由調整
"""
from datetime import datetime, date, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime, Date, JSON, Float, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now_utc() -> datetime:
    """時間統一存 UTC，顯示時再轉台灣時區"""
    return datetime.now(timezone.utc)


# ---------------- 一、基本資料 ----------------

class User(Base):
    """使用者"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    name: Mapped[str] = mapped_column(String(50))                          # 【可改】
    persona: Mapped[str | None] = mapped_column(String(20), nullable=True) # 冷啟動預設類型 【可改】
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)          # 作息、通勤、勿擾時段 【可改】
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Taipei")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 軟刪除 【先確認】


class Place(Base):
    """常用地點"""
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))           # 【不可改】
    name: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Task(Base):
    """任務（排程器的輸入）"""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))           # 【不可改】
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id"), nullable=True)  # 【不可改】
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), default="other")     # 【先確認】類別清單
    priority: Mapped[int] = mapped_column(SmallInteger, default=2)         # 1高 2中 3低 【先確認】
    est_minutes: Mapped[int] = mapped_column(default=30)                   # 使用者預估時長 【先確認】
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)      # 【先確認】
    fixed_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # 固定時間 【先確認】
    locked: Mapped[bool] = mapped_column(default=False)                    # 【先確認】
    status: Mapped[str] = mapped_column(String(20), default="pending")     # 【先確認】
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)    # 軟刪除 【先確認】


class TaskLog(Base):
    """任務執行紀錄（個人化的主要資料來源）"""
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))           # 【不可改】可多筆
    actual_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 【不可改】
    actual_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)    # 【不可改】
    completed: Mapped[bool] = mapped_column(default=False)                 # 【不可改】
    postponed_count: Mapped[int] = mapped_column(default=0)                # 【先確認】


# ---------------- 二、突發事件 ----------------

class Event(Base):
    """突發事件（觸發重排的原因）"""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))           # 【不可改】
    type: Mapped[str] = mapped_column(String(30))                          # 事件種類 【先確認】
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="real")        # real / simulated 【先確認】
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


# ---------------- 三、行程版本 ----------------

class Schedule(Base):
    """行程版本（每次重排都新增一版，不覆蓋舊的）"""
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))           # 【不可改】
    schedule_date: Mapped[date] = mapped_column(Date)                      # 【先確認】
    version: Mapped[int] = mapped_column(default=1)                        # 【不可改】
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id"), nullable=True)  # 【不可改】
    reason: Mapped[str] = mapped_column(String(20), default="initial")     # initial / replan 【先確認】
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)      # 【不可改】
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ScheduleItem(Base):
    """行程中的每一格（排程器的輸出）"""
    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"))   # 【不可改】
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))           # 【不可改】
    planned_start: Mapped[datetime] = mapped_column(DateTime)              # 【先確認】
    planned_end: Mapped[datetime] = mapped_column(DateTime)                # 【先確認】
    position: Mapped[int] = mapped_column(default=0)                       # 當天順序 【先確認】
    travel_minutes: Mapped[int] = mapped_column(default=0)                 # 【先確認】


# ---------------- 四、重排提案 ----------------

class ReplanProposal(Base):
    """重排提案與使用者回應（偏好學習的資料來源）"""
    __tablename__ = "replan_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)                      # 【不可改】
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))         # 【不可改】
    old_schedule_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id"), nullable=True)  # 【不可改】
    new_schedule_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id"), nullable=True)  # 【不可改】
    change_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 變動量 【先確認】
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)   # LLM 說明 【可改】
    user_response: Mapped[str] = mapped_column(String(20), default="pending")  # 【不可改】值要固定
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------- 五、個人化參數 ----------------

class UserWeights(Base):
    """每位使用者的個人化參數（一人一筆）"""
    __tablename__ = "user_weights"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)  # 【不可改】
    alpha: Mapped[float] = mapped_column(Float, default=0.5)               # 重排變動量權重 【先確認】
    beta: Mapped[float] = mapped_column(Float, default=0.3)                # 通勤時間權重 【先確認】
    gamma: Mapped[float] = mapped_column(Float, default=0.2)               # 低效時段權重 【先確認】
    duration_multipliers: Mapped[dict] = mapped_column(JSON, default=dict) # 各類別時長係數 【可改】
    slot_scores: Mapped[dict] = mapped_column(JSON, default=dict)          # 各時段分數 【可改】
    sample_count: Mapped[int] = mapped_column(default=0)                   # 學習用了幾筆 【可改】
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


# ---------------- 六、其他 ----------------

class ApiCache(Base):
    """外部 API 結果暫存"""
    __tablename__ = "api_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(200), unique=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
