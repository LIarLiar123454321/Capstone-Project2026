from sqlalchemy import select
from app.db import engine, SessionLocal, Base
from app import models

Base.metadata.create_all(engine)

with SessionLocal() as s:
    u = models.User(name="測試使用者", preferences={"wake": "07:00"})
    s.add(u)
    s.flush()
    s.add(models.Task(user_id=u.id, title="寫報告", category="study",
                      priority=1, est_minutes=90))
    s.commit()
    for t in s.scalars(select(models.Task)):
        print(t.id, t.title, t.priority)