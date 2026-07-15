from server import DEFAULT_DOCS_BASE_URL, catalog, render_page


async def test_catalog_lists_known_sections(docs_client):
    entries = await catalog(docs_client)
    sections = {e["section"] for e in entries}
    # Stable top-level sections of the Teamscale docs.
    assert {"introduction", "howto", "reference"} <= sections
    assert len(entries) > 100


async def test_section_filter_narrows(docs_client):
    entries = await catalog(docs_client, section="introduction")
    assert entries
    assert all(e["section"] == "introduction" for e in entries)


async def test_get_page_returns_markdown(docs_client):
    intro = await catalog(docs_client, section="introduction")
    page = await render_page(docs_client, intro[0]["path"], DEFAULT_DOCS_BASE_URL)
    assert page.startswith("#")                    # titled
    assert f"<{DEFAULT_DOCS_BASE_URL}" in page      # canonical URL
    assert len(page) > 200                          # non-trivial content
