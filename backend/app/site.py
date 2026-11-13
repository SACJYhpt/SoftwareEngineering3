"""Serve the built Vue front end and the API from one origin (ER-US-B11).

The front end uses HTML5 history routes such as /events/12, so opening a shared link or
refreshing a page asks the server for that path. Every path that is not a built file gets
index.html, and the Vue router then shows the right page. API requests keep the /api prefix
used in development and reach the API with the prefix removed, exactly like the Vite proxy.
"""
from pathlib import Path

from starlette.responses import FileResponse, PlainTextResponse

API_PREFIX = "/api"


class FrontendSite:
    def __init__(self, api, dist_dir):
        self.api = api
        self.dist = Path(dist_dir).resolve()
        self.index = self.dist / "index.html"
        if not self.index.is_file():
            raise RuntimeError(f"FRONTEND_DIST 找不到 index.html：{self.dist}（請先在 frontend 執行 npm run build）")

    @property
    def state(self):
        # Lets callers reach app.state (settings, sessions) as with the plain API app.
        return self.api.state

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.api(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == API_PREFIX or path.startswith(API_PREFIX + "/"):
            inner = path[len(API_PREFIX):] or "/"
            child = dict(scope, path=inner, raw_path=inner.encode())
            await self.api(child, receive, send)
            return
        if scope["type"] != "http":
            return
        await self.static(scope)(scope, receive, send)

    def static(self, scope):
        if scope["method"] not in ("GET", "HEAD"):
            return PlainTextResponse("Method Not Allowed", status_code=405, headers={"Allow": "GET, HEAD"})
        relative = scope["path"].lstrip("/")
        if relative:
            try:
                candidate = (self.dist / relative).resolve()
                found = candidate.is_relative_to(self.dist) and candidate.is_file()
            except (OSError, ValueError):
                found = False
            if found:
                # Vite puts a content hash in asset names, so they may be cached for long.
                cache = "public, max-age=31536000, immutable" if relative.startswith("assets/") else "no-cache"
                return FileResponse(candidate, headers={"Cache-Control": cache})
            if relative.startswith("assets/"):
                return PlainTextResponse("Not Found", status_code=404)
        # SPA fallback: the Vue router decides what /events/12, /faq, ... show.
        return FileResponse(self.index, headers={"Cache-Control": "no-cache"})


def with_frontend(api, dist_dir):
    return FrontendSite(api, dist_dir) if dist_dir else api
