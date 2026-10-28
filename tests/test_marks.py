from tests.test_diagnostics import make_learner, submit


def test_marks_distinguish_confidence(seeded):
    secure = seeded.get('/api/marks/student_101/python_recursion').json()
    fragile = seeded.get('/api/marks/student_103/python_recursion').json()
    assert secure['score'] == fragile['score'] == 4
    assert secure['secure_marks'] == 4
    assert fragile['secure_marks'] == 1
    assert fragile['fragile_marks'] == 3


def test_marks_latest_answer_and_probes(seeded):
    learner = 'marks_retake'
    make_learner(learner)
    initial = seeded.get(f'/api/marks/{learner}/python_recursion').json()
    assert initial['score'] == 0 and initial['unanswered'] == 4
    result = submit(seeded, learner, 'q1', 'B', 'Sure').json()
    submit(seeded, learner, result['probe_item']['item_id'], 'A', 'Sure', probe=True, parent='q1')
    marks = seeded.get(f'/api/marks/{learner}/python_recursion').json()
    assert marks['score'] == 0 and marks['answered'] == 1
    assert marks['wrong_by_story'] == {'missed_condition': 1}
    submit(seeded, learner, 'q1', 'A', 'Unsure')
    marks = seeded.get(f'/api/profile/{learner}/python_recursion').json()['marks']
    assert marks['score'] == 1 and marks['fragile_marks'] == 1
    assert marks['wrong'] == 0 and marks['unanswered'] == 3


def test_empty_skill(seeded):
    assert seeded.get('/api/marks/nobody/unknown').status_code == 404


def test_reject_invalid_probe_and_skill(seeded):
    assert submit(seeded, 'invalid_probe', 'q1', 'A', 'Sure', probe=True).status_code == 422
    assert submit(seeded, 'invalid_probe', 'q1_probe', 'A', 'Sure').status_code == 422
    result = submit(seeded, 'invalid_probe', 'q1', 'B', 'Sure').json()
    assert submit(seeded, 'no_parent', result['probe_item']['item_id'], 'A', 'Sure', probe=True).status_code == 422
    payload = dict(learner_id='wrong_skill', item_id='q1', skill_id='other', chosen_option='A', confidence='Sure', time_ms=1000)
    assert seeded.post('/api/submit', json=payload).status_code == 410
