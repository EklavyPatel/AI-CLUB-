"""Real browser teacher-to-student test with a disposable database. Run from repo root."""
import argparse
import json
import os
from pathlib import Path
import socket
import secrets
import subprocess
import sys
import tempfile
import time

import httpx
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=20000)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts'
TEST_PASSWORD=secrets.token_urlsafe(24)


def get_teacher_signup_code():
    code = os.environ.get('TEACHER_SIGNUP_CODE')
    if code:
        return code
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith('TEACHER_SIGNUP_CODE='):
                return line.split('=', 1)[1].strip()
    return 'demo-teacher-code'


TEACHER_SIGNUP_CODE = get_teacher_signup_code()


def register(page, role, email, name, sid=None, teacher_code=None):
    page.locator('#auth-screen').wait_for(timeout=30000)
    page.locator('#auth-toggle').click()
    page.locator('[name=name]').fill(name)
    page.locator(f'[name=role][value={role}]').check()
    page.locator('#auth-form [name=email]').fill(email)
    if role == 'student':
        expect(page.locator('#student-details')).to_be_visible()
        page.locator('[name=sid]').fill(sid or 'DEMO-CSE-001')
        page.locator('[name=branch]').fill('Computer Science')
    else:
        expect(page.locator('#student-details')).to_be_hidden()
    if role == 'teacher':
        expect(page.locator('#teacher-details')).to_be_visible()
        page.locator('[name=teacher_code]').fill(teacher_code or TEACHER_SIGNUP_CODE)
    page.locator('[name=password]').fill(TEST_PASSWORD)
    page.locator('#auth-form button').click()
    expect(page.locator('#account-name')).to_have_text(name)


