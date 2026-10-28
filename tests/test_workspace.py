from tests.test_diagnostics import make_learner, submit


def test_review_latest_answer_without_answer_key(seeded):
    learner = 'review_student'
    make_learner(learner)
    assert seeded.get(f'/api/review/{learner}/python_recursion').json() == []
    submit(seeded, learner, 'q2', 'B', 'Guessing')
    submit(seeded, learner, 'q2', 'A', 'Sure')
    rows = seeded.get(f'/api/review/{learner}/python_recursion').json()
    assert len(rows) == 1
    assert rows[0]['attempts'] == 2
    assert rows[0]['correct'] is True
    assert rows[0]['chosen_option'] == 'A'
    assert rows[0]['story'] == 'secure'
    assert 'options' not in rows[0] and 'misconception_code' not in rows[0]


def test_retake_removes_old_misconception_from_heatmap(seeded):
    learner = 'heatmap_retake'
    before = seeded.get('/api/teacher/heatmap/python_recursion').json()['misconception_heatmap'].get('confusing_base_case_with_zero', 0)
    result = submit(seeded, learner, 'q1', 'B', 'Sure').json()
    submit(seeded, learner, result['probe_item']['item_id'], 'B', 'Sure', probe=True, parent='q1')
    during = seeded.get('/api/teacher/heatmap/python_recursion').json()['misconception_heatmap']
    assert during['confusing_base_case_with_zero'] == before + 1
    submit(seeded, learner, 'q1', 'A', 'Sure')
    after = seeded.get('/api/teacher/heatmap/python_recursion').json()['misconception_heatmap']
    assert after.get('confusing_base_case_with_zero', 0) == before


def test_uncertain_probe_does_not_prove_a_slip(seeded):
    learner = 'uncertain_probe'
    result = submit(seeded, learner, 'q1', 'B', 'Sure').json()
    submit(seeded, learner, result['probe_item']['item_id'], 'A', 'Guessing', probe=True, parent='q1')
    profile = seeded.get(f'/api/profile/{learner}/python_recursion').json()
    assert profile['stories'] == {'unresolved': 1}
    assert profile['evidence_needed']


def test_workspace_assets(client):
    assert client.get('/').status_code == 200
    assert '/static/app.js' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/styles.css').status_code == 200
