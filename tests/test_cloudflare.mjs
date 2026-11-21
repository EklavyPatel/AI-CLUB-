import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker from '../cloudflare/worker.mjs';
const sqlite=new DatabaseSync(':memory:');
sqlite.exec('PRAGMA foreign_keys=ON;'+readFileSync('cloudflare/schema.sql','utf8'));
const DB={withSession(){return this},prepare(sql){let params=[];const prepared=sqlite.prepare(sql.replaceAll('""', "''"));return {bind(...values){params=values;return this},async first(){return prepared.get(...params)||null},async all(){return {results:prepared.all(...params)}},async run(){const result=prepared.run(...params);return {meta:{changes:Number(result.changes)}}}}},async batch(statements){sqlite.exec('BEGIN');try{const results=[];for(const s of statements)results.push(await s.run());sqlite.exec('COMMIT');return results}catch(e){sqlite.exec('ROLLBACK');throw e}}};
const TEACHER_CODE = process.env.TEACHER_SIGNUP_CODE || 'mock-teacher-secret-code';
const env={DB,API_TOKEN:'test-worker-secret',TEACHER_SIGNUP_CODE:TEACHER_CODE},base='https://test.invalid';
async function request(path,method='GET',body,session=''){
 const headers={authorization:'Bearer test-worker-secret','content-type':'application/json',cookie:session,'x-site-protocol':'http'};
 const response=await worker.fetch(new Request(base+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)}),env);
 return {status:response.status,data:await response.json(),cookie:response.headers.get('set-cookie')?.split(';')[0]};
}
async function register(role,n,extra={}){
  const payload={email:`${role}${n}@college.example`,name:`${role} ${n}`,role,password:'integration-test-password',...extra};
  if(role==='teacher'&&payload.teacher_code===undefined)payload.teacher_code=TEACHER_CODE;
  const r=await request('/api/auth/register','POST',payload);
  assert.equal(r.status,200,JSON.stringify(r.data));
  return r;
}

// 1. Verify invalid or missing teacher code returns 403
assert.equal((await request('/api/auth/register','POST',{email:'badteacher@college.example',name:'Bad Teacher',role:'teacher',password:'integration-test-password',teacher_code:'wrong-code'})).status, 403);
assert.equal((await request('/api/auth/register','POST',{email:'nocodeteacher@college.example',name:'No Code Teacher',role:'teacher',password:'integration-test-password'})).status, 403);

// 2. Verify admin role is rejected with 422
assert.equal((await request('/api/auth/register','POST',{email:'admin@college.example',name:'Admin User',role:'admin',password:'integration-test-password'})).status, 422);

const teacher=await register('teacher',1),student=await register('student',1),other=await register('student',2);
// Identity updates require a successful student login and persist across blank sign-ins.
const identity={email:student.data.email,password:'integration-test-password',role:'student',sid:'  CSE001  ',branch:' Computer Science '};
assert.equal((await request('/api/auth/login','POST',{...identity,password:'incorrect-password'})).status,401);
assert.equal((await request('/api/auth/me','GET',undefined,student.cookie)).data.sid,'');
const identified=await request('/api/auth/login','POST',identity);
assert.equal(identified.data.sid,'CSE001');assert.equal(identified.data.branch,'Computer Science');
const retained=await request('/api/auth/login','POST',{...identity,sid:'',branch:''});
assert.equal(retained.data.sid,'CSE001');assert.equal(retained.data.branch,'Computer Science');
assert.equal((await request('/api/auth/login','POST',{...identity,sid:'x'.repeat(65)})).status,422);

// 3. Verify duplicate SID returns 409 (case-insensitive) on register and login
assert.equal((await request('/api/auth/register','POST',{email:'dupstudent@college.example',name:'Dup Student',role:'student',password:'integration-test-password',sid:'cse001'})).status, 409);
assert.equal((await request('/api/auth/login','POST',{email:other.data.email,password:'integration-test-password',role:'student',sid:'cse001'})).status, 409);

