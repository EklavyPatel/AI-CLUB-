from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.auth import now
from app.database import SessionLocal
from app.models import ExamPaper, Item, QuizAttempt
from app.pdf_import import parse_questions
from tests.test_accounts import account, classroom, enroll


def publish_exam(teacher, class_id, bank=None, count=2):
    bank = bank or [{'item_id': f'q{i}', 'skill_id': 'cs', 'stem': f'Question {i}?',
                     'kind': 'multiple' if i == 0 else 'single',
                     'options': [{'id': 'A', 'text': 'One', 'is_correct': True},
                                 {'id': 'B', 'text': 'Two', 'is_correct': i == 0},
                                 {'id': 'C', 'text': 'Three', 'is_correct': False}]} for i in range(5)]
    result = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'College assessment', 'mode': 'mcq', 'question_count': count,
        'total_time_s': 300, 'question_time_s': 30, 'items': bank})
    assert result.status_code == 201, result.text
    return result.json()


def setup_exam(count=2):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    quiz = publish_exam(teacher, class_id, count=count)
    attempt = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    return teacher, student, info, class_id, quiz, attempt


def correct_answers(attempt_id):
    with SessionLocal() as db:
        paper = db.get(ExamPaper, attempt_id)
        return {q['item_id']: [o['id'] for o in q['options'] if o['is_correct']] for q in paper.questions}


