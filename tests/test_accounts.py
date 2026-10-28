from datetime import timedelta
import secrets

from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.auth import now
from app.models import QuizAttempt, Response
from sqlalchemy import select


def account(role):
    client = TestClient(app)
    email = secrets.token_hex(6)+'@example.com'
    response = client.post('/api/auth/register', json={
        'email': email, 'password': 'a-secure-password', 'name': role.title(), 'role': role})
    assert response.status_code == 200, response.text
    return client, response.json()


def classroom(teacher):
    response = teacher.post('/api/classes', json={'name': 'Private class'})
    assert response.status_code == 201
    return response.json()['id']


def enroll(teacher, student, info, class_id):
    response = teacher.post(f'/api/classes/{class_id}/invitations', json={'email': info['email']})
    assert response.status_code == 201
    token = response.json()['token']
    assert student.post('/api/invitations/accept', json={'token': token}).status_code == 200
    return token


def publish(teacher, class_id, count=4):
    response = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'Timed quiz', 'total_time_s': 300, 'question_time_s': 30,
        'items': [{'item_id': f'q{i}', 'skill_id': 'topic', 'stem': f'Question {i}',
                   'options': [{'id': 'A', 'text': 'Yes', 'is_correct': True},
                               {'id': 'B', 'text': 'No', 'is_correct': False}]} for i in range(count)]})
    assert response.status_code == 201, response.text
    return response.json()


def answer(client, attempt, option='A', confidence='Sure'):
    response = client.post(f"/api/attempts/{attempt['id']}/answer", json={
        'item_id': attempt['question']['item_id'], 'chosen_option': option, 'confidence': confidence})
    assert response.status_code == 200, response.text
    return response.json()


def test_account_login_logout_and_unauthenticated_access(client):
    user, info = account('teacher')
    assert user.get('/api/auth/me').json()['email'] == info['email']
    assert user.post('/api/auth/logout').status_code == 200
    assert user.get('/api/classes').status_code == 401
    assert user.get('/api/teacher/heatmap/python_recursion').status_code == 401
    assert user.post('/api/auth/login', json={'email': info['email'], 'password': 'wrong-password'}).status_code == 401
    assert user.post('/api/auth/login', json={'email': info['email'], 'password': 'a-secure-password'}).status_code == 200
    assert user.post('/api/classes', json={'name': 'x'}, headers={'Origin': 'https://attacker.example'}).status_code == 403


def test_class_privacy_and_email_bound_invitation(client):
    teacher, _ = account('teacher')
    outsider, _ = account('teacher')
    student, info = account('student')
    other, other_info = account('student')
    class_id = classroom(teacher)
    invitation = teacher.post(f'/api/classes/{class_id}/invitations', json={'email': info['email']}).json()
    assert other.post('/api/invitations/accept', json={'token': invitation['token']}).status_code == 403
    assert student.post('/api/invitations/accept', json={'token': invitation['token']}).status_code == 200
    assert student.post('/api/invitations/accept', json={'token': invitation['token']}).status_code == 422
    quiz = publish(teacher, class_id)
    assert student.post('/api/classes', json={'name': 'Forbidden'}).status_code == 403
    assert student.post(f'/api/classes/{class_id}/quizzes', json={'title': 'no'}).status_code == 403
    assert student.get(f"/api/teacher/heatmap/{quiz['skill_id']}").status_code == 403
    assert outsider.get(f"/api/teacher/heatmap/{quiz['skill_id']}").status_code == 403
    assert other.get(f"/api/items/{quiz['skill_id']}").status_code == 403
    assert student.get(f"/api/profile/{other_info['id']}/{quiz['skill_id']}").status_code == 403
    assert outsider.get(f'/api/classes/{class_id}/students').status_code == 403
    assert student.post('/api/items/bulk', json=[]).status_code == 403
    assert student.post('/api/seed').status_code == 403
    assert student.post('/api/submit', json={'learner_id': info['id'], 'item_id': 'anything', 'skill_id': quiz['skill_id'], 'chosen_option':'A', 'confidence':'Sure', 'time_ms':0}).status_code == 410
    assert teacher.get(f"/api/teacher/heatmap/{quiz['skill_id']}").json()['total_students'] == 1


