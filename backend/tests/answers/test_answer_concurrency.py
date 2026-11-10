"""Concurrency proof: an /answer request waiting on the LLM holds no threadpool token.

With one token in the threadpool, a request that held a thread while waiting on the
LLM would block the other request's auth dependency, the barrier would never fill,
and ``fail_after`` would fire.
"""

from collections.abc import Iterator

import anyio
import httpx
import pytest
from sqlalchemy.orm import Session

from app.answers.dependencies import get_app_llm_provider
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.identity.service import RegistrationResult, register_user
from app.main import app
from app.providers.base import ChatMessage, RouteDecision
from tests.fakes import RecordingLLMProvider


class _BarrierLLMProvider(RecordingLLMProvider):
    """Provider whose route call waits until every request in flight has arrived."""

    def __init__(self, *, parties: int) -> None:
        """Open the arrival counter and the barrier event.

        :param parties: Number of route calls that must arrive before any returns.
        """

        super().__init__(answer="direct answer")
        self._parties = parties
        self._arrived = 0
        self._all_arrived = anyio.Event()

    async def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Count this arrival and wait until every party has arrived.

        :param system: System prompt the router call carries.
        :param messages: Message list the router call carries.
        """

        self._arrived += 1
        if self._arrived == self._parties:
            self._all_arrived.set()
        await self._all_arrived.wait()
        return RouteDecision(route="direct", rewritten_query=None)


async def _ask(*, http: httpx.AsyncClient, project_id: str, token: str, statuses: list[int]) -> None:
    """POST one question and record the status code it came back with.

    :param http: Client already pointed at the app under test.
    :param project_id: Project the question is asked against.
    :param token: Bearer token identifying the asking user.
    :param statuses: List this call appends its status code to.
    """

    response = await http.post(
        f"/api/projects/{project_id}/answer",
        json={"query": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    statuses.append(response.status_code)


async def _ask_with(*, http: httpx.AsyncClient, owner: RegistrationResult, statuses: list[int]) -> None:
    """POST one owner's question and record its status code.

    :param http: Client already pointed at the app under test.
    :param owner: Registered owner whose project is asked against.
    :param statuses: List this call appends its status code to.
    """

    await _ask(
        http=http,
        project_id=str(owner.project.id),
        token=create_access_token(user_id=owner.user.id, settings=get_settings()),
        statuses=statuses,
    )


@pytest.mark.anyio
async def test_waiting_llm_calls_hold_no_threadpool_token(*, db_session: Session) -> None:
    """Check that two answers can both wait on the LLM while the threadpool has one token.

    :param db_session: Transaction-managed session the seed rows are written through.
    """

    owners = [
        register_user(db=db_session, email=f"conc-{index}@example.com", password="password123")
        for index in (1, 2)
    ]

    # One instance for both requests: a per-request provider would give each its
    # own barrier and they could never meet.
    provider = _BarrierLLMProvider(parties=2)

    def override_get_db() -> Iterator[Session]:
        """Serve the shared transaction-managed session instead of a fresh one."""

        yield db_session

    async def override_provider() -> _BarrierLLMProvider:
        """Serve the barrier provider so both requests wait inside it."""

        return provider

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_app_llm_provider] = override_provider
    limiter = anyio.to_thread.current_default_thread_limiter()
    original_tokens = limiter.total_tokens
    limiter.total_tokens = 1

    async def ask(owner: RegistrationResult) -> None:  # noqa: PLR0917
        """Ask this owner's question and record the status code it returns.

        :param owner: Registered owner whose project is asked against.
        """

        await _ask_with(http=http, owner=owner, statuses=statuses)

    statuses: list[int] = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            with anyio.fail_after(5):
                async with anyio.create_task_group() as group:
                    for owner in owners:
                        group.start_soon(ask, owner)
    finally:
        limiter.total_tokens = original_tokens
        app.dependency_overrides.clear()
    assert statuses == [200, 200]
