# Fast MCQ grading for an existing web application

Use an answer key approved when the test is published. Each student selects options and submits once. The server compares stable option IDs, adds the marks and returns a single result. Students only submit their choices. The scoring path needs no AI calls or written explanations.

## Research and scoring policy

The 1EdTech QTI standard defines a match_correct template for binary grading and a separate map_response template for mapped scores, including partial credit. Moodle documents both configurable multiple-choice grading and an all-or-nothing multiple-choice question type. These sources support exact matching as a practical policy for objective tests. They do not prescribe the marks for your exam.

- [1EdTech QTI 3 Beginner’s Guide, section 3.5](https://www.imsglobal.org/spec/qti/v3p0/guide)
- [Moodle multiple-choice grading](https://docs.moodle.org/501/en/Multichoice_Questions)
- [Moodle all-or-nothing multiple choice](https://docs.moodle.org/401/en/All_or_nothing_multiple_choice_question_type)

For a new test, use +1 for a correct response and 0 for wrong or skipped responses. Preserve the published marking policy for existing tests. If an exam specifies negative marking, store the wrong-answer deduction as a positive amount. A skipped question earns zero. For multi-select, enable exact-set scoring only on tests that award full credit for selecting every correct option and no extra options. Existing partial-credit items should retain their original scorer.

## Reference implementation

This Python function can sit behind an existing submit endpoint or be translated directly to another backend language. The server supplies the key for the exact questions assigned to this attempt. Each entry contains the question type, allowed option IDs as a set, correct IDs as a set, full marks and deduction. Store marks as integers in the smallest supported unit, for example 100 units per mark for a quarter-mark penalty. Validate keys at publication: unique IDs, nonempty correct set within allowed IDs, exactly one correct ID for single choice, positive full marks and nonnegative deductions.

```python
def grade_mcqs(key, answers):
    # answers maps question IDs to lists of selected option IDs.
    if not isinstance(answers, dict) or answers.keys() - key.keys():
        raise ValueError("Invalid submission or unknown question")

    result = dict(earned=0, maximum=0, correct=0, wrong=0, skipped=0)
    for qid, (kind, options, correct_ids, marks, deduction) in key.items():
        picks = answers.get(qid, [])
        if not isinstance(picks, list) or len(picks) > len(options):
            raise ValueError(f"Invalid selection for {qid}")
        if any(not isinstance(pick, str) for pick in picks):
            raise ValueError(f"Invalid option ID for {qid}")
        chosen = set(picks)
        if len(chosen) != len(picks) or not chosen <= options:
            raise ValueError(f"Duplicate or unknown option for {qid}")
        if kind == "single" and len(chosen) > 1:
            raise ValueError(f"Multiple selections for {qid}")

        result["maximum"] += marks
        if not chosen:
            result["skipped"] += 1
        elif chosen == correct_ids:
            result["correct"] += 1
            result["earned"] += marks
        else:
            result["wrong"] += 1
            result["earned"] -= deduction
    return result
```

## Integrating with the existing app

1. At test publication, freeze the answer key and marking rules. Bind each attempt to that version and its assigned questions. For legacy keys stored as letters or indices, map them through the original option order before shuffling. If that order cannot be recovered, flag the item for review.
2. In the MCQ form, keep radio buttons or checkboxes and remove any required reasoning field from both client and server validation. Submit the final selection using stable IDs. Clearing a choice should submit an empty selection. If the app uses autosave, grade the complete final snapshot.
3. In the existing submission handler, authenticate the student and check ownership. Lock the attempt in a transaction. If it is already graded, return its saved result. Otherwise check eligibility and deadline using the existing rules. Load the assigned key in one batch. Reject malformed submissions before saving a grade. Keep the key on the server.
4. Score the MCQ portion in one pass. Save the final selections and result atomically with one result per attempt. Return the summary only. For a mixed test, identify this as the MCQ subtotal until the other sections are graded. Apply an exam-wide minimum score only if the published rules require it.
5. Render one line for the student, for example **17/20 marks · 85% · 17 correct · 2 wrong · 1 skipped**. Compute percentage from earned / maximum × 100 using the final marking policy. Display it only when the maximum is positive.

## Verification before release

| Case | Expected result |
|---|---|
| A single-choice option moves from position 2 to 4 after shuffling | Same option ID earns the same marks |
| Multi-select key is B and D | D+B earns full marks. B alone or B+D+A earns the wrong-answer score |
| Student clears their selection | Skipped, zero marks |
| 8 correct, 1 wrong, 1 skipped with +1 and −0.25 | 7.75/10 marks, 77.5% |
| Unknown ID, duplicate selection or two choices on single-answer item | Validation error and no final grade saved |
| Two submissions arrive together | Both receive the same committed result |
| Teacher edits a question after the test begins | Attempt uses its assigned version |

With a prepared answer key and hash sets, expected scoring time is O(Q + S), where Q is the number of assigned questions and S the number of submitted selections. Single-choice grading is O(Q). Database and network time are additional. For rollout, replay previously marked attempts under their original rules and compare totals. Measure submission latency on the actual app, including database writes, with the expected number of students submitting together. This report does not establish a production latency or capacity figure.
