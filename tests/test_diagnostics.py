def submit(client, learner, item, option, conf, secs=20, probe=False, parent=None):
    return client.post("/api/submit", json={
        "learner_id": learner, "item_id": item, "skill_id": "python_recursion",
        "chosen_option": option, "confidence": conf, "time_ms": secs * 1000,
        "is_probe": probe, "parent_item_id": parent,
    })


def test_student_items_do_not_leak_answers(seeded):
    items = seeded.get("/api/items/python_recursion").json()
    assert len(items) == 4
    for it in items:
        for o in it["options"]:
            assert set(o) == {"id", "text"}


def test_cohort_states(seeded):
    d = seeded.get("/api/teacher/heatmap/python_recursion").json()
    assert d["total_students"] == 10
    assert d["state_distribution"] == {
        "Secure": 2, "Lucky / Fragile": 2, "Careless Slip": 3, "Deep Misconception": 3}
    assert d["misconception_heatmap"]["confusing_base_case_with_zero"] == 2
    assert d["misconception_heatmap"]["missing_termination_belief"] == 1


def test_same_wrong_answer_different_stories(seeded):
    slip = seeded.get("/api/profile/student_105/python_recursion").json()
    deep = seeded.get("/api/profile/student_106/python_recursion").json()
    assert slip["stories"].get("missed_condition") == 1
    assert slip["state"] == "Careless Slip"
    assert deep["stories"].get("mistaken_rule") == 2
    assert deep["state"] == "Deep Misconception"
    assert deep["dominant_misconception"] == "confusing_base_case_with_zero"


def test_ran_out_of_time_story(seeded):
    p = seeded.get("/api/profile/student_109/python_recursion").json()
    assert p["stories"].get("rushed") == 2
    assert p["state"] == "Careless Slip"


def test_confident_error_without_probe_is_unresolved(seeded):
    r = submit(seeded, "fresh_learner", "q1", "B", "Sure").json()
    assert r["trigger_probe"] is True
    assert r["story"] == "unresolved"
    p = seeded.get("/api/profile/fresh_learner/python_recursion").json()
    assert p["evidence_needed"]
    # answering the probe correctly resolves the story as a slip
    submit(seeded, "fresh_learner", r["probe_item"]["item_id"], "A", "Sure", probe=True, parent="q1")
    p = seeded.get("/api/profile/fresh_learner/python_recursion").json()
    assert p["stories"].get("missed_condition") == 1


def test_validation(seeded):
    assert submit(seeded, "x", "q1", "Z", "Sure").status_code == 422
    assert submit(seeded, "x", "nope", "A", "Sure").status_code == 404
    bad = [{"item_id": "bad", "skill_id": "s", "stem": "?",
            "options": [{"id": "A", "text": "x"}, {"id": "B", "text": "y"}]}]
    assert seeded.post("/api/items/bulk", json=bad).status_code == 422