def test_pdf_upload_to_final_result_and_teacher_report(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    response = teacher.post('/api/question-bank/import-pdf', files={
        'file': ('bank.pdf', Path('static/question-bank-template.pdf').read_bytes(), 'application/pdf')})
    assert response.status_code == 200, response.text
    bank = response.json()['items']
    assert len(bank) == 5 and bank[2]['kind'] == 'multiple'
    quiz = publish_exam(teacher, class_id, bank, count=3)
    attempt = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    assert attempt['mode'] == 'mcq' and attempt['total_questions'] == 3
    assert 'is_correct' not in str(attempt) and 'misconception_code' not in str(attempt)
    answers = correct_answers(attempt['id'])
    saved = student.put(f"/api/attempts/{attempt['id']}/draft", json={'answers': answers})
    assert saved.status_code == 200
    resumed = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    assert resumed['questions'] == attempt['questions'] and resumed['answers'] == answers
    assert resumed['deadline'] == attempt['deadline']
    result = student.post(f"/api/attempts/{attempt['id']}/submit", json={'answers': answers}).json()
    assert result['finished'] and result['result']['earned'] == 3
    assert result['questions'] == []
    replay = student.post(f"/api/attempts/{attempt['id']}/submit", json={'answers': {}}).json()
    assert replay['result'] == result['result']
    report = teacher.get(f"/api/teacher/heatmap/{quiz['skill_id']}").json()
    assert report['students'][0]['marks']['score'] == 3
    assert report['students'][0]['marks']['out_of'] == 3


def test_unique_sets_under_concurrent_allocation_and_exhaustion(client):
    teacher, _ = account('teacher')
    class_id = classroom(teacher)
    quiz = publish_exam(teacher, class_id, count=1)
    students = []
    for _ in range(6):
        student, info = account('student')
        enroll(teacher, student, info, class_id)
        students.append(student)
    with ThreadPoolExecutor(max_workers=5) as executor:
        attempts = list(executor.map(lambda s: s.post(f"/api/quizzes/{quiz['id']}/start"), students[:5]))
    assert all(a.status_code == 200 for a in attempts), [a.text for a in attempts]
    sets = {tuple(sorted(q['item_id'] for q in a.json()['questions'])) for a in attempts}
    assert len(sets) == 5
    assert students[-1].post(f"/api/quizzes/{quiz['id']}/start").status_code == 409


def test_invalid_submissions_do_not_finalize_and_ownership_is_enforced(client):
    teacher, student, info, class_id, quiz, attempt = setup_exam()
    outsider, _ = account('student')
    url = f"/api/attempts/{attempt['id']}/submit"
    assert outsider.post(url, json={'answers': {}}).status_code == 403
    assert teacher.post(url, json={'answers': {}}).status_code == 403
    assert student.post(url, json={'answers': {'unknown': ['A']}}).status_code == 422
    qid = attempt['questions'][0]['item_id']
    for picks in [['Z'], ['A', 'A'], [42], 'A']:
        assert student.post(url, json={'answers': {qid: picks}}).status_code == 422
    assert student.post(f"/api/quizzes/{quiz['id']}/start").json()['finished'] is False
    assert student.post(f"/api/attempts/{attempt['id']}/answer", json={'item_id': qid, 'chosen_option': 'A'}).status_code == 422
    assert student.post('/api/question-bank/import-pdf', files={'file': ('bad.pdf', b'bad', 'application/pdf')}).status_code == 403


def test_exact_set_scoring_skips_and_frozen_paper(client):
    teacher, student, info, class_id, quiz, attempt = setup_exam(count=5)
    answers = correct_answers(attempt['id'])
    multi = next(q for q in attempt['questions'] if q['kind'] == 'multiple')
    answers[multi['item_id']] = ['B', 'A']
    single = next(q for q in attempt['questions'] if q['kind'] == 'single')
    assert student.post(f"/api/attempts/{attempt['id']}/submit", json={
        'answers': {single['item_id']: ['A', 'B']}}).status_code == 422
    # Changes to the original item cannot change a frozen assigned paper.
    with SessionLocal() as db:
        item = db.get(Item, single['item_id'])
        for option in item.options:
            option.is_correct = option.label == 'C'
        db.commit()
    answers[single['item_id']] = []
    other = next(q for q in attempt['questions'] if q['kind'] == 'single' and q != single)
    answers[other['item_id']] = ['C']
    result = student.post(f"/api/attempts/{attempt['id']}/submit", json={'answers': answers}).json()['result']
    assert result == {'earned': 3, 'maximum': 5, 'correct': 3, 'wrong': 1, 'skipped': 1, 'percentage': 60.0}


def test_deadline_grades_saved_snapshot_and_simultaneous_submits(client):
    _, student, _, _, quiz, attempt = setup_exam()
    answers = correct_answers(attempt['id'])
    student.put(f"/api/attempts/{attempt['id']}/draft", json={'answers': answers})
    with SessionLocal() as db:
        db.get(QuizAttempt, attempt['id']).deadline = now()-timedelta(seconds=1)
        db.commit()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: student.post(f"/api/attempts/{attempt['id']}/submit", json={'answers': {}}), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()['result'] == responses[1].json()['result']
    assert responses[0].json()['result']['earned'] == 2
    with SessionLocal() as db:
        assert len(list(db.scalars(select(ExamPaper).where(ExamPaper.attempt_id == attempt['id'])))) == 1


def test_pdf_errors_are_actionable_and_no_guessed_key(client):
    import pytest
    teacher, _ = account('teacher')
    assert teacher.post('/api/question-bank/import-pdf', files={'file': ('bad.pdf', b'not a pdf', 'application/pdf')}).status_code == 422
    assert teacher.post('/api/question-bank/import-pdf', files={'file': ('big.pdf', b'%PDF-'+b'0'*(3*1024*1024), 'application/pdf')}).status_code == 413
    with pytest.raises(ValueError, match='valid Answer'):
        parse_questions('1. Question?\nA. Yes\nB. No')
    with pytest.raises(ValueError, match='Scanned PDFs'):
        parse_questions('')


def test_multiple_select_rejects_partial_or_extra_choices_and_cleared_is_skip():
    from app.exams import grade
    question = {'item_id': 'multi', 'kind': 'multiple', 'options': [
        {'id': 'B', 'is_correct': True}, {'id': 'D', 'is_correct': True},
        {'id': 'A', 'is_correct': False}]}
    assert grade([question], {'multi': ['D', 'B']})['earned'] == 1
    assert grade([question], {'multi': ['B']})['wrong'] == 1
    assert grade([question], {'multi': ['B', 'D', 'A']})['wrong'] == 1
    assert grade([question], {'multi': []})['skipped'] == 1


def test_simultaneous_final_submissions_commit_one_result(client):
    _, student, _, _, _, attempt = setup_exam()
    answers = correct_answers(attempt['id'])
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda picks: student.post(
            f"/api/attempts/{attempt['id']}/submit", json={'answers': picks}), [answers, {}]))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()['result'] == responses[1].json()['result']
    assert responses[0].json()['result']['earned'] in (0, 2)


