import httpx

from server import extract_page, normalize_page_url, render_page

PAGE_HTML = """
<!DOCTYPE html><html><head><title>Doc | Teamscale</title></head><body>
<nav class="VPNav">navbar junk</nav>
<div class="VPDoc">
  <div class="content-container"><main class="main"><div class="content"><div class="content-body">
    <div class="vp-doc">
      <h1>Pre-commit analysis</h1>
      <p>Run analysis <a href="/reference/">before commit</a>.</p>
      <pre><code>teamscale precommit</code></pre>
      <div class="VPDocFooter"><footer>edit this page</footer></div>
    </div>
  </div></main></div>
  <aside class="VPDocAside">outline junk</aside>
</div>
<div class="pager"><a class="prev-next">next page junk</a></div>
</body></html>
"""


def test_normalize_page_url():
    base = "https://docs.teamscale.com"
    assert normalize_page_url("howto/x/", base) == "https://docs.teamscale.com/howto/x/"
    assert normalize_page_url("/howto/x/", base) == "https://docs.teamscale.com/howto/x/"
    full = "https://docs.teamscale.com/howto/x/"
    assert normalize_page_url(full, base) == full


def test_extract_page_returns_title_and_clean_markdown():
    title, markdown = extract_page(PAGE_HTML)
    assert title == "Pre-commit analysis"
    assert "Pre-commit analysis" in markdown
    assert "teamscale precommit" in markdown       # code preserved
    assert "before commit" in markdown             # link text preserved
    assert "outline junk" not in markdown          # aside stripped
    assert "next page junk" not in markdown        # pager stripped
    assert "edit this page" not in markdown        # footer stripped
    assert "navbar junk" not in markdown           # nav stripped


async def test_render_page_formats_and_caps():
    def handler(request):
        return httpx.Response(200, text=PAGE_HTML)
    client = httpx.AsyncClient(
        base_url="https://docs.teamscale.com",
        transport=httpx.MockTransport(handler),
    )
    out = await render_page(client, "howto/pre-commit/", "https://docs.teamscale.com")
    assert out.startswith("# Pre-commit analysis")
    assert "<https://docs.teamscale.com/howto/pre-commit/>" in out

    capped = await render_page(
        client, "howto/pre-commit/", "https://docs.teamscale.com", max_chars=40
    )
    assert capped.endswith("[truncated]")
    assert len(capped) <= 40 + len("\n\n[truncated]")
