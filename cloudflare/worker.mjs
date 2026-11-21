// Private D1 API. Only the Vercel gateway holds API_TOKEN; browsers use app sessions.
const enc = new TextEncoder();
const fail = (status, detail) => { throw Object.assign(new Error(detail), {status}); };
const json = (body, status=200, headers={}) => Response.json(body, {status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...headers}});
const id = () => crypto.randomUUID().replaceAll('-','');
const hex = bytes => [...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('');
const hash = async value => hex(await crypto.subtle.digest('SHA-256', enc.encode(value)));
const token = () => hex(crypto.getRandomValues(new Uint8Array(32)));
const publicUser = u => ({id:u.id,email:u.email,name:u.name,role:u.role,sid:u.sid||'',branch:u.branch||''});
const parse = JSON.parse;
const dump = JSON.stringify;
function integer(value,min,max,label){if(!Number.isInteger(value)||value<min||value>max)fail(422,`${label} must be an integer from ${min} to ${max}.`);return value;}
function text(value,max,label){if(typeof value!=='string'||!value.trim()||value.length>max)fail(422,`Enter a valid ${label}.`);return value.trim();}
function email(value){const e=text(value,254,'email').toLowerCase();if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e))fail(422,'Enter a valid email address.');return e;}
function role(value){if(!['teacher','student','admin'].includes(value))fail(422,'Choose teacher, student, or admin.');return value;}
async function password(value,salt=token()){
  if(typeof value!=='string'||value.length<10||value.length>128)fail(422,'Use a password from 10 to 128 characters.');
  const key=await crypto.subtle.importKey('raw',enc.encode(value),'PBKDF2',false,['deriveBits']);
  const bits=await crypto.subtle.deriveBits({name:'PBKDF2',salt:enc.encode(salt),iterations:100000,hash:'SHA-256'},key,256);
  return `${salt}:${hex(bits)}`;
}
async function equal(a,b){return await hash(a)===await hash(b);}
function randomInt(max){const limit=Math.floor(4294967296/max)*max;let n;do{n=crypto.getRandomValues(new Uint32Array(1))[0];}while(n>=limit);return n%max;}
function shuffle(items){for(let i=items.length-1;i>0;i--){const j=randomInt(i+1);[items[i],items[j]]=[items[j],items[i]];}return items;}
function capacity(n,k){let c=1n;for(let i=1;i<=k;i++)c=c*BigInt(n-i+1)/BigInt(i);return c;}
function* combinations(n,k,start=0,chosen=[]){if(chosen.length===k){yield chosen;return;}for(let i=start;i<=n-(k-chosen.length);i++)yield* combinations(n,k,i+1,[...chosen,i]);}
export function validateAnswers(questions,answers){
  if(!answers||Array.isArray(answers)||typeof answers!=='object')fail(422,'Answers must map question IDs to selected option IDs.');
  const key=new Map(questions.map(q=>[q.item_id,q]));
  for(const [qid,picks] of Object.entries(answers)){
    const q=key.get(qid);if(!q)fail(422,'Submission contains an unassigned question.');
    if(!Array.isArray(picks)||picks.some(p=>typeof p!=='string')||new Set(picks).size!==picks.length||picks.some(p=>!q.options.some(o=>o.id===p)))fail(422,'Duplicate or unknown option ID.');
    if(q.kind==='single'&&picks.length>1)fail(422,'Choose one option on a single-choice question.');
  }
}
export function grade(questions,answers,negativeMarks=0){
  let correct=0,wrong=0,skipped=0;
  for(const q of questions){const picks=answers[q.item_id]||[],key=q.options.filter(o=>o.is_correct).map(o=>o.id);if(!picks.length)skipped++;else if(picks.length===key.length&&picks.every(p=>key.includes(p)))correct++;else wrong++;}
  const neg = Number(negativeMarks) || 0;
  const penalty = Math.round(wrong * neg * 100) / 100;
  const earned = Math.round((correct - penalty) * 100) / 100;
  const res = {earned,maximum:questions.length,correct,wrong,skipped,percentage:Math.round(earned/questions.length*10000)/100};
  if(neg > 0){res.negative_marks = neg; res.penalty = penalty;}
  return res;
}
function validateBank(items,quizId){
  if(!Array.isArray(items)||!items.length||items.length>200)fail(422,'Provide 1 to 200 questions.');
  const ids=new Set();
  return items.map((q,i)=>{
    if(!q||typeof q!=='object')fail(422,'Each question must be an object.');
    const original=text(q.item_id,128,'question ID');if(ids.has(original))fail(422,'Question IDs must be unique.');ids.add(original);
    if(q.is_probe)fail(422,'MCQ banks cannot contain probe questions.');
    const kind=q.kind||'single';if(!['single','multiple'].includes(kind))fail(422,'Invalid question kind.');
    if(!Array.isArray(q.options)||!q.options.length||q.options.length>8)fail(422,'Each question needs 1 to 8 options.');
    const labels=new Set();const options=q.options.map(o=>{const label=text(o.id,8,'option ID');if(labels.has(label))fail(422,'Option IDs must be unique.');labels.add(label);return {id:label,text:text(o.text,10000,'option text'),is_correct:o.is_correct===true};});
    const correct=options.filter(o=>o.is_correct).length;if(!correct||(kind==='single'&&correct!==1))fail(422,'Approve a valid answer key for every question.');
    return {item_id:`${quizId}_${i}`,skill_id:`quiz_${quizId}`,kind,stem:text(q.stem,20000,'question text'),options};
  });
}