def test_results_read_finalizes_expired_draft(client):
    teacher, student, _, _, quiz, attempt = setup_exam()
    student.put(f"/api/attempts/{attempt['id']}/draft", json={'answers': correct_answers(attempt['id'])})
    with SessionLocal() as db:
        db.get(QuizAttempt, attempt['id']).deadline = now()-timedelta(seconds=1)
        db.commit()
    marks = teacher.get(f"/api/teacher/heatmap/{quiz['skill_id']}").json()['students'][0]['marks']
    assert marks['status'] == 'graded' and marks['score'] == 2


def test_negative_marking_calculation_and_penalty(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    bank = [
        {'item_id': 'eng1', 'skill_id': 'eng', 'stem': 'Antonym of diligent?', 'kind': 'single',
         'options': [{'id': 'A', 'text': 'Lazy', 'is_correct': True}, {'id': 'B', 'text': 'Active', 'is_correct': False}]},
        {'item_id': 'eng2', 'skill_id': 'eng', 'stem': 'Synonyms of fast?', 'kind': 'multiple',
         'options': [{'id': 'A', 'text': 'Quick', 'is_correct': True}, {'id': 'B', 'text': 'Swift', 'is_correct': True}, {'id': 'C', 'text': 'Slow', 'is_correct': False}]},
        {'item_id': 'eng3', 'skill_id': 'eng', 'stem': 'Meaning of benevolent?', 'kind': 'single',
         'options': [{'id': 'A', 'text': 'Kind', 'is_correct': True}, {'id': 'B', 'text': 'Cruel', 'is_correct': False}]},
        {'item_id': 'eng4', 'skill_id': 'eng', 'stem': 'Identify noun:', 'kind': 'single',
         'options': [{'id': 'A', 'text': 'London', 'is_correct': True}, {'id': 'B', 'text': 'Run', 'is_correct': False}]},
    ]
    res = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'English MCQ with Negative Marking',
        'mode': 'mcq',
        'question_count': 4,
        'total_time_s': 600,
        'question_time_s': 30,
        'negative_marks': 0.25,
        'schedule_mode': 'instant',
        'items': bank
    })
    assert res.status_code == 201, res.text
    quiz = res.json()
    attempt = student.post(f"/api/quizzes/{quiz['id']}/start").json()
    assert attempt['negative_marks'] == 0.25
    key = correct_answers(attempt['id'])
    questions = attempt['questions']
    # Q0: correct (+1)
    # Q1: correct (+1)
    # Q2: wrong (-0.25)
    # Q3: skipped (0)
    q0 = questions[0]['item_id']
    q1 = questions[1]['item_id']
    q2 = questions[2]['item_id']
    q3 = questions[3]['item_id']
    wrong_opt = 'B' if key[q2] == ['A'] else 'A'
    submission = {
        q0: key[q0],
        q1: key[q1],
        q2: [wrong_opt],
        q3: []
    }
    result = student.post(f"/api/attempts/{attempt['id']}/submit", json={'answers': submission}).json()['result']
    assert result['correct'] == 2
    assert result['wrong'] == 1
    assert result['skipped'] == 1
    assert result['penalty'] == 0.25
    assert result['earned'] == 1.75
    assert result['percentage'] == 43.75

    heatmap = teacher.get(f"/api/teacher/heatmap/{quiz['skill_id']}").json()
    student_mark = heatmap['students'][0]['marks']
    assert student_mark['score'] == 1.75
    assert '-0.25 per wrong answer' in student_mark['scoring_formula']


