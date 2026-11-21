"""Controlled test of already-enrolled students. Synthetic session seeding is explicit.
Prepare writes short-lived test session secrets to a 0600 temporary file. Run reads
and removes it immediately. Reports never contain passwords or session tokens.
"""
import argparse
import asyncio
from collections import Counter
from contextlib import AsyncExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import time

import httpx

ARTIFACTS = Path(__file__).resolve().parents[1] / 'artifacts'


def save_private(data, suffix):
    fd, path = tempfile.mkstemp(prefix='college-load-', suffix=suffix)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f)
    return path


def prepare(base, students):
    tag = str(time.time_ns())
    with httpx.Client(base_url=base, timeout=60) as client:
        r = client.post('/api/auth/register', json={'name': 'Capacity Test Teacher',
            'email': f'capacity-teacher-{tag}@college.example', 'password': secrets.token_urlsafe(24), 'role': 'teacher'})
        r.raise_for_status()
        teacher_id = r.json()['id']
        r = client.post('/api/classes', json={'name': f'Capacity test · {students} synthetic students'})
        r.raise_for_status()
        class_id = r.json()['id']
        items = [{'item_id': f'load{i}', 'skill_id': 'capacity', 'kind': 'single',
                  'stem': f'Capacity test question {i+1}: choose the correct option.',
                  'options': [{'id': 'A', 'text': 'Correct answer', 'is_correct': True},
                              {'id': 'B', 'text': 'Alternative B', 'is_correct': False},
                              {'id': 'C', 'text': 'Alternative C', 'is_correct': False},
                              {'id': 'D', 'text': 'Alternative D', 'is_correct': False}]} for i in range(60)]
        r = client.post(f'/api/classes/{class_id}/quizzes', json={'title': 'Capacity test · 20 questions',
            'mode': 'mcq', 'question_count': 20, 'total_time_s': 3600, 'question_time_s': 180, 'items': items})
        r.raise_for_status()
        quiz_id = r.json()['id']
    records = []
    seed = []
    for i in range(students):
        user_id, session = secrets.token_hex(16), secrets.token_urlsafe(32)
        records.append({'id': user_id, 'session': session})
        seed.append({'id': user_id, 'email': f'capacity-student-{tag}-{i}@college.example',
                     'token_hash': hashlib.sha256(session.encode()).hexdigest()})
    public = {'base': base, 'students': students, 'teacher_id': teacher_id, 'class_id': class_id, 'quiz_id': quiz_id,
              'user_ids': [r['id'] for r in records], 'created_at': time.time()}
    ARTIFACTS.mkdir(exist_ok=True)
    meta_path = ARTIFACTS / f'capacity-test-{tag}-records.json'
    meta_path.write_text(json.dumps(public, indent=2))
    auth_path = save_private({**public, 'records': records}, '.auth.json')
    seed_path = save_private({'class_id': class_id, 'expires_ms': int(time.time()*1000)+7200000, 'students': seed}, '.seed.json')
    print(json.dumps({'auth_path': auth_path, 'seed_path': seed_path, 'records_path': str(meta_path),
                      'students': students, 'class_id': class_id, 'quiz_id': quiz_id}), flush=True)


def percentile(values, p):
    values = sorted(values)
    return round(values[max(0, math.ceil(len(values)*p)-1)], 3) if values else None