def test_scores_full_partial_uncertain_and_duplicate(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    quiz = publish(teacher, class_id)
    attempt = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    original = attempt
    attempt = answer(student, attempt)
    assert attempt['marks']['score'] == 1
    assert attempt['marks']['percentage'] == attempt['marks']['performance_percentage'] == 25
    duplicate = student.post(f"/api/attempts/{attempt['id']}/answer", json={'item_id': original['question']['item_id'], 'chosen_option':'A','confidence':'Sure'})
    assert duplicate.status_code == 409
    for _ in range(3):
        attempt = answer(student, attempt)
    assert attempt['finished'] is True
    assert attempt['marks']['score'] == 4
    assert attempt['marks']['performance_percentage'] == 100
    resumed = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    assert resumed['id'] == attempt['id'] and resumed['finished']
    second = publish(teacher, class_id, 1)
    attempt = student.post(f"/api/quizzes/{second['id']}/start").json()
    attempt = answer(student, attempt, confidence='Guessing')
    assert attempt['marks']['score'] == 1
    assert attempt['marks']['percentage'] == 100
    assert attempt['marks']['performance_percentage'] == 75


def test_server_enforced_deadlines_and_resume(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    quiz = publish(teacher, class_id, 2)
    attempt = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    resumed = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    assert resumed['deadline'] == attempt['deadline']
    assert resumed['question_deadline'] == attempt['question_deadline']
    with SessionLocal() as db:
        row = db.get(QuizAttempt, attempt['id'])
        row.question_deadline = now()-timedelta(seconds=1)
        db.commit()
    attempt = answer(student, attempt)
    assert attempt['marks']['score'] == 0
    assert attempt['current_index'] == 1
    with SessionLocal() as db:
        row = db.get(QuizAttempt, attempt['id'])
        row.deadline = now()-timedelta(seconds=1)
        db.commit()
    attempt = answer(student, attempt)
    assert attempt['finished'] and attempt['marks']['score'] == 0
    with SessionLocal() as db:
        assert not db.scalar(select(Response).where(Response.learner_id == info['id']))


def test_preview_hides_future_questions_and_server_records_elapsed_time(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    quiz = publish(teacher, class_id, 1)
    preview = student.get(f"/api/items/{quiz['skill_id']}").json()
    assert set(preview[0]) == {'item_id', 'expected_time_s'}
    assert preview[0]['expected_time_s'] == 30
    attempt = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    with SessionLocal() as db:
        row = db.get(QuizAttempt, attempt['id'])
        row.question_started_at = now()-timedelta(seconds=5)
        db.commit()
    result = answer(student, attempt, confidence='Unsure')
    assert result['marks']['score'] == 1
    assert result['marks']['performance_percentage'] == 85
    journal = student.get(f"/api/review/{info['id']}/{quiz['skill_id']}").json()
    assert journal[0]['time_ms'] >= 5000
    assert 'is_correct' not in attempt['question']['options'][0]


def test_invitation_expiry_and_role_login(client):
    from app.auth import digest
    from app.models import Invitation
    teacher, teacher_info = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    token = teacher.post(f'/api/classes/{class_id}/invitations', json={'email': info['email']}).json()['token']
    with SessionLocal() as db:
        invitation = db.get(Invitation, digest(token))
        invitation.expires_at = now()-timedelta(days=1)
        db.commit()
    assert student.post('/api/invitations/accept', json={'token': token}).status_code == 422
    assert student.post(f'/api/quizzes/not-a-quiz/start').status_code == 404
    assert teacher.post('/api/auth/login', json={'email': teacher_info['email'], 'password': 'a-secure-password', 'role': 'student'}).status_code == 401


def test_quiz_time_overrides_and_class_isolation(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    other_class = classroom(teacher)
    quiz = publish(teacher, other_class, 1)
    assert student.post(f"/api/quizzes/{quiz['id']}/start").status_code == 403
    response = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'Different question times', 'total_time_s': 90, 'question_time_s': 20,
        'items': [
            {'item_id': 'one', 'skill_id': 'topic', 'stem': 'First?', 'expected_time_s': 45,
             'options': [{'id':'A', 'text':'Yes', 'is_correct':True}]},
            {'item_id': 'two', 'skill_id': 'topic', 'stem': 'Second?',
             'options': [{'id':'A', 'text':'Yes', 'is_correct':True}]}]})
    assert response.status_code == 201
    new_quiz = response.json()
    questions = teacher.get(f"/api/items/{new_quiz['skill_id']}").json()
    assert [q['expected_time_s'] for q in questions] == [45, 20]
    attempt = student.post(f"/api/quizzes/{new_quiz['id']}/start").json()
    assert attempt['question']['stem'] == 'First?'
    assert answer(student, attempt)['question']['stem'] == 'Second?'
