import os
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import httpx
import uvicorn
from bs4 import BeautifulSoup
from fastmcp import FastMCP
from markdownify import markdownify
from starlette.requests import Request
from starlette.responses import PlainTextResponse

DOCS_BASE_URL_ENV = "DOCS_BASE_URL"
DEFAULT_DOCS_BASE_URL = "https://docs.teamscale.com"

MCP_HOST_ENV = "MCP_HOST"
MCP_PORT_ENV = "MCP_PORT"
MCP_PATH_ENV = "MCP_PATH"
MCP_ALLOWED_HOSTS_ENV = "MCP_ALLOWED_HOSTS"

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8082
# A distinct path from the sibling teamscale-mcp REST API server (which serves
# `/mcp`), so both can sit behind one host without colliding.
DEFAULT_PATH = "/docs-mcp"
HEALTH_PATH = "/health"


def register_health(mcp: FastMCP) -> None:
    """Add an unauthenticated health endpoint for container healthchecks."""

    @mcp.custom_route(HEALTH_PATH, methods=["GET"])
    async def health(_request: Request):
        return PlainTextResponse("ok")


SITEMAP_PATH = "/sitemap.xml"


async def fetch_sitemap_urls(client: httpx.AsyncClient) -> list[str]:
    """Fetch the docs sitemap and return every <loc> URL."""
    response = await client.get(SITEMAP_PATH)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    # Match <loc> regardless of the sitemap namespace prefix.
    return [
        el.text.strip()
        for el in root.iter()
        if el.tag.endswith("loc") and el.text and el.text.strip()
    ]


def _humanize(slug: str) -> str:
    text = slug.replace("-", " ").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else text


def parse_catalog(urls: list[str], section: str | None = None) -> list[dict]:
    """Turn sitemap URLs into catalog entries, optionally filtered by section."""
    entries: list[dict] = []
    for url in urls:
        path = urlsplit(url).path.strip("/")
        if not path:
            continue
        segments = path.split("/")
        page_section = segments[0]
        if section and page_section != section:
            continue
        entries.append({
            "path": f"/{path}/",
            "section": page_section,
            "title": _humanize(segments[-1] or segments[0]),
        })
    return entries


async def catalog(client: httpx.AsyncClient, section: str | None = None) -> list[dict]:
    """The page catalog: sitemap URLs parsed into entries."""
    return parse_catalog(await fetch_sitemap_urls(client), section)


def register_list_documentation(mcp: FastMCP, client: httpx.AsyncClient) -> None:
    @mcp.tool(name="list_documentation")
    async def list_documentation(section: str | None = None) -> list[dict]:
        """List Teamscale documentation pages (from the docs sitemap).

        Returns entries of {path, section, title}. There are ~335 pages, so pass
        a `section` to narrow: one of howto, reference, tutorial, introduction,
        getting-started, troubleshooting, glossary, terms, changelog, goto.
        Use `get_documentation_page(path)` to read a page.
        """
        return await catalog(client, section)


MAX_PAGE_CHARS = 50_000

# The VitePress rendered content lives in `.vp-doc`; try progressively broader
# fallbacks. Non-content chrome is removed before conversion.
_CONTENT_SELECTORS = (".vp-doc", ".content-body", "main")
_CHROME_SELECTORS = (
    "nav", "aside", "footer",
    ".VPDocAside", ".VPDocFooter", ".pager", ".prev-next", ".edit-info",
)


def normalize_page_url(path_or_url: str, base_url: str) -> str:
    """Return an absolute page URL for a site-relative path or a full URL."""
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    return f"{base_url.rstrip('/')}/{path_or_url.lstrip('/')}"


def extract_page(html: str) -> tuple[str, str]:
    """Extract (title, Markdown) from a VitePress documentation page."""
    soup = BeautifulSoup(html, "html.parser")
    node = None
    for selector in _CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is not None:
            break
    if node is None:
        node = soup.body or soup
    for chrome in _CHROME_SELECTORS:
        for element in node.select(chrome):
            element.decompose()
    heading = node.find(["h1", "h2"])
    if heading:
        title = heading.get_text(strip=True)
    elif soup.title:
        title = soup.title.get_text(strip=True)
    else:
        title = ""
    markdown = markdownify(str(node), heading_style="ATX").strip()
    return title, markdown


async def render_page(
    client: httpx.AsyncClient,
    path: str,
    base_url: str,
    max_chars: int = MAX_PAGE_CHARS,
) -> str:
    """Fetch a documentation page and return it as titled Markdown, truncated."""
    url = normalize_page_url(path, base_url)
    response = await client.get(url)
    response.raise_for_status()
    title, markdown = extract_page(response.text)
    header = f"# {title}\n\n<{url}>\n\n" if title else f"<{url}>\n\n"
    out = header + markdown
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "\n\n[truncated]"
    return out


def register_get_documentation_page(
    mcp: FastMCP, client: httpx.AsyncClient, base_url: str
) -> None:
    @mcp.tool(name="get_documentation_page")
    async def get_documentation_page(path: str) -> str:
        """Fetch a Teamscale documentation page as Markdown.

        `path` is a page path from `list_documentation` (e.g.
        "/howto/setup/pre-commit-analysis/") or a full docs.teamscale.com URL.
        Returns the page's Markdown, prefixed with its title and canonical URL.
        """
        return await render_page(client, path, base_url)


def build_server(client: httpx.AsyncClient | None = None) -> FastMCP:
    """Build the docs MCP server. `client` is injectable for testing; in
    production it targets DOCS_BASE_URL. The docs are public, so no auth."""
    base_url = os.environ.get(DOCS_BASE_URL_ENV, DEFAULT_DOCS_BASE_URL).rstrip("/")
    if client is None:
        client = httpx.AsyncClient(base_url=base_url, timeout=30, follow_redirects=True)
    mcp = FastMCP(name="Teamscale Docs MCP")
    register_health(mcp)
    register_list_documentation(mcp, client)
    register_get_documentation_page(mcp, client, base_url)
    return mcp


def serve(mcp: FastMCP) -> None:
    """Serve the MCP server over streamable HTTP (no auth middleware)."""
    host = os.environ.get(MCP_HOST_ENV, DEFAULT_HOST)
    port = int(os.environ.get(MCP_PORT_ENV, DEFAULT_PORT))
    path = os.environ.get(MCP_PATH_ENV, DEFAULT_PATH)

    allowed = os.environ.get(MCP_ALLOWED_HOSTS_ENV, "").strip()
    if allowed:
        hosts = [h.strip() for h in allowed.split(",") if h.strip()]
        app = mcp.http_app(path=path, allowed_hosts=hosts)
        print(f"Host protection ON; allowed hosts (plus localhost): {hosts}",
              file=sys.stderr)
    else:
        app = mcp.http_app(path=path, host_origin_protection=False)
        print(f"Host protection OFF (any Host accepted) -- set "
              f"{MCP_ALLOWED_HOSTS_ENV} to restrict.", file=sys.stderr)

    print(f"Serving Teamscale Docs MCP on http://{host}:{port}{path}",
          file=sys.stderr)
    uvicorn.run(app, host=host, port=port)


def main():
    serve(build_server())


if __name__ == "__main__":
    main()
