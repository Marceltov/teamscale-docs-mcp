<h1 align="center"><a href="https://github.com/MarcelBruckner/teamscale-docs-mcp">Teamscale Docs MCP server</a></h1>

<p align="center"><em>Standalone MCP server exposing Teamscale's product documentation as tools — sitemap catalog + on-demand Markdown, no auth, self-hosted or central</em></p>

A standalone [MCP](https://modelcontextprotocol.io) server that exposes
[Teamscale](https://teamscale.com)'s product documentation to MCP clients as
tools. It runs as a **container sidecar**: it fetches a docs site's
`sitemap.xml` for a page catalog and converts individual VitePress pages to
Markdown **on demand**, served over streamable **HTTP** so any MCP client
connects to it by URL.

It can point at either a Teamscale instance's own **bundled documentation**
(served at `/documentation/`) or the public docs at
[docs.teamscale.com](https://docs.teamscale.com) — see
[Architecture](#architecture). The docs are public content, so **the server
needs no authentication** — no tokens, no identity headers.

> **Related:** [**teamscale-mcp**](https://github.com/MarcelBruckner/teamscale-mcp)
> is the companion server that exposes Teamscale's **REST API** as MCP tools
> (against your instance, with per-client credentials). The two are designed to
> run side by side as sidecars — this docs server on `8082`, teamscale-mcp on
> `8081` — giving an MCP client both the product's *documentation* and its
> *live data*.

## Contents

- [Contents](#contents)
- [Who it's for](#who-its-for)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Connecting a client](#connecting-a-client)
- [Tools](#tools)
- [Configuration](#configuration)
- [TLS / reverse proxy](#tls--reverse-proxy)
- [Security](#security)
- [How it works](#how-it-works)
- [Contributing](#contributing)

## Who it's for

Teamscale's official [Claude Code plugin](https://github.com/teamscale/claude-code)
is built for **developers editing code** — fix these findings, close these test
gaps. This docs server serves a **different audience**: people who need to
**understand** Teamscale rather than change code.

- **Newcomers** learning what a test gap, a finding category, or an analysis
  profile actually is — and how to set one up — asked in plain language instead of
  hunting through the manual.
- **Managers and other non-developers** who want what they see in a dashboard
  explained, on demand.
- **Consultants** (internal or partner) who need the product's how-tos and
  reference at their fingertips across many customer instances.

Pair it with the companion
[**teamscale-mcp**](https://github.com/MarcelBruckner/teamscale-mcp) (the Teamscale
REST API as tools) and the agent can both **explain** Teamscale — concepts,
how-tos, reference (this server) — and **act on it** — read data, set up projects,
adjust analysis profiles (teamscale-mcp) — in one conversation. Together they're a
**data-and-understanding assistant**, complementary to the plugin's code-editing
workflows.

## Architecture

**teamscale-docs-mcp** (this repo) is a small stateless service between MCP
clients and a documentation source. It holds no secrets and stores no state,
so it can be deployed in either of two topologies:

**A. Alongside a Teamscale instance (self-hosted, no external calls).** Every
Teamscale instance ships its **version-matched** documentation at
`/documentation/` — a VitePress site with a `sitemap.xml`, the same shape as
the public docs. Run the sidecar on the same Docker network and point
`DOCS_BASE_URL` at the in-network instance, so an LLM only ever talks to *your
own instance* and nothing leaves your network — ideal for customers who don't
want their LLM calling an external service. This is how the bundled
[`docker-compose.yaml`](docker-compose.yaml) is wired
(`DOCS_BASE_URL: http://teamscale:8080/documentation`).

> The instance's sitemap lists canonical `docs.teamscale.com` URLs; the server
> re-joins each page path onto `DOCS_BASE_URL`, so pages are still fetched from
> the local instance. Verified against a live instance: the full catalog (300+
> pages across `howto`, `reference`, `tutorial`, `introduction`,
> `getting-started`, `troubleshooting`, `glossary`, `terms`, `changelog`,
> `faq`, `goto`) is served, and the docs match that instance's exact version.

**B. One central hosted endpoint.** Because the docs are public and the server
needs no auth, a single shared deployment (`DOCS_BASE_URL:
https://docs.teamscale.com`) can serve every client. Host it behind the docs
site — e.g. at `https://docs.teamscale.com/docs-mcp` — and clients just add that URL,
with no local container to run. Lowest friction; the docs track the latest
public release.

## Quick start

**Add teamscale-docs-mcp to your Teamscale's `docker-compose.yaml`** — one
service, pulling the prebuilt image, so there's nothing to clone or build:

```yaml
services:
  teamscale:
    # ... your existing Teamscale service ...

  teamscale-docs-mcp:
    image: ghcr.io/marcelbruckner/teamscale-docs-mcp:latest
    container_name: teamscale-docs-mcp
    restart: unless-stopped
    depends_on:
      # Wait for your existing Teamscale to be healthy before starting, so the
      # first docs fetch doesn't race its startup. Requires a healthcheck on the
      # teamscale service (drop `condition` if it has none).
      teamscale:
        condition: service_healthy
    environment:
      # Serve this instance's version-matched bundled docs (/documentation/),
      # so no request leaves your network. `teamscale` is the service name of
      # your existing Teamscale on the same compose network. Set this to
      # https://docs.teamscale.com instead to serve the public docs.
      DOCS_BASE_URL: http://teamscale:8080/documentation
    ports:
      - "8082:8082"
    healthcheck:
      # /health is always unauthenticated and returns `ok` once the server is up.
      test: ["CMD", "curl", "-fsS", "http://localhost:8082/health"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 10s
```

Then start it:

```bash
docker compose up -d teamscale-docs-mcp
```

Both services share the compose network, so `teamscale` resolves to your
existing container. The MCP endpoint is then available at
`http://localhost:8082/docs-mcp`. (Port `8082` and path `/docs-mcp` both differ
from the sibling [teamscale-mcp](https://github.com/MarcelBruckner/teamscale-mcp),
whose REST API MCP server runs on `8081` at `/mcp` — so the two never collide,
even behind one host.)

Verify the server is up:

```bash
curl -s http://localhost:8082/health   # -> ok
```

**Connect your MCP client** — no headers needed:

```bash
claude mcp add teamscale-docs --scope user --transport http \
  http://localhost:8082/docs-mcp
```

Prefer not to run a container at all? Point clients at a central hosted
endpoint instead — see [Architecture](#architecture) option B.

## Connecting a client

The docs are public, so the client presents **no credentials**. Point the URL
at wherever teamscale-docs-mcp is reachable (a TLS reverse proxy, or the
container directly on a trusted LAN):

```bash
# Behind a reverse proxy (TLS)
claude mcp add teamscale-docs --scope user --transport http \
  https://your-host/docs-mcp

# Directly over a LAN, by IP or hostname
claude mcp add teamscale-docs --scope user --transport http \
  http://192.168.1.50:8082/docs-mcp
```

The `--scope user` flag registers the server across **all** your projects. Drop
it to fall back to `claude mcp add`'s default **local** scope — available only
to you in the current project:

```bash
claude mcp add teamscale-docs --transport http \
  http://localhost:8082/docs-mcp
```

## Tools

| Tool                     | Signature                                                       | Description                                                                                                                                                                                |
| ------------------------ | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `list_documentation`     | `list_documentation(section: str \| None = None) -> list[dict]` | Lists documentation pages from the docs sitemap as `{path, section, title}` entries. Pass a `section` to narrow the (~335-page) catalog.                                                   |
| `get_documentation_page` | `get_documentation_page(path: str) -> str`                      | Fetches a page (by `path` from `list_documentation`, or a full `docs.teamscale.com` URL) and returns its Markdown, prefixed with the title and canonical URL. Capped at 50,000 characters. |

Sections are the first path segment, e.g. `howto`, `reference`, `tutorial`,
`introduction`, `getting-started`, `troubleshooting`, `glossary`, `terms`,
`changelog`, `goto`.

## Configuration

All configuration is via environment variables:

| Variable            | Default                      | Description                                                                                                                                                                                                                          |
| ------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `DOCS_BASE_URL`     | `https://docs.teamscale.com` | Base URL of the documentation site. Set it to a Teamscale instance's bundled docs (e.g. `http://teamscale:8080/documentation`) to serve version-matched docs with no external calls — see [Architecture](#architecture). |
| `MCP_HOST`          | `0.0.0.0`                    | Interface the server binds to.                                                                                                                                                                                                       |
| `MCP_PORT`          | `8082`                       | Port the server listens on (inside the container).                                                                                                                                                                                   |
| `MCP_PATH`          | `/docs-mcp`                  | HTTP path the MCP endpoint is served under. Distinct from teamscale-mcp's `/mcp` so both can share one host.                                                                                                                          |
| `MCP_ALLOWED_HOSTS` | _(unset = any)_              | Comma-separated `Host` allowlist (DNS-rebinding protection). Unset accepts any Host; set it to restrict.                                                                                                                              |

## TLS / reverse proxy

The container serves plain HTTP on `:8082`; terminate TLS at your reverse proxy.

**Dedicated host** — teamscale-docs-mcp on its own domain:

```
docs-mcp.example.com {
    reverse_proxy teamscale-docs-mcp:8082
}
```

**Same host as Teamscale, under `/docs-mcp`** — serve both from one domain, so
clients reach Teamscale at `https://teamscale.example.com/` and the docs MCP
endpoint at `https://teamscale.example.com/docs-mcp`. The `/docs-mcp` path is
distinct from the REST API server's `/mcp`, so both MCP sidecars can live behind
the same host at once:

```
teamscale.example.com {
    # Route the docs MCP endpoint to its sidecar. `handle` keeps the /docs-mcp
    # path, which is exactly what the server serves (MCP_PATH), so no rewrite is
    # needed.
    handle /docs-mcp* {
        reverse_proxy teamscale-docs-mcp:8082
    }

    # The REST API MCP server (teamscale-mcp), if you run it too, at /mcp.
    handle /mcp* {
        reverse_proxy teamscale-mcp:8081
    }

    # Everything else is Teamscale itself.
    handle {
        reverse_proxy teamscale:8080
    }
}
```

`teamscale`, `teamscale-docs-mcp`, and `teamscale-mcp` are the compose service
names — put Caddy on the same Docker network so they resolve. Teamscale has no
`/docs-mcp` or `/mcp` route of its own, so the split is unambiguous. Host
protection is off by default; if you enable it, add the domain to
`MCP_ALLOWED_HOSTS`.

## Security

The documentation is public content, so the server has **no authentication** —
no tokens, no identity headers, no per-client credentials. It is also
effectively **read-only**: the only outbound calls it makes are `GET`s for the
sitemap and individual pages from `DOCS_BASE_URL`.

- In the **self-hosted** topology ([Architecture](#architecture) option A), all
  traffic stays on your network: clients reach the sidecar, and the sidecar
  reads docs from your own Teamscale instance over the Docker network — nothing
  leaves your infrastructure.
- By default the server accepts requests for **any** `Host` (FastMCP's
  DNS-rebinding protection is disabled), so it can be reached by LAN IP or by
  the domain your reverse proxy forwards. To lock this down, set
  `MCP_ALLOWED_HOSTS` to a comma-separated list of the host[:port] values you
  actually use (e.g. `192.168.1.50:8082,teamscale.example.com`); `localhost` is
  always allowed, and anything else gets a `421`.
- The `/health` endpoint is always unauthenticated (used by the container
  healthcheck) and returns `ok`.

## How it works

There is no startup download — the server comes up immediately and fetches from
`DOCS_BASE_URL` lazily:

- `list_documentation` fetches `sitemap.xml` and parses each `<loc>` URL into a
  `{path, section, title}` catalog entry, optionally filtered by section.
- `get_documentation_page` fetches a single page, strips VitePress chrome
  (nav/aside/footer), converts the content region to Markdown, prefixes the
  title and canonical URL, and caps the result at 50,000 characters.

Because the sitemap lists canonical `docs.teamscale.com` URLs, each page path is
re-joined onto `DOCS_BASE_URL` before fetching — so pointing at a local instance
still reads pages from that instance.

## Contributing

For a self-contained stack — a throwaway Teamscale instance plus this server
built from local source — bring both up with:

```bash
docker compose up -d --build
```

For iterating on the server directly:

```bash
cd app
uv sync
uv run pytest            # unit tests
uv run pytest tests/live # live tests against docs.teamscale.com (auto-skip if offline)
```