assert.equal((await request('/api/ready')).status,200);
assert.equal((await request('/api/classes')).status,401);
const c=await request('/api/classes','POST',{name:'Computer Science'},teacher.cookie);assert.equal(c.status,201);const classId=c.data.id;
assert.equal((await request('/api/classes','POST',{name:'No'},student.cookie)).status,403);
const roomCode=c.data.join_code;
assert.match(roomCode,/^[A-Z0-9]{8}$/);
assert.equal((await request('/api/classes','GET',undefined,teacher.cookie)).data[0].join_code,roomCode);
assert.equal((await request('/api/classes/join','POST',{code:roomCode},teacher.cookie)).status,403);
assert.equal((await request('/api/classes/join','POST',{code:'00000000'},other.cookie)).status,404);
assert.equal((await request('/api/classes/join','POST',{code:'short'},other.cookie)).status,422);
assert.equal((await request('/api/classes/join','POST',{code:roomCode})).status,401);
for(let i=0;i<2;i++)assert.equal((await request('/api/classes/join','POST',{code:' '+roomCode.toLowerCase()+' '},other.cookie)).status,200);
assert.deepEqual((await request('/api/classes','GET',undefined,other.cookie)).data,[{id:classId,name:'Computer Science'}]);
assert.equal(sqlite.prepare('SELECT count(*) AS n FROM memberships WHERE class_id=? AND user_id=?').get(classId,other.data.id).n,1);
// Existing classrooms receive a code without a schema rewrite or data reset.
sqlite.prepare('INSERT INTO classes(id,name,teacher_id) VALUES(?,?,?)').run('legacy-room','Existing class',teacher.data.id);
const existing=(await request('/api/classes','GET',undefined,teacher.cookie)).data.find(c=>c.id==='legacy-room');
assert.match(existing.join_code,/^[A-Z0-9]{8}$/);
assert.notEqual(existing.join_code,roomCode);

for(const user of [student,other]){
 const inv=await request(`/api/classes/${classId}/invitations`,'POST',{email:user.data.email},teacher.cookie);assert.equal(inv.status,201);
 if(user===student)assert.equal((await request('/api/invitations/accept','POST',{token:inv.data.token},other.cookie)).status,403);
 assert.equal((await request('/api/invitations/accept','POST',{token:inv.data.token},user.cookie)).status,200);
 assert.equal((await request('/api/invitations/accept','POST',{token:inv.data.token},user.cookie)).status,422);
}
const items=Array.from({length:5},(_,i)=>({item_id:'q'+i,stem:'Question '+i,kind:i===0?'multiple':'single',options:[{id:'A',text:'Yes',is_correct:true},{id:'B',text:'Maybe',is_correct:i===0},{id:'C',text:'No',is_correct:false}]}));
const q=await request(`/api/classes/${classId}/quizzes`,'POST',{title:'Semester test',question_count:3,total_time_s:300,items},teacher.cookie);assert.equal(q.status,201,JSON.stringify(q.data));
const quizId=q.data.id,skill=q.data.skill_id;
const start=await request(`/api/quizzes/${quizId}/start`,'POST',undefined,student.cookie);assert.equal(start.status,200,JSON.stringify(start.data));
assert.equal(start.data.negative_marks, 0);
const second=await request(`/api/quizzes/${quizId}/start`,'POST',undefined,other.cookie);assert.equal(second.status,200);
assert.notDeepEqual(new Set(start.data.questions.map(q=>q.item_id)),new Set(second.data.questions.map(q=>q.item_id)));
assert.ok(!JSON.stringify(start.data).includes('is_correct'));
assert.equal((await request(`/api/attempts/${start.data.id}/submit`,'POST',{answers:{}},other.cookie)).status,403);
assert.equal((await request(`/api/attempts/${start.data.id}/submit`,'POST',{answers:{unknown:['A']}},student.cookie)).status,422);
const stored=JSON.parse(sqlite.prepare('SELECT questions FROM attempts WHERE id=?').get(start.data.id).questions);
const answers=Object.fromEntries(stored.map(q=>[q.item_id,q.options.filter(o=>o.is_correct).map(o=>o.id)]));
assert.equal((await request(`/api/attempts/${start.data.id}/draft`,'PUT',{answers},student.cookie)).status,200);
const resumed=await request(`/api/quizzes/${quizId}/start`,'POST',undefined,student.cookie);assert.deepEqual(resumed.data.questions,start.data.questions);assert.deepEqual(resumed.data.answers,answers);assert.equal(resumed.data.deadline,start.data.deadline);
const result=await request(`/api/attempts/${start.data.id}/submit`,'POST',{answers},student.cookie);assert.equal(result.data.result.earned,3);assert.ok(result.data.finished);
assert.deepEqual((await request(`/api/attempts/${start.data.id}/submit`,'POST',{answers:{}},student.cookie)).data.result,result.data.result);
const report=await request(`/api/teacher/heatmap/${skill}`,'GET',undefined,teacher.cookie);assert.equal(report.status,200);assert.equal(report.data.students.find(s=>s.learner_id===student.data.id).sid,'CSE001');assert.equal(report.data.students.find(s=>s.learner_id===student.data.id).branch,'Computer Science');assert.equal(report.data.students.find(s=>s.learner_id===student.data.id).marks.score,3);
assert.equal((await request(`/api/teacher/heatmap/${skill}`,'GET',undefined,student.cookie)).status,403);
assert.equal((await request(`/api/profile/${other.data.id}/${skill}`,'GET',undefined,student.cookie)).status,403);
// Deadline rejects late choices and uses only the last saved snapshot.
sqlite.prepare('UPDATE attempts SET deadline_ms=0 WHERE id=?').run(second.data.id);
const expired=await request(`/api/attempts/${second.data.id}/submit`,'POST',{answers},other.cookie);assert.equal(expired.data.result.earned,0);assert.equal(expired.data.result.skipped,3);
// Negative marking and Calendar scheduling checks on Cloudflare Worker
const scheduledQuiz=await request(`/api/classes/${classId}/quizzes`,'POST',{title:'Scheduled assessment',question_count:2,total_time_s:300,negative_marks:0.25,schedule_mode:'scheduled',start_time:new Date(Date.now()+3600000).toISOString(),end_time:new Date(Date.now()+7200000).toISOString(),items:items.slice(0,3)},teacher.cookie);
assert.equal(scheduledQuiz.status,201);
assert.equal(scheduledQuiz.data.negative_marks,0.25);
assert.equal(scheduledQuiz.data.schedule_mode,'scheduled');
// Premature attempt returns 403
const premature=await request(`/api/quizzes/${scheduledQuiz.data.id}/start`,'POST',undefined,student.cookie);
assert.equal(premature.status,403);

