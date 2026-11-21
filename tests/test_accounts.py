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


def test_classroom_codes_join_and_privacy(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    other_teacher, _ = account('teacher')
    response = teacher.post('/api/classes', json={'name': 'Join by code'})
    code = response.json()['join_code']
    class_id = response.json()['id']
    assert len(code) == 8 and code.isalnum() and code == code.upper()
    assert next(c for c in teacher.get('/api/classes').json() if c['id'] == class_id)['join_code'] == code
    assert other_teacher.post('/api/classes/join', json={'code': code}).status_code == 403
    assert student.post('/api/classes/join', json={'code': 'short'}).status_code == 422
    assert student.post('/api/classes/join', json={'code': '00000000'}).status_code == 404
    for _ in range(2):
        joined = student.post('/api/classes/join', json={'code': ' '+code.lower()+' '})
        assert joined.status_code == 200 and joined.json()['class_id'] == class_id
    assert student.get('/api/classes').json() == [{'id': class_id, 'name': 'Join by code'}]
    assert len(teacher.get(f'/api/classes/{class_id}/students').json()) == 1
    assert other_teacher.get('/api/classes').json() == []
    assert teacher.get(f'/api/classes/{class_id}/students').json()[0]['id'] == info['id']


def test_existing_classroom_gets_stable_code(client):
    from app.models import Classroom, ClassOwner
    teacher, info = account('teacher')
    old_id = secrets.token_hex(16)
    with SessionLocal() as db:
        db.add(Classroom(class_id=old_id, name='Existing class'))
        db.flush()
        db.add(ClassOwner(class_id=old_id, teacher_id=info['id']))
        db.commit()
    first = teacher.get('/api/classes').json()[0]['join_code']
    assert len(first) == 8
    assert teacher.get('/api/classes').json()[0]['join_code'] == first


def test_student_identity_login_and_teacher_results(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    credentials = {'email': info['email'], 'password': 'a-secure-password',
                   'sid': '  CSE001  ', 'branch': ' Computer Science '}
    assert student.post('/api/auth/login', json={**credentials, 'password': 'wrong-password'}).status_code == 401
    assert student.get('/api/auth/me').json()['sid'] == ''
    signed_in = student.post('/api/auth/login', json=credentials)
    assert signed_in.status_code == 200
    assert signed_in.json()['sid'] == 'CSE001'
    assert signed_in.json()['branch'] == 'Computer Science'
    assert student.post('/api/auth/login', json={**credentials, 'sid': '', 'branch': ''}).json()['sid'] == 'CSE001'
    assert student.post('/api/auth/login', json={**credentials, 'sid': 'x'*65}).status_code == 422
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    quiz = publish(teacher, class_id)
    roster = teacher.get(f'/api/classes/{class_id}/students').json()
    assert roster[0]['sid'] == 'CSE001'
    assert roster[0]['branch'] == 'Computer Science'
    student.post(f"/api/quizzes/{quiz['id']}/start")
    report = teacher.get(f"/api/teacher/heatmap/{quiz['skill_id']}").json()
    row = next(s for s in report['students'] if s['learner_id'] == info['id'])
    assert row['sid'] == 'CSE001'
    assert row['branch'] == 'Computer Science'


def test_student_sid_login_and_case_insensitivity(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    res = student.post('/api/auth/login', json={'email': info['email'], 'password': 'a-secure-password', 'sid': 'CS2024_042', 'branch': 'AI & DS'})
    assert res.status_code == 200
    assert res.json()['sid'] == 'CS2024_042'
    assert res.json()['branch'] == 'AI & DS'

    student.post('/api/auth/logout')
    assert student.get('/api/auth/me').status_code == 401

    sid_client = TestClient(app)
    login_sid = sid_client.post('/api/auth/login', json={'sid': 'CS2024_042', 'password': 'a-secure-password'})
    assert login_sid.status_code == 200
    assert login_sid.json()['email'] == info['email']
    assert login_sid.json()['sid'] == 'CS2024_042'

    sid_lower_client = TestClient(app)
    login_email_as_sid = sid_lower_client.post('/api/auth/login', json={'email': 'cs2024_042', 'password': 'a-secure-password'})
    assert login_email_as_sid.status_code == 200
    assert login_email_as_sid.json()['email'] == info['email']

    bad_pass = TestClient(app).post('/api/auth/login', json={'sid': 'CS2024_042', 'password': 'wrong-password'})
    assert bad_pass.status_code == 401
    assert 'incorrect' in bad_pass.json()['detail']

    bad_sid = TestClient(app).post('/api/auth/login', json={'sid': 'NONEXISTENT_SID', 'password': 'a-secure-password'})
    assert bad_sid.status_code == 401
    assert 'not found' in bad_sid.json()['detail'].lower()


def test_learner_profile_and_teacher_insight_sid(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    student.post('/api/auth/login', json={'email': info['email'], 'password': 'a-secure-password', 'sid': 'STU999', 'branch': 'ECE'})
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    quiz = publish(teacher, class_id, 1)

    profile = teacher.get(f"/api/profile/{info['id']}/{quiz['skill_id']}").json()
    assert profile['sid'] == 'STU999'
    assert profile['branch'] == 'ECE'
    assert profile['display_name'] == info['name']
    assert profile['email'] == info['email']

    attempt = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    answer(student, attempt)

    profile_after = teacher.get(f"/api/profile/{info['id']}/{quiz['skill_id']}").json()
    assert profile_after['sid'] == 'STU999'
    assert profile_after['branch'] == 'ECE'
    assert profile_after['display_name'] == info['name']
    assert profile_after['email'] == info['email']

    heatmap = teacher.get(f"/api/teacher/heatmap/{quiz['skill_id']}").json()
    student_row = next(s for s in heatmap['students'] if s['learner_id'] == info['id'])
    assert student_row['sid'] == 'STU999'
    assert student_row['branch'] == 'ECE'
    assert isinstance(student_row['sid'], str)
    assert isinstance(student_row['branch'], str)


def test_teacher_remove_student_from_class_and_admin_rejected(client):
    # Admin role is not allowed and must fail validation
    invalid_admin = TestClient(app).post('/api/auth/register', json={
        'name': 'Admin User', 'email': 'admin@college.example', 'password': 'a-secure-password', 'role': 'admin'
    })
    assert invalid_admin.status_code == 422

    teacher_client, teacher_info = account('teacher')
    other_teacher, _ = account('teacher')
    student_client, student_info = account('student')
    student_client.post('/api/auth/login', json={'email': student_info['email'], 'password': 'a-secure-password', 'sid': 'SID_TEST', 'branch': 'IT'})

    class_id = classroom(teacher_client)
    enroll(teacher_client, student_client, student_info, class_id)
    quiz = publish(teacher_client, class_id, 1)
    attempt = student_client.post(f"/api/quizzes/{quiz['id']}/start").json()
    answer(student_client, attempt)

    # Admin endpoints no longer exist
    assert teacher_client.get('/api/admin/students').status_code == 404
    assert student_client.get('/api/admin/students').status_code == 404

    # Other teacher cannot remove student from this class
    assert other_teacher.delete(f"/api/classes/{class_id}/students/{student_info['id']}").status_code == 403

    # Classroom teacher can remove student from their class
    remove_from_class = teacher_client.delete(f"/api/classes/{class_id}/students/{student_info['id']}")
    assert remove_from_class.status_code == 200

    assert not any(s['id'] == student_info['id'] for s in teacher_client.get(f'/api/classes/{class_id}/students').json())
    assert student_client.get('/api/auth/me').status_code == 200
