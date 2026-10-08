
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.document_store import (
    DocumentStore,
    get_document_store,
)


@pytest.fixture
def client():
    test_store = DocumentStore()

    app.dependency_overrides[get_document_store] = (
        lambda: test_store
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_create_document(client):
    response = client.post(
        "/documents",
        json={
            "title": "FastAPI Guide",
            "filename": "fastapi.pdf",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "FastAPI Guide"
    assert data["filename"] == "fastapi.pdf"
    assert "created_at" in data


def test_list_documents(client):
    client.post(
        "/documents",
        json={"title": "Test", "filename": "test.txt"},
    )

    response = client.get("/documents")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_document(client):
    created = client.post(
        "/documents",
        json={"title": "Test", "filename": "test.pdf"},
    ).json()

    response = client.get(
        f"/documents/{created['id']}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_delete_document(client):
    created = client.post(
        "/documents",
        json={"title": "Test", "filename": "test.pdf"},
    ).json()

    document_id = created["id"]

    response = client.delete(
        f"/documents/{document_id}"
    )

    assert response.status_code == 204
    assert response.content == b""

    get_response = client.get(
        f"/documents/{document_id}"
    )

    assert get_response.status_code == 404


def test_invalid_document(client):
    response = client.post(
        "/documents",
        json={
            "title": "Test",
            "filename": "test.pdf",
            "admin": True,
        },
    )

    assert response.status_code == 422


def test_document_not_found(client):
    response = client.get("/documents/99999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Document not found"
    }


def test_delete_nonexistent_document(client):
    response = client.delete("/documents/99999")

    assert response.status_code == 404