// Instant quiz with negative marking
const negQuiz=await request(`/api/classes/${classId}/quizzes`,'POST',{title:'English MCQ Negative Marking',question_count:2,total_time_s:300,negative_marks:0.5,items:items.slice(0,3)},teacher.cookie);
assert.equal(negQuiz.status,201);
const negStart=await request(`/api/quizzes/${negQuiz.data.id}/start`,'POST',undefined,student.cookie);
assert.equal(negStart.status,200);
// Verify negative_marks in paperPayload()
assert.equal(negStart.data.negative_marks, 0.5);
assert.equal(negStart.data.schedule_mode, 'instant');

const storedNeg=JSON.parse(sqlite.prepare('SELECT questions FROM attempts WHERE id=?').get(negStart.data.id).questions);
const correctNeg=storedNeg[0].options.filter(o=>o.is_correct).map(o=>o.id);
const negAnswers={
  [storedNeg[0].item_id]: correctNeg, // correct (+1)
  [storedNeg[1].item_id]: ['C']       // wrong (-0.5)
};
const negDraft=await request(`/api/attempts/${negStart.data.id}/draft`,'PUT',{answers:negAnswers},student.cookie);
assert.equal(negDraft.status, 200);
assert.equal(negDraft.data.negative_marks, 0.5);

const negSub=await request(`/api/attempts/${negStart.data.id}/submit`,'POST',{answers:negAnswers},student.cookie);
assert.equal(negSub.data.negative_marks, 0.5);
assert.equal(negSub.data.result.earned, 0.5);
assert.equal(negSub.data.result.penalty, 0.5);
assert.equal(negSub.data.result.correct, 1);
assert.equal(negSub.data.result.wrong, 1);

// Verify teacher-only DELETE /api/quizzes/:id and DELETE /api/classes/:id
// Non-teacher DELETE returns 403
assert.equal((await request(`/api/quizzes/${negQuiz.data.id}`,'DELETE',undefined,student.cookie)).status, 403);
assert.equal((await request(`/api/classes/${classId}`,'DELETE',undefined,student.cookie)).status, 403);

// Other teacher DELETE returns 403
const teacher2=await register('teacher', 2);
assert.equal((await request(`/api/classes/${classId}`,'DELETE',undefined,teacher2.cookie)).status, 403);

// Teacher DELETE quiz returns 200 and cascade cleans up attempts
const delQuizRes=await request(`/api/quizzes/${negQuiz.data.id}`,'DELETE',undefined,teacher.cookie);
assert.equal(delQuizRes.status, 200);
assert.equal(delQuizRes.data.message, 'Quiz deleted.');
assert.equal((await request(`/api/quizzes/${negQuiz.data.id}/start`,'POST',undefined,student.cookie)).status, 404);

// Teacher DELETE class returns 200 and cascade cleans up quizzes, attempts, codes, memberships
const delClassRes=await request(`/api/classes/${classId}`,'DELETE',undefined,teacher.cookie);
assert.equal(delClassRes.status, 200);
assert.equal(delClassRes.data.message, 'Classroom deleted.');
assert.equal((await request(`/api/classes/${classId}/quizzes`,'GET',undefined,teacher.cookie)).status, 404);

const logout=await request('/api/auth/logout','POST',undefined,student.cookie);assert.equal(logout.status,200);assert.equal((await request('/api/auth/me','GET',undefined,student.cookie)).status,401);
console.log('Cloudflare Worker integration checks passed: schema, sessions, roles, invitations, unique papers, frozen key hiding, autosave/resume, grading, negative marking, calendar scheduling, idempotency, deadlines, class privacy, teacher results, and delete controls.');
sqlite.close();
