import os
import tempfile

# Must be set BEFORE the app is imported so tests use their own throwaway database.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs lifespan -> creates tables
        yield c


@pytest.fixture(scope="session")
def seeded(client):
    r = client.post("/api/seed")
    assert r.status_code == 200
    return client
