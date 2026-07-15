import httpx
import pytest
import pytest_asyncio

from server import DEFAULT_DOCS_BASE_URL, SITEMAP_PATH


def _docs_reachable() -> bool:
    try:
        response = httpx.get(
            f"{DEFAULT_DOCS_BASE_URL}{SITEMAP_PATH}", timeout=5.0, follow_redirects=True
        )
    except httpx.HTTPError:
        return False
    return response.status_code == 200


@pytest_asyncio.fixture
async def docs_client():
    if not _docs_reachable():
        pytest.skip(f"docs site not reachable at {DEFAULT_DOCS_BASE_URL}")
    async with httpx.AsyncClient(
        base_url=DEFAULT_DOCS_BASE_URL, timeout=30, follow_redirects=True
    ) as client:
        yield client
