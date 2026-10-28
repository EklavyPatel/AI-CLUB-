import os
import tempfile

os.environ['DATABASE_URL'] = f'sqlite:///{tempfile.mkdtemp()}/test.db'

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import ClassOwner, Quiz
from app.seed import seed_database


@pytest.fixture(scope='session')
def client():
    with TestClient(app) as c:
        account = c.post('/api/auth/register', json={
            'email': 'diagnostics@example.com', 'password': 'diagnostic-password',
            'name': 'Diagnostics Teacher', 'role': 'teacher'}).json()
        c.teacher_id = account['id']
        yield c


@pytest.fixture(scope='session')
def seeded(client):
    with SessionLocal() as db:
        seed_database(db)
        db.add(ClassOwner(class_id='demo-class', teacher_id=client.teacher_id))
        db.add(Quiz(id='diagnostic-demo', class_id='demo-class', title='Diagnostic demo',
                    skill_id='python_recursion', total_time_s=300))
        db.commit()
    return client
