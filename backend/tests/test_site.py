"""ER-US-B11: shared event links and refreshes reach the event page after deployment."""
import pytest
from fastapi.testclient import TestClient

from app.site import FrontendSite


@pytest.fixture
def site(application, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=app>SPA</div>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"ico")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    with TestClient(FrontendSite(application, dist)) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/events/1", "/events/1?from=line", "/faq", "/manage/events/3/edit", "/me/events"])
def test_spa_routes_return_index_for_direct_open_and_refresh(site, path):
    response = site.get(path)
    assert response.status_code == 200
    assert "SPA" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_built_files_are_served_and_hashed_assets_cached(site):
    asset = site.get("/assets/index-abc123.js")
    assert asset.status_code == 200 and asset.text == "console.log(1)"
    assert "immutable" in asset.headers["cache-control"]
    assert site.get("/favicon.ico").content == b"ico"
    assert site.get("/assets/missing.js").status_code == 404


def test_api_is_reachable_under_prefix_with_same_paths_as_dev_proxy(site):
    events = site.get("/api/events")
    assert events.status_code == 200 and isinstance(events.json(), list)
    assert site.get("/api/events/999").json()["detail"]["code"] == "EVENT_NOT_FOUND"
    assert site.get("/api/faq").json()["content"] == "測試文件"
    # Private API responses keep their no-store header behind the prefix.
    assert site.get("/api/auth/me").headers.get("cache-control") == "no-store"


def test_api_docs_page_loads_its_schema_under_the_prefix(site):
    page = site.get("/api/docs")
    assert page.status_code == 200 and "/api/openapi.json" in page.text
    assert site.get("/api/openapi.json").json()["info"]["title"] == "海大活動報名系統 API"


def test_files_outside_dist_are_never_served(site):
    for path in ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"]:
        response = site.get(path)
        assert "outside" not in response.text


def test_only_get_and_head_reach_static_files(site):
    assert site.post("/events/1").status_code == 405
    assert site.head("/events/1").status_code == 200