async def run(auth_path):
    path = Path(auth_path)
    data = json.loads(path.read_text())
    path.unlink()
    base, students = data['base'], data['records']
    report = {'base': base, 'concurrent_clients': len(students), 'questions_per_student': 20,
              'scenario': 'Pre-enrolled, authenticated students: simultaneous start, three synchronized autosave bursts, simultaneous final submission; no client retries.',
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'phases': []}
    papers = {}
    report['transport']='Three warmed HTTP/2 connections, 100 independent student sessions per connection'
    for i,student in enumerate(students):
        student['transport']=i%3
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=120)
    async with AsyncExitStack() as stack:
        clients=[await stack.enter_async_context(httpx.AsyncClient(base_url=base, http2=True, timeout=httpx.Timeout(90, connect=30, pool=90), limits=limits)) for _ in range(3)]
        warmed=await asyncio.gather(*[client.get('/api/health') for client in clients])
        if any(r.status_code!=200 or r.http_version!='HTTP/2' for r in warmed):
            raise RuntimeError('HTTP/2 transport warm-up failed; do not report a 300-concurrent test.')
        async def phase(name, action, fraction=None):
            ready = asyncio.Event()
            async def one(student):
                await ready.wait()
                start = time.perf_counter()
                try:
                    client=clients[student['transport']]
                    headers = {'Cookie': 'btn_session='+student['session']}
                    if action == 'start':
                        response = await client.post(f"/api/quizzes/{data['quiz_id']}/start", headers=headers)
                    else:
                        paper = papers[student['id']]
                        selected = paper['questions'][:int(20*fraction)] if fraction else paper['questions']
                        answers = {q['item_id']: ['A'] for q in selected}
                        response = await client.request('PUT' if action == 'draft' else 'POST',
                            f"/api/attempts/{paper['id']}/{'draft' if action == 'draft' else 'submit'}",
                            headers=headers, json={'answers': answers})
                    elapsed = time.perf_counter()-start
                    if response.status_code != 200:
                        return {'ok': False, 'status': response.status_code, 'seconds': elapsed,
                                'detail': response.text[:180]}
                    payload = response.json()
                    if action == 'start':
                        assert len(payload['questions']) == 20 and not payload['finished']
                        papers[student['id']] = payload
                    elif action == 'submit':
                        assert payload['finished'] and payload['result']['earned'] == 20 and payload['result']['maximum'] == 20
                    else:
                        assert len(payload['answers']) == int(20*fraction)
                    return {'ok': True, 'status': 200, 'seconds': elapsed,'http_version':response.http_version}
                except Exception as exc:
                    return {'ok': False, 'status': type(exc).__name__, 'seconds': time.perf_counter()-start,
                            'detail': type(exc).__name__}
            tasks = [asyncio.create_task(one(s)) for s in students]
            await asyncio.sleep(0)
            start = time.perf_counter()
            ready.set()
            results = await asyncio.gather(*tasks)
            timings = [r['seconds'] for r in results]
            good = sum(r['ok'] for r in results)
            summary = {'phase': name, 'requests': len(results), 'successful': good, 'failed': len(results)-good,
                'status_counts': dict(Counter(str(r['status']) for r in results)), 'protocols':dict(Counter(r.get('http_version','unknown') for r in results)),
                'duration_s': round(time.perf_counter()-start, 3), 'p50_s': percentile(timings,.5),
                'p95_s': percentile(timings,.95), 'p99_s': percentile(timings,.99), 'max_s': round(max(timings),3),
                'failure_samples': [r for r in results if not r['ok']][:5]}
            report['phases'].append(summary)
            print(json.dumps(summary), flush=True)
            return good == len(students)
        if await phase('Simultaneous start', 'start'):
            signatures = {tuple(sorted(q['item_id'] for q in p['questions'])) for p in papers.values()}
            report['distinct_question_sets'] = len(signatures)
            if len(signatures) != len(students):
                report['failure'] = 'Duplicate assigned question sets'
            else:
                for index, fraction in enumerate([.25, .5, 1], 1):
                    await asyncio.sleep(1)
                    if not await phase(f'Autosave burst {index}', 'draft', fraction):
                        break
                else:
                    await asyncio.sleep(1)
                    await phase('Simultaneous final submission', 'submit')
        report['passed'] = len(report['phases']) == 5 and all(p['failed']==0 for p in report['phases']) and report.get('distinct_question_sets') == len(students)
    report_path = ARTIFACTS/'capacity-300-report.json'
    report_path.write_text(json.dumps(report,indent=2))
    print(json.dumps({'passed': report['passed'], 'report': str(report_path)}), flush=True)


def renew(records_path):
    data=json.loads(Path(records_path).read_text())
    records=[]
    seed=[]
    for uid in data['user_ids']:
        session=secrets.token_urlsafe(32)
        records.append({'id':uid,'session':session})
        seed.append({'id':uid,'token_hash':hashlib.sha256(session.encode()).hexdigest()})
    auth=save_private({**data,'records':records},'.auth.json')
    seed_path=save_private({'sessions_only':True,'expires_ms':int(time.time()*1000)+7200000,'students':seed},'.seed.json')
    print(json.dumps({'auth_path':auth,'seed_path':seed_path,'students':len(records)}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--base-url',required=True)
    p.add_argument('--students',type=int,default=300)
    p = sub.add_parser('renew')
    p.add_argument('--records-file',required=True)
    p = sub.add_parser('run')
    p.add_argument('--auth-file',required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        if not 1 <= args.students <= 300:
            parser.error('Use 1 to 300 students for this bounded test.')
        prepare(args.base_url.rstrip('/'),args.students)
    elif args.command == 'renew':
        renew(args.records_file)
    else:
        asyncio.run(run(args.auth_file))
