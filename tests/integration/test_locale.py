import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_set_locale_sets_cookie_and_redirects(client: TestClient) -> None:
    response = client.get("/locale/en", follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["locale"] == "en"


@pytest.mark.integration
def test_set_locale_rejects_unknown_language(client: TestClient) -> None:
    response = client.get("/locale/fr", follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["locale"] == "pt"


@pytest.mark.integration
def test_overview_page_respects_locale_cookie(client: TestClient) -> None:
    client.cookies.set("locale", "en")
    response = client.get("/")
    assert response.status_code == 200
    assert "Overview" in response.text
