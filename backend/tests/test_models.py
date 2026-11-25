import pytest
from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app import models as m


def make_user(s, name="測試"):
    u = m.User(name=name)
    s.add(u)
    s.flush()
    return u


def test_create_user_and_task(session):
    u = make_user(session)
    t = m.Task(user_id=u.id, title="寫報告", category="study", priority=1, est_minutes=90)
    session.add(t)
    session.commit()
    got = session.scalars(select(m.Task)).one()
    assert got.title == "寫報告" and got.user_id == u.id
    assert got.locked is False and got.status == "pending"


def test_foreign_key_is_enforced(session):
    session.add(m.Task(user_id=999, title="孤兒任務"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_task_can_have_multiple_logs(session):
    u = make_user(session)
    t = m.Task(user_id=u.id, title="讀英文")
    session.add(t)
    session.flush()
    session.add_all([m.TaskLog(task_id=t.id), m.TaskLog(task_id=t.id, completed=True)])
    session.commit()
    logs = session.scalars(select(m.TaskLog).where(m.TaskLog.task_id == t.id)).all()
    assert len(logs) == 2


def test_schedule_version_chain(session):
    u = make_user(session)
    v1 = m.Schedule(user_id=u.id, schedule_date=date(2026, 11, 4), version=1)
    session.add(v1)
    session.flush()
    v2 = m.Schedule(user_id=u.id, schedule_date=date(2026, 11, 4), version=2,
                    parent_id=v1.id, reason="replan")
    session.add(v2)
    session.commit()
    assert session.get(m.Schedule, v2.id).parent_id == v1.id


def test_one_weights_row_per_user(session):
    u = make_user(session)
    session.add(m.UserWeights(user_id=u.id))
    session.commit()
    session.add(m.UserWeights(user_id=u.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_soft_delete_filter(session):
    from datetime import datetime
    u = make_user(session)
    session.add_all([m.Task(user_id=u.id, title="保留"),
                     m.Task(user_id=u.id, title="已刪除", deleted_at=datetime(2026, 11, 1))])
    session.commit()
    alive = session.scalars(select(m.Task).where(m.Task.deleted_at.is_(None))).all()
    assert [t.title for t in alive] == ["保留"]