def test_calendar_scheduled_modes_and_window_enforcement(client):
    teacher, _ = account('teacher')
    student, info = account('student')
    class_id = classroom(teacher)
    enroll(teacher, student, info, class_id)
    bank = [
        {'item_id': 'q1', 'skill_id': 'eng', 'stem': 'Question 1', 'kind': 'single',
         'options': [{'id': 'A', 'text': 'Yes', 'is_correct': True}, {'id': 'B', 'text': 'No', 'is_correct': False}]},
        {'item_id': 'q2', 'skill_id': 'eng', 'stem': 'Question 2', 'kind': 'single',
         'options': [{'id': 'A', 'text': 'Yes', 'is_correct': True}, {'id': 'B', 'text': 'No', 'is_correct': False}]}
    ]

    # Validation: end_time must be after start_time
    invalid = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'Invalid Schedule', 'mode': 'mcq', 'question_count': 1, 'total_time_s': 300, 'question_time_s': 30,
        'schedule_mode': 'scheduled',
        'start_time': (now() + timedelta(hours=2)).isoformat() + 'Z',
        'end_time': (now() + timedelta(hours=1)).isoformat() + 'Z',
        'items': bank
    })
    assert invalid.status_code == 422

    # Mode 2: Future window (Premature start blocked with 403)
    future_start = now() + timedelta(hours=1)
    future_end = now() + timedelta(hours=3)
    future_quiz = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'Future Scheduled Test', 'mode': 'mcq', 'question_count': 1, 'total_time_s': 300, 'question_time_s': 30,
        'schedule_mode': 'scheduled',
        'start_time': future_start.isoformat() + 'Z',
        'end_time': future_end.isoformat() + 'Z',
        'items': bank
    }).json()
    blocked_early = student.post(f"/api/quizzes/{future_quiz['id']}/start")
    assert blocked_early.status_code == 403
    assert 'Testing window opens' in blocked_early.json()['detail']

    # Mode 2: Active window (starts successfully and deadline respects end_time)
    active_start = now() - timedelta(minutes=10)
    active_end = now() + timedelta(minutes=5)  # 5 min left, less than total_time_s (10 min)
    active_quiz = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'Active Scheduled Test', 'mode': 'mcq', 'question_count': 1, 'total_time_s': 600, 'question_time_s': 30,
        'schedule_mode': 'scheduled',
        'start_time': active_start.isoformat() + 'Z',
        'end_time': active_end.isoformat() + 'Z',
        'items': bank
    }).json()
    attempt = student.post(f"/api/quizzes/{active_quiz['id']}/start")
    assert attempt.status_code == 200
    attempt_data = attempt.json()
    # Deadline should be capped at active_end (approx 5 minutes, not 10 minutes)
    import datetime
    deadline_dt = datetime.datetime.fromisoformat(attempt_data['deadline'].rstrip('Z'))
    assert deadline_dt <= active_end + timedelta(seconds=2)

    # Mode 2: Past window (Attempt blocked with 403)
    past_start = now() - timedelta(hours=3)
    past_end = now() - timedelta(hours=1)
    past_quiz = teacher.post(f'/api/classes/{class_id}/quizzes', json={
        'title': 'Past Scheduled Test', 'mode': 'mcq', 'question_count': 1, 'total_time_s': 300, 'question_time_s': 30,
        'schedule_mode': 'scheduled',
        'start_time': past_start.isoformat() + 'Z',
        'end_time': past_end.isoformat() + 'Z',
        'items': bank
    }).json()
    blocked_late = student.post(f"/api/quizzes/{past_quiz['id']}/start")
    assert blocked_late.status_code == 403
    assert 'window closed' in blocked_late.json()['detail']
