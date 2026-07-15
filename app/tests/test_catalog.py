import httpx

from server import catalog, fetch_sitemap_urls, parse_catalog

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://docs.teamscale.com/introduction/agile-requirements-tracing/</loc></url>
  <url><loc>https://docs.teamscale.com/howto/setup/pre-commit-analysis/</loc></url>
  <url><loc>https://docs.teamscale.com/reference/rest-api/</loc></url>
</urlset>
"""


def _client():
    def handler(request):
        assert request.url.path == "/sitemap.xml"
        return httpx.Response(200, text=SITEMAP)
    return httpx.AsyncClient(
        base_url="https://docs.teamscale.com",
        transport=httpx.MockTransport(handler),
    )


def test_parse_catalog_maps_path_section_title():
    entries = parse_catalog([
        "https://docs.teamscale.com/introduction/agile-requirements-tracing/",
    ])
    assert entries == [{
        "path": "/introduction/agile-requirements-tracing/",
        "section": "introduction",
        "title": "Agile requirements tracing",
    }]


def test_parse_catalog_filters_by_section():
    urls = [
        "https://docs.teamscale.com/howto/a/",
        "https://docs.teamscale.com/reference/b/",
    ]
    sections = {e["section"] for e in parse_catalog(urls, section="howto")}
    assert sections == {"howto"}


async def test_fetch_sitemap_urls_parses_locs():
    urls = await fetch_sitemap_urls(_client())
    assert len(urls) == 3
    assert "https://docs.teamscale.com/reference/rest-api/" in urls


async def test_catalog_end_to_end():
    entries = await catalog(_client())
    assert {e["section"] for e in entries} == {"introduction", "howto", "reference"}
