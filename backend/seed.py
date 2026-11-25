"""
放測試資料。執行前請先建表：alembic upgrade head
執行：python seed.py
"""
from datetime import datetime, timedelta, date
from sqlalchemy import select, func
from app.db import SessionLocal
from app import models as m

# 測試用資料
PERSONAS = [("小明", "student"), ("小華", "student"), ("小美", "worker"),
            ("阿傑", "worker"), ("小雨", "freelancer")]
TASK_TEMPLATES = [  # (標題, 類別, 優先級, 預估分鐘)
    ("寫報告", "study", 1, 90), ("讀英文", "study", 2, 45),
    ("小組討論", "class", 2, 60), ("社團活動", "social", 3, 90),
    ("打工", "work", 2, 180), ("運動", "other", 3, 60),
]


def main():
    with SessionLocal() as s:
        if s.scalar(select(func.count()).select_from(m.User)) > 0:
            print("資料庫已有使用者，略過 seed（要重來請刪除 itinerary.db 後重新 alembic upgrade head）")
            return

        base_day = datetime(2026, 11, 2, 9, 0)
        for name, persona in PERSONAS:
            u = m.User(name=name, persona=persona, preferences={"wake": "07:00", "sleep": "23:30"})
            s.add(u)
            s.flush()
            s.add(m.UserWeights(user_id=u.id, duration_multipliers={"study": 1.0}))

            tasks = []
            for title, cat, pri, mins in TASK_TEMPLATES:
                t = m.Task(user_id=u.id, title=title, category=cat, priority=pri, est_minutes=mins)
                s.add(t)
                tasks.append(t)
            s.flush()

            # 每個任務做 3 次紀錄：實際時間約為預估的 1.2～1.5 倍
            for t in tasks:
                for k in range(3):
                    start = base_day + timedelta(days=k, hours=2)
                    actual = int(t.est_minutes * (1.2 + 0.1 * k))
                    s.add(m.TaskLog(task_id=t.id, actual_start=start,
                                    actual_end=start + timedelta(minutes=actual), completed=True))

        # 為第一位使用者建立「第 1 版行程 → 事件 → 第 2 版行程 → 提案」的範例
        u1 = s.scalars(select(m.User).order_by(m.User.id)).first()
        t1, t2 = s.scalars(select(m.Task).where(m.Task.user_id == u1.id).order_by(m.Task.id).limit(2)).all()
        day = date(2026, 11, 4)
        v1 = m.Schedule(user_id=u1.id, schedule_date=day, version=1, reason="initial")
        s.add(v1)
        s.flush()
        s.add_all([
            m.ScheduleItem(schedule_id=v1.id, task_id=t1.id, position=1,
                           planned_start=datetime(2026, 11, 4, 16, 0), planned_end=datetime(2026, 11, 4, 17, 30)),
            m.ScheduleItem(schedule_id=v1.id, task_id=t2.id, position=2,
                           planned_start=datetime(2026, 11, 4, 18, 0), planned_end=datetime(2026, 11, 4, 18, 45)),
        ])
        ev = m.Event(user_id=u1.id, type="meeting_overrun", source="simulated", detail={"delay_minutes": 40})
        s.add(ev)
        s.flush()
        v2 = m.Schedule(user_id=u1.id, schedule_date=day, version=2, parent_id=v1.id, reason="replan", event_id=ev.id)
        s.add(v2)
        s.flush()
        s.add_all([
            m.ScheduleItem(schedule_id=v2.id, task_id=t1.id, position=1,
                           planned_start=datetime(2026, 11, 4, 16, 40), planned_end=datetime(2026, 11, 4, 18, 10)),
            m.ScheduleItem(schedule_id=v2.id, task_id=t2.id, position=2,
                           planned_start=datetime(2026, 11, 4, 18, 30), planned_end=datetime(2026, 11, 4, 19, 15)),
        ])
        s.add(m.ReplanProposal(event_id=ev.id, old_schedule_id=v1.id, new_schedule_id=v2.id,
                               change_score=0.2, explanation="討論延長 40 分鐘，後面行程順延。",
                               user_response="accepted"))
        s.commit()

        for table in (m.User, m.Task, m.TaskLog, m.Schedule, m.ScheduleItem, m.Event, m.ReplanProposal):
            print(table.__tablename__, s.scalar(select(func.count()).select_from(table)))


if __name__ == "__main__":
    main()
