import asyncio

import httpx

from app.main import app


def test_landing_and_unknown_page_flow():
    asyncio.run(_test_landing_and_unknown_page_flow())


async def _test_landing_and_unknown_page_flow():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        landing = await client.get("/", follow_redirects=False)
        unknown = await client.get("/anything-else", follow_redirects=False)
        login = await client.get("/login", follow_redirects=False)
        api_unknown = await client.get("/api/anything-else", follow_redirects=False)

    assert landing.status_code == 200
    assert "SynapseMed" in landing.text
    assert 'href="/login"' in landing.text
    for agent_name in (
        "Report Analysis Agent",
        "Guideline RAG",
        "Risk Router",
        "Summary Agent",
        "Recommendation Agent",
        "Clinical Reconciliation Agent",
        "Reviewer Feedback Loop",
    ):
        assert agent_name in landing.text
    assert "Start with a secure workspace for the records already waiting on your team." in landing.text
    assert unknown.status_code == 303
    assert unknown.headers["location"] == "/login"
    assert login.status_code == 200
    assert "Sign in" in login.text
    assert api_unknown.status_code == 404