export async function handle(request,env){
  if(!env.API_TOKEN||!await equal(request.headers.get('authorization')||'',`Bearer ${env.API_TOKEN}`))return json({detail:'Unauthorized gateway.'},401);
  const db=env.DB.withSession('first-primary');
  const stmt=(sql,...params)=>db.prepare(sql).bind(...params);
  const first=(sql,...params)=>stmt(sql,...params).first();
  const all=async(sql,...params)=>(await stmt(sql,...params).all()).results;
  const run=(sql,...params)=>stmt(sql,...params).run();
  const url=new URL(request.url),path=url.pathname,method=request.method;
  let match;
  const body=async()=>{try{const data=await request.json();if(!data||typeof data!=='object'||Array.isArray(data))fail(422,'Send a JSON object.');return data;}catch{fail(422,'Send a valid JSON object.');}};
  const cookie=request.headers.get('cookie')?.match(/(?:^|;\s*)btn_session=([^;]+)/)?.[1]||'';
  const cookieHash=await hash(cookie);
  async function loginResponse(user){
    const value=token();await run('INSERT INTO sessions(token_hash,user_id,expires_ms) VALUES(?,?,?)',await hash(value),user.id,Date.now()+7*86400000);
    return json(publicUser(user),200,{'Set-Cookie':`btn_session=${value}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800${request.headers.get('x-site-protocol')==='http'?'':'; Secure'}`});
  }
  async function throttle(label,limit){
    const key=await hash(`${label}:${request.headers.get('x-client-ip')||''}:${Math.floor(Date.now()/60000)}`);
    const row=await stmt('INSERT INTO login_limits(key,count,expires_ms) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1 RETURNING count',key,Date.now()+120000).first();
    if(row.count>limit)fail(429,'Too many attempts. Try again in a minute.');
    await run('DELETE FROM login_limits WHERE expires_ms<?',Date.now());
  }
  if(path==='/api/health')return json({status:'ok'});
  if(path==='/api/ready'){await first('SELECT 1');return json({status:'ready',database:'Cloudflare D1'});}
  if(path==='/api/auth/register'&&method==='POST'){
    await throttle('register',100);const data=await body(),user={id:id(),email:email(data.email),name:text(data.name,128,'name'),role:role(data.role)};
    user.sid=user.role==='student'&&data.sid?.trim()?text(data.sid,64,'SID'):'';
    user.branch=user.role==='student'&&data.branch?.trim()?text(data.branch,128,'branch'):'';
    const hashed=await password(data.password);
    const result=await run('INSERT OR IGNORE INTO users(id,email,name,role,password_hash,sid,branch) VALUES(?,?,?,?,?,?,?)',user.id,user.email,user.name,user.role,hashed,user.sid,user.branch);
    if(!result.meta.changes)fail(409,'An account with this email already exists.');return loginResponse(user);
  }
  if(path==='/api/auth/login'&&method==='POST'){
    const data=await body();
    const sidCandidate = (typeof data.sid === 'string' && data.sid.trim()) ? data.sid.trim() : '';
    const emailCandidate = (typeof data.email === 'string' && data.email.trim()) ? data.email.trim() : '';
    if(!emailCandidate && !sidCandidate) fail(422, 'Enter your email or SID.');
    const hasAt = emailCandidate.includes('@');
    let user = null;
    if(hasAt){
      const validEmail = email(emailCandidate);
      await throttle('login:'+validEmail, 10);
      user = await first('SELECT * FROM users WHERE email=?', validEmail);
    }
    if(!user){
      const sid = sidCandidate || (!hasAt ? emailCandidate : '');
      if(sid){
        await throttle('login:sid:'+sid.toLowerCase(), 10);
        user = await first('SELECT * FROM users WHERE sid != "" AND LOWER(sid)=?', sid.toLowerCase());
      }
    }
    const salt=user?.password_hash?.split(':')[0]||token();
    const hashed=await password(data.password,salt);
    if(!user||!await equal(hashed,user.password_hash)||(data.role&&data.role!==user.role)) fail(401,'Email, SID, or password is incorrect.');
    if(user.role==='student'){
      const sidCandidate=data.sid?.trim();
      const sid=sidCandidate?(user.sid&&sidCandidate.toLowerCase()===user.sid.toLowerCase()?user.sid:text(sidCandidate,64,'SID')):user.sid;
      const branch=data.branch?.trim()?text(data.branch,128,'branch'):user.branch;
      if(sid!==user.sid||branch!==user.branch)await run('UPDATE users SET sid=?,branch=? WHERE id=?',sid,branch,user.id);
      user.sid=sid;user.branch=branch;
    }
    return loginResponse(user);
  }
  const user=await first('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_ms>?',cookieHash,Date.now());
  if(!user)fail(401,'Please sign in to continue.');
  const requireTeacher=()=>{if(user.role!=='teacher')fail(403,'Only teachers can perform this action.');};
  async function accessClass(classId){
    const c=await first('SELECT * FROM classes WHERE id=?',classId);
    if(!c)fail(404,'Classroom not found.');
    if(user.role==='teacher'){if(c.teacher_id!==user.id)fail(403,'This classroom belongs to another teacher.');}
    else if(!await first('SELECT 1 FROM memberships WHERE class_id=? AND user_id=?',classId,user.id))fail(403,'Join this classroom with its room code or an invitation first.');
    return c;
  }
  async function accessQuiz(quizId,isSkill=false){const q=await first(`SELECT * FROM quizzes WHERE ${isSkill?'skill_id':'id'}=?`,quizId);if(!q)fail(404,'Quiz not found.');await accessClass(q.class_id);return q;}
  async function checkLearner(q,learner){if(user.role==='student'&&learner!==user.id)fail(403,'You may only view your own performance.');if(!await first('SELECT 1 FROM memberships WHERE class_id=? AND user_id=?',q.class_id,learner))fail(403,'This learner is not in your class.');}
  async function finalize(attempt,answers){
    const q=await first('SELECT negative_marks FROM quizzes WHERE id=?',attempt.quiz_id);
    const neg=q?.negative_marks||0;
    const questions=parse(attempt.questions);validateAnswers(questions,answers);
    const result=grade(questions,answers,neg);
    await run('UPDATE attempts SET answers=?,result=? WHERE id=? AND result IS NULL AND deadline_ms>?',dump(answers),dump(result),attempt.id,Date.now());
    // If the deadline won the race, grade the last persisted draft with a compare-and-swap.
    let current=await first('SELECT * FROM attempts WHERE id=?',attempt.id);
    for(let i=0;!current.result&&Date.now()>=current.deadline_ms&&i<5;i++){
      const saved=current.answers,expired=grade(parse(current.questions),parse(saved),neg);
      await run('UPDATE attempts SET result=? WHERE id=? AND result IS NULL AND answers=?',dump(expired),current.id,saved);
      current=await first('SELECT * FROM attempts WHERE id=?',attempt.id);
    }
    return current;
  }
  async function expire(attempt){return attempt&&!attempt.result&&Date.now()>=attempt.deadline_ms?finalize(attempt,parse(attempt.answers)):attempt;}
  async function paperPayload(attempt){
    attempt=await expire(attempt);
    return {id:attempt.id,mode:'mcq',finished:!!attempt.result,server_time:new Date().toISOString(),deadline:new Date(attempt.deadline_ms).toISOString(),total_questions:parse(attempt.questions).length,answers:parse(attempt.answers),result:attempt.result?parse(attempt.result):null,
      questions:attempt.result?[]:parse(attempt.questions).map(q=>({...q,options:q.options.map(o=>({id:o.id,text:o.text}))}))};
  }
  async function marks(q,learner,existing){
    const attempt=await expire(existing===undefined?await first('SELECT * FROM attempts WHERE quiz_id=? AND learner_id=?',q.id,learner):existing);
    const r=attempt?.result?parse(attempt.result):{earned:0,maximum:q.question_count,correct:0,wrong:0,skipped:q.question_count,percentage:0};
    const neg=q.negative_marks||0;
    return {...r,mode:'mcq',learner_id:learner,skill_id:q.skill_id,score:r.earned,out_of:r.maximum,answered:r.correct+r.wrong,unanswered:r.skipped,status:attempt?.result?'graded':attempt?'in_progress':'not_started',secure_marks:0,fragile_marks:0,performance_percentage:r.percentage,negative_marks:neg};
  }
  if(path==='/api/auth/me')return json(publicUser(user));
  if(path==='/api/auth/logout'&&method==='POST'){await run('DELETE FROM sessions WHERE token_hash=?',cookieHash);return json({message:'Signed out.'},200,{'Set-Cookie':'btn_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0; Secure'});}
  async function classroomCode(classId){
    for(let i=0;i<10;i++){
      const existing=await first('SELECT code FROM classroom_codes WHERE class_id=?',classId);
      if(existing)return existing.code;
      const alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
      const code=Array.from({length:8},()=>alphabet[randomInt(alphabet.length)]).join('');
      await run('INSERT OR IGNORE INTO classroom_codes(class_id,code) VALUES(?,?)',classId,code);
    }
    fail(503,'Could not create a classroom code. Please try again.');
  }
  if(path==='/api/classes'){
    if(method==='POST'){requireTeacher();const data=await body(),c={id:id(),name:text(data.name,128,'class name')};await run('INSERT INTO classes(id,name,teacher_id) VALUES(?,?,?)',c.id,c.name,user.id);c.join_code=await classroomCode(c.id);return json(c,201);}
    if(user.role==='teacher'){
      const rows=await all('SELECT id,name FROM classes WHERE teacher_id=?',user.id);
      for(const c of rows)c.join_code=await classroomCode(c.id);
      return json(rows);
    }
    return json(await all('SELECT c.id,c.name FROM classes c JOIN memberships m ON m.class_id=c.id WHERE m.user_id=?',user.id));
  }
  if(path==='/api/classes/join'&&method==='POST'){
    if(user.role!=='student')fail(403,'Sign in with a student account to join a class.');
    await throttle('room-code:'+user.id,20);
    const data=await body(),code=text(data.code,32,'classroom code').toUpperCase();
    if(!/^[A-Z0-9]{8}$/.test(code))fail(422,'Enter the 8-character classroom code.');
    const room=await first('SELECT class_id FROM classroom_codes WHERE code=?',code);
    if(!room)fail(404,'Classroom code not found. Check the code with your teacher.');
    await run('INSERT OR IGNORE INTO memberships(class_id,user_id) VALUES(?,?)',room.class_id,user.id);
    return json({class_id:room.class_id,message:'You joined the classroom.'});
  }
  match=path.match(/^\/api\/classes\/([^/]+)\/students\/([^/]+)$/);
  if(match&&method==='DELETE'){
    requireTeacher();const [,classId,studentId]=match;await accessClass(classId);
    const m=await first('SELECT 1 FROM memberships WHERE class_id=? AND user_id=?',classId,studentId);
    if(!m)fail(404,'Student is not enrolled in this classroom.');
    const quizzes=await all('SELECT id FROM quizzes WHERE class_id=?',classId);
    for(const q of quizzes){await run('DELETE FROM attempts WHERE quiz_id=? AND learner_id=?',q.id,studentId);}
    await run('DELETE FROM memberships WHERE class_id=? AND user_id=?',classId,studentId);
    return json({message:'Student removed from classroom.'});
  }
  match=path.match(/^\/api\/classes\/([^/]+)\/(invitations|students|quizzes)$/);
  if(match){const [,classId,action]=match;await accessClass(classId);
    if(action==='invitations'&&method==='POST'){requireTeacher();const data=await body(),value=token(),e=email(data.email);await run('INSERT INTO invitations(token_hash,class_id,email,expires_ms) VALUES(?,?,?,?)',await hash(value),classId,e,Date.now()+7*86400000);return json({token:value,email:e,expires_in_days:7},201);}
    if(action==='students'){requireTeacher();return json(await all('SELECT u.id,u.name,u.email,u.sid,u.branch FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.class_id=?',classId));}
    if(action==='quizzes'){
      if(method==='POST'){
        requireTeacher();const data=await body(),quizId=id(),bank=validateBank(data.items,quizId),count=integer(data.question_count||bank.length,1,bank.length,'Questions per student'),seconds=integer(data.total_time_s,10,86400,'Total time');
        if(enc.encode(dump(bank)).length>1000000)fail(413,'Question bank text is too large. Use a bank smaller than 1 MB after extraction.');
        const enrolled=await first('SELECT count(*) AS n FROM memberships WHERE class_id=?',classId);if(capacity(bank.length,count)<BigInt(enrolled.n))fail(422,'Add questions or change questions per student to provide enough distinct sets.');
        const neg=Math.max(0,Math.min(5,Number(data.negative_marks)||0));
        const mode=data.schedule_mode==='scheduled'?'scheduled':'instant';
        let startMs=null,endMs=null;
        if(mode==='scheduled'){
          if(!data.start_time||!data.end_time)fail(422,'Scheduled assessments require start and end times.');
          startMs=Date.parse(data.start_time);endMs=Date.parse(data.end_time);
          if(isNaN(startMs)||isNaN(endMs)||endMs<=startMs)fail(422,'Assessment end time must be after start time.');
        }
        const q={id:quizId,title:text(data.title,128,'quiz title'),skill_id:`quiz_${quizId}`,total_time_s:seconds,question_count:count,mode:'mcq',negative_marks:neg,schedule_mode:mode,start_time_ms:startMs,end_time_ms:endMs};
        await run('INSERT INTO quizzes(id,class_id,title,skill_id,total_time_s,question_count,bank,negative_marks,schedule_mode,start_time_ms,end_time_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?)',q.id,classId,q.title,q.skill_id,seconds,count,dump(bank),neg,mode,startMs,endMs);
        return json({id:q.id,title:q.title,skill_id:q.skill_id,total_time_s:q.total_time_s,question_count:q.question_count,mode:'mcq',negative_marks:neg,schedule_mode:mode,start_time:startMs?new Date(startMs).toISOString():null,end_time:endMs?new Date(endMs).toISOString():null},201);
      }
      return json((await all('SELECT id,title,skill_id,total_time_s,question_count,negative_marks,schedule_mode,start_time_ms,end_time_ms FROM quizzes WHERE class_id=?',classId)).map(q=>({...q,mode:'mcq',negative_marks:q.negative_marks||0,schedule_mode:q.schedule_mode||'instant',start_time:q.start_time_ms?new Date(q.start_time_ms).toISOString():null,end_time:q.end_time_ms?new Date(q.end_time_ms).toISOString():null})));
    }
  }
  if(path==='/api/invitations/accept'&&method==='POST'){
    if(user.role!=='student')fail(403,'Sign in with a student account to join a class.');const data=await body(),hashed=await hash(text(data.token,128,'invitation token'));
    const invite=await first('SELECT * FROM invitations WHERE token_hash=?',hashed);
    if(!invite||invite.accepted||invite.expires_ms<=Date.now())fail(422,'This invitation is expired, invalid, or already used.');
    if(invite.email!==user.email)fail(403,'This invitation is for a different email address.');
    // Membership and token consumption commit together; only the first acceptance inserts.
    const results=await db.batch([
      stmt('INSERT OR IGNORE INTO memberships(class_id,user_id) SELECT class_id,? FROM invitations WHERE token_hash=? AND email=? AND accepted=0 AND expires_ms>?',user.id,hashed,user.email,Date.now()),
      stmt('UPDATE invitations SET accepted=1 WHERE token_hash=? AND accepted=0 AND expires_ms>?',hashed,Date.now())
    ]);
    if(!results[1].meta.changes)fail(422,'This invitation has already been accepted.');return json({message:'You joined the classroom.',class_id:invite.class_id});
  }
  match=path.match(/^\/api\/quizzes\/([^/]+)\/start$/);
  if(match&&method==='POST'){
    if(user.role!=='student')fail(403,'Only students can take quizzes.');const q=await accessQuiz(match[1]);
    let attempt=await first('SELECT * FROM attempts WHERE quiz_id=? AND learner_id=?',q.id,user.id);if(attempt)return json(await paperPayload(attempt));
    const nowMs=Date.now();
    if(q.schedule_mode==='scheduled'){
      if(q.start_time_ms&&nowMs<q.start_time_ms)fail(403,`Assessment has not started yet. Testing window opens at ${new Date(q.start_time_ms).toISOString()}.`);
      if(q.end_time_ms&&nowMs>=q.end_time_ms)fail(403,`The assessment window closed at ${new Date(q.end_time_ms).toISOString()}.`);
    }
    const bank=parse(q.bank),used=new Set((await all('SELECT signature FROM attempts WHERE quiz_id=?',q.id)).map(r=>r.signature));
    if(BigInt(used.size)>=capacity(bank.length,q.question_count))fail(409,'All distinct question sets have been assigned. Ask your teacher to publish a larger bank or a new test.');
    const generator=combinations(bank.length,q.question_count);
    for(let tries=0;tries<500;tries++){
      const indices=tries<100?shuffle([...bank.keys()]).slice(0,q.question_count):generator.next().value;if(!indices)break;
      const signature=await hash([...indices].sort((a,b)=>a-b).join(','));if(used.has(signature))continue;
      const questions=shuffle(indices).map(i=>({...bank[i],options:shuffle(bank[i].options.map(o=>({...o})))}));
      const attemptId=id(),started=Date.now();
      const plannedDeadline=started+q.total_time_s*1000;
      const deadline=(q.schedule_mode==='scheduled'&&q.end_time_ms)?Math.min(plannedDeadline,q.end_time_ms):plannedDeadline;
      const inserted=await run('INSERT OR IGNORE INTO attempts(id,quiz_id,learner_id,signature,questions,started_ms,deadline_ms) VALUES(?,?,?,?,?,?,?)',attemptId,q.id,user.id,signature,dump(questions),started,deadline);
      attempt=await first('SELECT * FROM attempts WHERE quiz_id=? AND learner_id=?',q.id,user.id);if(attempt)return json(await paperPayload(attempt));
      if(!inserted.meta.changes)used.add(signature);
    }
    fail(409,'Question sets are being assigned. Please try again.');
  }
  match=path.match(/^\/api\/attempts\/([^/]+)\/(draft|submit)$/);
  if(match){
    let a=await first('SELECT * FROM attempts WHERE id=?',match[1]);if(!a||a.learner_id!==user.id)fail(403,'This is not your quiz attempt.');await accessQuiz(a.quiz_id);
    if(a.result)return json(await paperPayload(a));
    if(Date.now()>=a.deadline_ms)return json(await paperPayload(a));
    const data=await body();validateAnswers(parse(a.questions),data.answers);
    if(match[2]==='draft'&&method==='PUT'){
      await run('UPDATE attempts SET answers=? WHERE id=? AND result IS NULL AND deadline_ms>?',dump(data.answers),a.id,Date.now());
      a=await first('SELECT * FROM attempts WHERE id=?',a.id);
    }else if(match[2]==='submit'&&method==='POST')a=await finalize(a,data.answers);else fail(405,'Method not allowed.');
    return json(await paperPayload(a));
  }
  match=path.match(/^\/api\/items\/([^/]+)$/);
  if(match){const q=await accessQuiz(match[1],true);return json(parse(q.bank).map(item=>user.role==='student'?{item_id:item.item_id,expected_time_s:q.total_time_s}:{...item,options:item.options.map(o=>({id:o.id,text:o.text}))}));}
  match=path.match(/^\/api\/(profile|marks|review)\/([^/]+)\/([^/]+)$/);
  if(match){
    const [,action,learner,skill]=match,q=await accessQuiz(skill,true);
    await checkLearner(q,learner);
    if(action==='review')return json([]);
    const m=await marks(q,learner);
    if(action==='marks')return json(m);
    const u=await first('SELECT id,name,email,sid,branch FROM users WHERE id=?',learner);
    return json({learner_id:learner,skill_id:skill,state:m.status==='graded'?'Assessed':'Unassessed',display_name:u?.name||learner,sid:u?.sid||'',branch:u?.branch||'',email:u?.email||null,marks:m});
  }
  match=path.match(/^\/api\/teacher\/heatmap\/([^/]+)$/);
  if(match){requireTeacher();const q=await accessQuiz(match[1],true),rows=await all('SELECT u.id,u.name,u.email,u.sid,u.branch FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.class_id=?',q.class_id),students=[];
    const attempts=new Map((await all('SELECT * FROM attempts WHERE quiz_id=?',q.id)).map(a=>[a.learner_id,a]));
    for(const u of rows){const m=await marks(q,u.id,attempts.get(u.id)||null);students.push({learner_id:u.id,display_name:u.name,email:u.email,sid:u.sid||'',branch:u.branch||'',state:m.status==='graded'?'Assessed':'Unassessed',marks:m,updated_at:'',dominant_misconception:'None',evidence_count:0});}
    return json({skill_id:q.skill_id,total_students:students.length,students,state_distribution:{},misconception_heatmap:{}});
  }
  if(path==='/api/skills')return json((user.role==='teacher'?await all('SELECT q.skill_id FROM quizzes q JOIN classes c ON q.class_id=c.id WHERE c.teacher_id=?',user.id):await all('SELECT q.skill_id FROM quizzes q JOIN memberships m ON m.class_id=q.class_id WHERE m.user_id=?',user.id)).map(q=>q.skill_id));
  fail(404,'Endpoint not found.');
}
export default {async fetch(request,env){try{return await handle(request,env);}catch(error){if(!error.status)console.error('Assessment API failed',error.message);return json({detail:error.status?error.message:'The assessment service is temporarily unavailable. Please retry.'},error.status||503);}}};