def run(base):
    ARTIFACTS.mkdir(exist_ok=True)
    tag=str(time.time_ns())
    student_sid = f'CSE-{tag[-6:]}'
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        teacher_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        student_context = browser.new_context(viewport={'width': 1280, 'height': 900})
        teacher = teacher_context.new_page()
        student = student_context.new_page()
        errors = []
        for page in (teacher, student):
            page.on('pageerror', lambda error: errors.append(str(error)))
        teacher.goto(base)
        register(teacher, 'teacher', f'teacher-{tag}@college.example', 'College Teacher')
        teacher.locator('#create-class-form [name=name]').fill('B.Tech · Computer Science')
        teacher.locator('#create-class-form button').click()
        expect(teacher.locator('.class-card h3')).to_have_text('B.Tech · Computer Science')
        teacher.locator('#invite-form [name=email]').fill(f'student-{tag}@college.example')
        teacher.locator('#invite-form button').first.click()
        expect(teacher.locator('#invite-link')).not_to_have_value('')
        invitation = teacher.locator('#invite-link').input_value()
        student.goto(invitation)
        register(student, 'student', f'student-{tag}@college.example', 'College Student', sid=student_sid)
        expect(student.locator('#class-select')).to_contain_text('B.Tech · Computer Science')
        teacher.locator('a[data-page=upload]').click()
        expect(teacher.locator('input[value=instant]')).to_be_checked()
        expect(teacher.locator('input[value=scheduled]')).to_be_visible()
        expect(teacher.locator('select[name=negative_marks]')).to_be_visible()
        teacher.locator('[name=title]').fill('Computer Science · Semester assessment')
        teacher.locator('[name=question_count]').fill('3')
        teacher.locator('#json-file').set_input_files(ROOT/'static/question-bank-template.pdf')
        expect(teacher.locator('[data-key-question]')).to_have_count(20)
        bank = json.loads(teacher.locator('#json-editor').input_value())
        assert len(bank) == 5
        teacher.locator('[name=approved]').check()
        teacher.screenshot(path=str(ARTIFACTS/'teacher-pdf-review.png'), full_page=True)
        teacher.locator('#upload-form [type=submit]').click()
        expect(teacher.locator('#skill-select')).to_contain_text('Semester assessment')
        expect(teacher.locator('#toast')).to_contain_text('Quiz published')
        student.locator('#refresh-button').click()
        expect(student.locator('#skill-select')).to_contain_text('Semester assessment')
        student.locator('a[data-page=quiz]').click()
        student.get_by_role('button', name='Start or resume quiz').click()
        expect(student.locator('.quiz-stem')).to_be_visible()
        answer_text = {q['stem']: [o['text'] for o in q['options'] if o['is_correct']] for q in bank}
        for index in range(3):
            stem = student.locator('.quiz-stem').inner_text()
            for value in answer_text[stem]:
                student.locator('.option').filter(has=student.get_by_text(value, exact=True)).click()
            expect(student.locator('#draft-status')).to_have_text('Draft saved')
            if index < 2:
                student.get_by_role('button', name='Next →', exact=True).click()
        deadline_text = student.locator('#overall-timer').inner_text()
        assert deadline_text != '…'
        student.wait_for_timeout(1500)
        student.reload()
        try:
            expect(student.locator('#account-name')).to_have_text('College Student', timeout=60000)
            student.get_by_role('button', name='Start or resume quiz').click(timeout=60000)
        except Exception:
            student.screenshot(path=str(ARTIFACTS/'reload-error.png'),full_page=True)
            print('Reload page:',student.locator('body').inner_text()[:2500],flush=True)
            raise
        expect(student.locator('[data-exam-option]:checked')).not_to_have_count(0)
        student.screenshot(path=str(ARTIFACTS/'student-assessment.png'), full_page=True)
        student.set_viewport_size({'width': 390, 'height': 844})
        student.screenshot(path=str(ARTIFACTS/'student-mobile.png'), full_page=True)
        assert student.evaluate('document.documentElement.scrollWidth <= innerWidth')
        student.once('dialog', lambda dialog: dialog.accept())
        student.get_by_role('button', name='Submit assessment', exact=True).click()
        expect(student.locator('#page')).to_contain_text('3/3 marks · 100% · 3 correct · 0 wrong · 0 skipped')
        student.screenshot(path=str(ARTIFACTS/'student-result.png'), full_page=True)
        student.get_by_role('button', name='My results').click()
        expect(student.locator('#page')).to_contain_text('3/3 marks')

        # Test student logout and re-login using SID (case-insensitive)
        student.locator('#logout-button').click()
        expect(student.locator('#auth-screen')).to_be_visible()
        student.locator('input[name=role][value=student]').check()
        student.locator('#auth-email-input').fill(student_sid.lower())
        student.locator('[name=password]').fill(TEST_PASSWORD)
        student.locator('#auth-form button').click()
        expect(student.locator('#account-name')).to_have_text('College Student')

        teacher.locator('a[data-page=teacher]').click()
        teacher.locator('#refresh-button').click()
        expect(teacher.locator('tbody')).to_contain_text('College Student')
        expect(teacher.locator('tbody')).to_contain_text('Submitted')
        expect(teacher.locator('tbody')).to_contain_text('3/3')
        expect(teacher.locator('tbody')).to_contain_text(student_sid)
        expect(teacher.locator('tbody')).to_contain_text('Computer Science')
        with teacher.expect_download() as download:
            teacher.get_by_role('button', name='Export CSV').click()
        report = Path(download.value.path()).read_text(encoding='utf-8-sig')
        assert 'SID' in report and 'Branch' in report and student_sid in report and 'Computer Science' in report
        assert '100' in report and '3' in report
        teacher.screenshot(path=str(ARTIFACTS/'teacher-results.png'), full_page=True)

        # Test Teacher removing student from classroom
        teacher.on('dialog', lambda dialog: dialog.accept())
        teacher.locator('button[data-action=remove-student]').first.click()
        expect(teacher.locator('#toast')).to_contain_text('removed from classroom')
        expect(teacher.locator('tbody')).not_to_contain_text('College Student')

        # Verify Admin login is not present on the login/register screen
        student.locator('#logout-button').click()
        expect(student.locator('#auth-screen')).to_be_visible()
        expect(student.locator('input[value=admin]')).to_have_count(0)

        # Student logs back in with SID
        student.locator('input[name=role][value=student]').check()
        student.locator('#auth-email-input').fill(student_sid.lower())
        student.locator('[name=password]').fill(TEST_PASSWORD)
        student.locator('#auth-form button').click()
        expect(student.locator('#account-name')).to_have_text('College Student')

        # Test tab-switch auto-submit feature
        teacher.locator('a[data-page=classes]').click()
        teacher.locator('#invite-form [name=email]').fill(f'student2-{tag}@college.example')
        teacher.locator('#invite-form button').first.click()
        expect(teacher.locator('#invite-link')).not_to_have_value('')
        invitation2 = teacher.locator('#invite-link').input_value()

        student2_context = browser.new_context(viewport={'width': 1280, 'height': 900})
        student2 = student2_context.new_page()
        student2.on('pageerror', lambda error: errors.append(str(error)))
        student2.goto(invitation2)
        register(student2, 'student', f'student2-{tag}@college.example', 'Cheater Tester')
        student2.locator('a[data-page=quiz]').click()
        expect(student2.locator('#page')).to_contain_text('Fullscreen lockdown is active')
        student2.get_by_role('button', name='Start or resume quiz').click()
        expect(student2.locator('.quiz-stem')).to_be_visible()
        expect(student2.locator('.timer-bar')).to_contain_text('Anti-Cheat Active')

        # Verify copy blocking and user-select none
        copy_prevented = student2.evaluate("() => { const e = new Event('copy', { cancelable: true }); return !document.dispatchEvent(e); }")
        assert copy_prevented, "Copy event should be prevented"
        user_select = student2.locator('.quiz-stem').evaluate("el => getComputedStyle(el).userSelect")
        assert user_select == 'none', f"Expected userSelect 'none', got {user_select}"

        # Test 2-strike tab switch anti-cheat flow
        # Strike 1: Warning toast, exam remains active
        student2.evaluate("Object.defineProperty(document, 'hidden', { value: true, writable: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange'));")
        expect(student2.locator('#toast')).to_contain_text('Warning (1/2)')
        expect(student2.locator('.quiz-stem')).to_be_visible()

        # Strike 2: Auto-submits the assessment
        student2.evaluate("document.dispatchEvent(new Event('visibilitychange'));")
        expect(student2.locator('#page')).to_contain_text('Assessment submitted', timeout=15000)
        expect(student2.locator('#toast')).to_contain_text('Tab switch detected')

        assert not errors, errors
        browser.close()
        print('Browser E2E passed: teacher registration, classroom, invitation, PDF review/publication, student assignment, autosave/resume, desktop/mobile, final grading, teacher report, CSV export, student SID login, teacher student removal, admin role removed, copy blocking, and 2-strike tab-switch auto-submit; no page errors.')



if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',help='Run against an existing deployment instead of starting a disposable server')
    args=parser.parse_args()
    if args.base_url:
        run(args.base_url.rstrip('/'))
        raise SystemExit(0)
    with tempfile.TemporaryDirectory(prefix='college-browser-') as temp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'DATABASE_URL': f'sqlite:///{temp}/browser.db', 'TEACHER_SIGNUP_CODE': TEACHER_SIGNUP_CODE}
        log = open(Path(temp)/'server.log', 'w+')
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--port', str(port)],
                                  cwd=ROOT, env=env, stdout=log, stderr=log)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    if httpx.get(base+'/api/ready').status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                if server.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read())
                time.sleep(.1)
            else:
                raise RuntimeError('Preview server did not become ready')
            run(base)
        finally:
            server.terminate()
            server.wait(timeout=10)
            log.close()
