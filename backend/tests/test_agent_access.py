import pytest
from fastapi import HTTPException

from app.models.thread import Thread, ThreadType
from app.models.user import Plan, User
from app.services.agent.access import ensure_search_thread, require_agent_eligible


def _user(*, plan: Plan = Plan.FREE, max_user_id: int | None = None) -> User:
    user = User(email="u@test.com", plan=plan)
    user.max_user_id = max_user_id
    return user


def test_require_agent_eligible_pro_without_max_allowed_for_entry():
    require_agent_eligible(_user(plan=Plan.PRO, max_user_id=None))


def test_require_agent_eligible_pro_max():
    require_agent_eligible(_user(plan=Plan.PRO, max_user_id=123), require_max=True)


def test_require_agent_eligible_rejects_without_max_when_required():
    with pytest.raises(HTTPException) as exc:
        require_agent_eligible(_user(plan=Plan.PRO, max_user_id=None), require_max=True)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "agent_max_required"


def test_require_agent_eligible_rejects_free():
    with pytest.raises(HTTPException) as exc:
        require_agent_eligible(_user(plan=Plan.FREE, max_user_id=1))
    assert exc.value.detail["code"] == "agent_pro_required"


def test_ensure_search_thread_rejects_agent():
    thread = Thread(user_id=_user().id, title="Агент 1", thread_type=ThreadType.AGENT)
    with pytest.raises(HTTPException) as exc:
        ensure_search_thread(thread)
    assert exc.value.detail["code"] == "wrong_thread_type"
