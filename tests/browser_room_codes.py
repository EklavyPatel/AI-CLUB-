"""Check the teacher code and student join UI on a running application."""
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_e2e import register, ARTIFACTS

expect.set_options(timeout=60000)
parser = argparse.ArgumentParser()
parser.add_argument('--base-url', required=True)
args = parser.parse_args()
base = args.base_url.rstrip('/')
tag = str(time.time_ns())
ARTIFACTS.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    teacher_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    student_context = browser.new_context(viewport={'width': 390, 'height': 844})
    teacher = teacher_context.new_page()
    student = student_context.new_page()
    errors = []
    for page in (teacher, student):
        page.on('pageerror', lambda e: errors.append(str(e)))
    teacher.goto(base)
    register(teacher, 'teacher', f'room-teacher-{tag}@college.example', 'Room Code Teacher')
    teacher.locator('#create-class-form [name=name]').fill('Room code test classroom')
    teacher.locator('#create-class-form button').click()
    expect(teacher.locator('.room-code')).to_have_text(__import__('re').compile(r'^[A-Z0-9]{8}$'))
    code = teacher.locator('.room-code').inner_text()
    teacher_id = teacher.evaluate('async()=> (await (await fetch("/api/auth/me")).json()).id')
    class_id = teacher.locator('[data-action=open-class]').get_attribute('data-class-id')
    Path(ARTIFACTS/'room-code-test-records.json').write_text(json.dumps({'teacher_id':teacher_id,'class_id':class_id}))
    teacher.screenshot(path=str(ARTIFACTS/'classroom-code-teacher.png'), full_page=True)
    teacher.reload(wait_until="domcontentloaded")
    expect(teacher.locator('.room-code')).to_have_text(code)
    student.goto(base)
    register(student, 'student', f'room-student-{tag}@college.example', 'Room Code Student')
    student_id = student.evaluate('async()=> (await (await fetch("/api/auth/me")).json()).id')
    Path(ARTIFACTS/'room-code-test-records.json').write_text(json.dumps({'teacher_id':teacher_id,'student_id':student_id,'class_id':class_id}))
    expect(student.locator('#join-code-form')).to_be_visible()
    student.locator('#join-code-form [name=code]').fill('00000000')
    student.locator('#join-code-form button').click()
    expect(student.locator('#error')).to_contain_text('Classroom code not found')
    student.locator('#join-code-form [name=code]').fill(code.lower())
    student.locator('#join-code-form button').click()
    expect(student.locator('.class-card h3')).to_have_text('Room code test classroom')
    expect(student.locator('#class-select')).to_contain_text('Room code test classroom')
    expect(student.locator('.room-code')).to_have_count(0)
    student.locator('#join-code-form [name=code]').fill(code)
    student.locator('#join-code-form button').click()
    expect(student.locator('.class-card')).to_have_count(1)
    student.reload(wait_until="domcontentloaded")
    expect(student.locator('.class-card h3')).to_have_text('Room code test classroom')
    assert student.evaluate('document.documentElement.scrollWidth <= innerWidth')
    student.screenshot(path=str(ARTIFACTS/'classroom-code-student.png'), full_page=True)
    roster = teacher.evaluate('async id=>await (await fetch(`/api/classes/${id}/students`)).json()', class_id)
    assert len(roster)==1 and roster[0]['id']==student_id, roster
    assert not errors, errors
    browser.close()
    print('Room-code browser check passed: teacher sees a persistent 8-character code; student joins with lowercase code, invalid codes fail, repeated joins are safe, refresh preserves enrollment and the teacher roster updates; mobile layout has no overflow.')
