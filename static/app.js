'use strict';
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const title = value => String(state.quizzes?.find(q=>q.skill_id===value)?.title || value || '').replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());
const storage = {get(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } }, set(key,value) { try { localStorage.setItem(key,value); } catch {} }};
const state = {page:'dashboard', skills:[], skill:storage.get('btn-skill',''), learner:storage.get('btn-learner','student_' + Math.random().toString(36).slice(2,8)), questions:[], profile:{}, review:[], heatmap:{students:[]}, index:0, selected:null, confidence:null, quizStarted:false, skipAnswered:false, startedAt:0, submitting:false, pending:null, query:'', filter:'all', sort:'id', uploadText:'', loading:false, generation:0, account:null, classes:[], classId:'', quizzes:[], attempt:null, serverOffset:0, inviteToken:new URLSearchParams(location.search).get('invite')||'', classStudents:[], violations:0};
const MAX_INTEGRITY_STRIKES = 2;
const labels = {classes:'My classrooms',dashboard:'Overview',quiz:'Practice studio',profile:'My performance',teacher:'Class insights',upload:'Question bank'};
const storyLabels = {secure:'Confident understanding',fragile_correct:'Correct, with uncertainty',knowledge_gap:'Concept needs practice',rushed:'Possibly rushed',unresolved:'More evidence needed',missed_condition:'A condition was missed',mistaken_rule:'A rule needs revisiting'};
function badge(value) { const cls = {'Secure':'secure','Lucky / Fragile':'fragile','Careless Slip':'slip','Deep Misconception':'deep'}[value] || ''; return `<span class="badge ${cls}">${escapeHTML(value || 'Unassessed')}</span>`; }
function toast(message) { $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('#toast').hidden=true,4500); }
function showError(error) { $('#error').textContent=error.message || String(error); $('#error').hidden=false; }
function clearError() { $('#error').hidden=true; }
async function api(path, options={}) {
    let response;
    try { response=await fetch(path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}}); }
    catch { throw new Error('Cannot reach the assessment server. Check your connection and try again.'); }
    const text=await response.text(); let data;
    try { data=JSON.parse(text); } catch { throw new Error('The server returned an unexpected response. Please refresh and try again.'); }
    if(!response.ok) { const detail=Array.isArray(data.detail)?data.detail.map(e=>`${e.loc?.slice(1).join('.') || 'Input'}: ${e.msg}`).join('; '):data.detail; throw new Error(detail || `Request failed (${response.status}).`); }
    return data;
}
function marks() { return state.profile.marks || {score:0,out_of:state.questions.length,percentage:0,secure_marks:0,fragile_marks:0,wrong:0,answered:0,unanswered:state.questions.length}; }
function header(eyebrow,heading,subtitle,action='') { return `<div class="heading"><div><span class="eyebrow">${eyebrow}</span><h1>${heading}</h1><p>${subtitle}</p></div>${action}</div>`; }
function stat(label,value,caption,icon) {return `<div class="stat"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-caption">${caption}</div></div>`;}
function empty(heading,description,action='') {return `<div class="panel empty"><div class="empty-icon">✦</div><h2>${heading}</h2><p>${description}</p>${action}</div>`;}
function understanding() {
    const m=marks(), pct=m.performance_percentage||0;
    return `<div class="understanding"><div class="ring" style="--percent:${pct}"><div>${pct}%<small>confidence performance</small></div></div><div class="legend">${[['Secure marks',m.secure_marks,'var(--purple)'],['Correct but unsure',m.fragile_marks,'#c4b6ef'],['Needs attention',m.wrong,'#e7b374'],['Not answered',m.unanswered,'#c7cad7']].map(([label,n,color])=>`<div class="legend-row"><span class="legend-dot" style="background:${color}"></span>${label}<strong>${n}</strong></div>`).join('')}</div></div><div class="note">Raw marks count every correct answer. Performance weights correct answers by confidence: Sure 100%, Unsure 85%, Guessing 75%. Wrong or unanswered: 0%.</div>`;
}
function recommendation() {
    if(state.profile.remediation) return state.profile.remediation;
    if(state.profile.evidence_needed) return state.profile.evidence_needed;
    const m=marks();
    if(!m.answered) return 'Start a short practice session. Tag your confidence so we can understand what is working and where you need support.';
    if(m.unanswered) return `You have ${m.unanswered} unanswered question${m.unanswered===1?'':'s'}. Continue your practice to complete the picture.`;
    if(m.fragile_marks) return 'Revisit answers you were unsure about. Explain your reasoning in your own words before trying again.';
    if(m.wrong) return 'Review the answers that need attention, then retry with careful reading and a clear reasoning step.';
    return 'You are answering confidently. Try explaining the concepts without looking at the options to strengthen your understanding.';
}
function dashboard() {
    const m=marks();
    if(m.mode==='mcq')return header('YOUR ASSESSMENT WORKSPACE','Ready for your next assessment?',escapeHTML(title(state.skill)))+`<div class="stats">${stat('Questions in your paper',m.out_of,'Your saved question set','☷')}${stat('Status',m.status==='graded'?'Submitted':m.status==='in_progress'?'In progress':'Not started','One attempt per assessment','◷')}${stat('Final marks',m.status==='graded'?`${m.score}/${m.out_of}`:'—','+1 correct · 0 wrong or skipped','↗')}${stat('Final percentage',m.status==='graded'?`${m.percentage}%`:'—','Available after submission','✧')}</div><div class="panel"><h2>Your assessment is assigned.</h2><p class="note">Your paper is saved when you start. Answers autosave, and the server enforces the deadline. You can review answers before final submission.</p><button class="button primary" data-action="practice">Open assessment →</button></div>`;
    return header('A LITTLE PROGRESS, EVERY DAY','Your next chapter starts here.','See where you stand. Understand what comes next.',`<span class="date-tag">${escapeHTML(new Date().toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short',year:'numeric'}))}</span>`)+
    `<div class="hero"><div class="hero-copy"><span class="eyebrow">UNDERSTANDING &gt; MEMORIZATION</span><h2>You’re more than<br><em>your last score.</em></h2><p>Turn every answer into a better understanding of how you learn. One thoughtful step at a time.</p><button class="button" data-action="practice">${m.answered?'Continue learning':'Start your first practice'} <span>↗</span></button></div><div class="hero-art" aria-hidden="true"><div class="orbit three"></div><div class="orbit"></div><div class="orbit two"></div><div class="art-core">✦</div><span class="float-chip first">✓ Build confidence</span><span class="float-chip second">↗ Make progress</span><span class="art-dot"></span></div></div>`+
    `<div class="stats">${stat('Your score',`${m.score}<small> / ${m.out_of}</small>`,'Latest answer per question','◷')}${stat('Raw marks percentage',`${m.percentage}<small>%</small>`,'Unanswered questions count as zero','↗')}${stat('Secure marks',m.secure_marks,'Correct answers tagged “Sure”','✧')}${stat('Questions attempted',`${m.answered}<small> / ${m.out_of}</small>`,`${m.unanswered} still to explore`,'☷')}</div>`+
    `<div class="grid-main"><div class="panel"><div class="panel-head"><div><h3>Your learning path</h3><p>A focused space to build your understanding</p></div><span class="badge">${state.skills.length} topics</span></div>${state.skills.length?state.skills.map(skill=>`<div class="topic-row"><span class="topic-icon">⌘</span><div class="topic-info"><strong>${escapeHTML(title(skill))}</strong><p>${skill===state.skill?`${m.answered} of ${m.out_of} questions explored`:'Ready when you are'}</p>${skill===state.skill?`<div class="progress"><span style="width:${m.out_of?m.answered/m.out_of*100:0}%"></span></div>`:''}</div><button class="button small" data-action="topic" data-skill="${escapeHTML(skill)}">${skill===state.skill&&m.answered?'Continue':'Explore'} →</button></div>`).join(''):`<div class="note">No topics yet. Load the demo classroom or add your own question bank.</div><button class="button primary" data-action="seed" style="margin-top:16px">Load demo classroom →</button>`}</div><div class="panel"><div class="panel-head"><div><h3>What’s behind your score?</h3><p>Confidence gives your marks more meaning</p></div><span class="violet">◉</span></div>${understanding()}</div></div>`+
    `<div class="panel"><div class="panel-head"><div><h3>A small step. A stronger foundation.</h3><p>Your next action, based on your actual responses</p></div><span class="badge">FOR YOU</span></div><div class="next-step"><span class="number">01</span><div><h3>${m.answered?'Keep the understanding growing':'Make your first move'}</h3><p>${escapeHTML(recommendation())}</p></div><button class="button" data-action="navigate" data-target="profile">My performance ↗</button></div></div>`;
}
function confidenceInputs(name) {return `<div class="confidence"><p>How confident do you feel?</p><div class="confidence-options">${[['Sure','✦'],['Unsure','◐'],['Guessing','?']].map(([v,icon])=>`<label class="confidence-choice"><input required type="radio" name="${name}" value="${v}" ${name==='confidence'&&state.confidence===v?'checked':''}>${icon} ${v}</label>`).join('')}</div></div>`;}
function questionHTML(question,name) {return `<h2 class="quiz-stem">${escapeHTML(question.stem)}</h2><div class="options">${question.options.map(o=>`<label class="option"><input required type="radio" name="${name}" value="${escapeHTML(o.id)}" ${name==='answer'&&state.selected===o.id?'checked':''}><span class="option-letter">${escapeHTML(o.id)}</span><span class="option-text">${escapeHTML(o.text)}</span></label>`).join('')}</div>`;}
function quiz() {
    const heading=header('THE PRACTICE STUDIO','A clear mind. A fair challenge.',state.quizzes.find(q=>q.skill_id===state.skill)?.mode==='mcq'?'Your teacher sets the deadline. Review your answers and submit when ready.':'Your teacher sets the deadlines. Marks and confidence performance are shown separately.');
    if(state.account.role==='teacher')return heading+empty('Quizzes are taken by students.','Publish a quiz from your question bank and review results in Class insights.','<button class="button primary" data-action="navigate" data-target="upload">Publish a quiz →</button>');
    if(!state.skill)return heading+empty('No quiz assigned yet.','Join a classroom using your teacher’s 8-character code or invitation link. Published quizzes will appear here.','<button class="button primary" data-action="navigate" data-target="classes">My classrooms →</button>');
    const q=state.quizzes.find(q=>q.skill_id===state.skill);
    if(!state.attempt){
        const nowMs=Date.now();
        const startMs=q?.start_time?Date.parse(q.start_time):null;
        const endMs=q?.end_time?Date.parse(q.end_time):null;
        const isScheduled=q?.schedule_mode==='scheduled';
        const isUpcoming=isScheduled&&startMs&&nowMs<startMs;
        const isClosed=isScheduled&&endMs&&nowMs>=endMs;
        const windowStatus=isUpcoming?`<div class="banner warning" style="background:#fef3c7;color:#92400e;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-weight:600">⏳ Calendar Scheduled Assessment: Opens on ${new Date(startMs).toLocaleString()}</div>`:
                            isClosed?`<div class="banner danger" style="background:#fee2e2;color:#991b1b;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-weight:600">🔒 Assessment Window Closed on ${new Date(endMs).toLocaleString()}</div>`:
                            isScheduled?`<div class="banner active" style="background:#ecfdf5;color:#065f46;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-weight:600">🟢 Active Assessment Window: Closes on ${new Date(endMs).toLocaleString()}</div>`:'';
        const startButton=isUpcoming?`<button class="button" disabled style="opacity:0.6;cursor:not-allowed">⏳ Opens on ${new Date(startMs).toLocaleDateString()} at ${new Date(startMs).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</button>`:
                          isClosed?`<button class="button" disabled style="opacity:0.6;cursor:not-allowed">🔒 Assessment window closed</button>`:
                          `<button class="button primary" data-action="start">Start or resume quiz →</button>`;
        const negativeText=q?.negative_marks>0?`<li>⚡ Negative marking active: -${q.negative_marks} marks deducted per wrong answer. Skipped questions earn 0.</li>`:'<li>✓ No negative marking: Wrong or skipped answers earn 0.</li>';
        return heading+`<div class="panel">${windowStatus}<span class="eyebrow">${escapeHTML(q?.title)}</span><h2>Ready for your timed assessment?</h2><ul class="checklist"><li>${q?.question_count||state.questions.length} questions · ${q?.total_time_s} seconds overall.</li>${q?.mode==='mcq'?'<li>A distinct set is assigned to you and saved when you start.</li>':'<li>Each question has its own deadline, shown when it opens.</li>'}<li>The server saves your timer. Refreshing does not reset it.</li>${q?.mode==='mcq'?'<li>Review, clear and revisit answers before your final submission. Drafts autosave.</li>':'<li>One attempt per quiz. Questions cannot be revisited.</li>'}${negativeText}<li>✦ MCQ test: Single-choice and multiple-correct questions. Select all and only correct options.</li><li style="color:#e06c75;font-weight:600">⚠️ Academic integrity: Fullscreen lockdown is active. Exiting fullscreen, switching tabs, or copying content will auto-submit or is blocked.</li></ul>${startButton}</div>`;
    }
    const attempt=state.attempt;
    if(attempt.mode==='mcq')return examView(heading);
    if(attempt.finished)return heading+empty('Your quiz is complete.','Your submitted answers and marks have been saved. Unanswered or expired questions earn zero.','<button class="button primary" data-action="navigate" data-target="profile">View my results →</button>');
    return heading+`<div class="quiz-layout"><form id="quiz-form" class="panel quiz-panel"><div class="timer-bar"><span>Question: <strong id="question-timer">…</strong></span><span>Quiz remaining: <strong id="overall-timer">…</strong></span></div><div class="quiz-meta"><span>QUESTION ${attempt.current_index+1} OF ${attempt.total_questions}</span><span>${escapeHTML(q?.title)}</span></div><div class="progress"><span style="width:${attempt.current_index/attempt.total_questions*100}%"></span></div>${questionHTML(attempt.question,'answer')}${confidenceInputs('confidence')}<div class="quiz-bottom"><button class="button subtle" type="button" data-action="skip">Skip question</button><button class="button primary" type="submit" ${state.submitting?'disabled':''}>${state.submitting?'Saving…':'Save answer & continue →'}</button></div></form><div class="panel"><h3>How your score works</h3><ul class="checklist"><li>Correct + Sure + within time = 100% of this question’s performance weight.</li><li>Correct + Unsure = 85%.</li><li>Correct + Guessing = 75%.</li><li>Wrong, skipped, or expired = 0%.</li></ul><div class="note">Raw marks count every correct, on-time answer equally. One correct answer out of four always gives 1/4 (25%). The quiz timer continues when you leave this page.</div></div></div>`;
}
function profile() {
    if(!state.skill)return empty('Your results will appear here.','Join a classroom and take an assigned quiz first.');
    const m=marks();
    if(m.mode==='mcq'){
        const penaltyInfo=m.penalty?` · -${m.penalty} penalty`:m.negative_marks>0?` · -0.0 penalty`:'' ;
        return header('MY RESULTS',escapeHTML(title(state.skill)),m.negative_marks>0?`MCQ Assessment · -${m.negative_marks} negative marking`:'MCQ Assessment · Standard marking')+`<div class="panel"><h2>${m.status==='graded'?`${m.score}/${m.out_of} marks · ${m.percentage}% · ${m.correct} correct · ${m.wrong} wrong${penaltyInfo} · ${m.skipped} skipped`:'Your results will appear after final submission.'}</h2><p class="muted">MCQ format: Multiple-select questions require every correct option and no extra options.</p></div>`;
    }
    return header('YOUR LEARNING, IN FOCUS','There’s a story behind every score.','Look beyond the percentage. Find your strengths and your next steps.',`<button class="button primary" data-action="practice">Practice again ↗</button>`)+
    `<div class="grid-main"><div class="panel"><div class="panel-head"><div><h3>${escapeHTML(title(state.skill)||'Your assessment')}</h3><p>Learner: <strong>${escapeHTML(state.profile.display_name||state.learner)}</strong>${state.profile.sid?` · SID: <strong>${escapeHTML(state.profile.sid)}</strong>`:''}${state.profile.branch?` · ${escapeHTML(state.profile.branch)}`:''}</p></div>${badge(state.profile.state)}</div><div class="big-score">${m.score}<span> / ${m.out_of}</span></div><div class="progress"><span style="width:${m.percentage}%"></span></div><div class="quiz-meta" style="margin-top:12px"><span>${m.percentage}% raw marks</span><span>${m.unanswered} unanswered</span></div><div class="note">Each on-time correct answer earns one mark. Confidence never removes a correct mark. Timed quizzes allow one attempt.</div></div><div class="panel"><div class="panel-head"><h3>Confidence & understanding</h3></div>${understanding()}</div></div><div class="panel" style="margin-bottom:22px"><span class="eyebrow">YOUR NEXT STEP</span><h3>${escapeHTML(state.profile.misconception_description||'Build from what you know.')}</h3><p class="muted" style="font-size:12px;margin-top:10px">${escapeHTML(recommendation())}</p></div><div class="panel"><div class="panel-head"><div><h3>Your answer journal</h3><p>Review your latest response to each question</p></div><span class="badge">${state.review.length} responses</span></div>${state.review.length?state.review.map((r,i)=>`<article class="review-card"><div class="review-top"><span class="eyebrow" style="margin:0">QUESTION ${i+1}</span><span class="badge ${r.correct?'secure':'fragile'}">${r.correct?'✓ Correct':'Needs practice'}</span></div><h3>${escapeHTML(r.stem)}</h3><p>Your answer: ${escapeHTML(r.chosen_option)} · ${escapeHTML(r.answer_text)}</p><div class="review-tags"><span>◉ ${escapeHTML(r.confidence)}</span><span>◷ ${(r.time_ms/1000).toFixed(1)}s</span><span>↻ ${r.attempts} attempt${r.attempts===1?'':'s'}</span><span>✦ ${escapeHTML(storyLabels[r.story]||'Evidence in progress')}</span></div></article>`).join(''):'<div class="empty"><div class="empty-icon">✎</div><h2>A fresh page.</h2><p>Your answer journal will appear here after your first practice.</p><button class="button primary" data-action="practice">Start learning →</button></div>'}</div>`;
}
function filteredStudents() {
    return (state.heatmap.students||[]).filter(s=>[s.learner_id,s.display_name,s.email,s.sid,s.branch].filter(Boolean).join(' ').toLowerCase().includes(state.query.toLowerCase())&&(state.filter==='all'||s.state===state.filter)).sort((a,b)=>state.sort==='score'?(b.marks?.percentage||0)-(a.marks?.percentage||0):a.learner_id.localeCompare(b.learner_id));
}
function rosterRows() {return filteredStudents().map(s=>`<tr><td><div class="student-cell"><span class="mini-avatar">${escapeHTML(s.learner_id.slice(-2).toUpperCase())}</span><strong>${escapeHTML(s.display_name||s.learner_id)}</strong></div></td><td><span class="badge ${s.sid?'secure':'fragile'}">${escapeHTML(s.sid||'—')}</span></td><td>${escapeHTML(s.branch||'—')}</td><td><strong>${s.marks.score}/${s.marks.out_of}</strong> <span class="muted"> · ${s.marks.percentage}%</span></td><td>${badge(s.state)}</td><td>${s.marks.performance_percentage||0}%</td><td>${s.marks.secure_marks}</td><td>${escapeHTML(s.updated_at)}</td><td><button class="text-link" data-action="student" data-learner="${escapeHTML(s.learner_id)}">View →</button> <button class="button subtle danger small" data-action="remove-student" data-learner="${escapeHTML(s.learner_id)}" data-name="${escapeHTML(s.display_name||s.learner_id)}" title="Remove student from classroom">Remove</button></td></tr>`).join('')||'<tr><td colspan="9" class="muted" style="text-align:center;padding:30px">No students match your filters.</td></tr>';}
function teacher() {
    if(state.account.role!=='teacher')return empty('Class insights are private.','Only the classroom teacher can view class performance. You can view your own results in My performance.');
    if(!state.classId)return empty('No classroom selected.','Create or select a classroom from My classrooms first.');
    if(!state.skill){
        const list=state.classStudents||[];
        return header('THE TEACHER SPACE','Classroom Roster & Student SIDs',`Enrolled students in ${escapeHTML(state.classes.find(c=>c.id===state.classId)?.name||'selected classroom')}`)+
        `<div class="stats">${stat('Enrolled students',list.length,'Students in this classroom','♧')}${stat('Classroom code',state.classes.find(c=>c.id===state.classId)?.join_code||'—','Share with students to join','☷')}</div>`+
        `<div class="panel"><div class="panel-head"><div><h3>Classroom Roster</h3><p>Student names, SIDs, and enrollment</p></div><span class="badge">${list.length} students</span></div>`+
        `<div class="table-wrap"><table><thead><tr><th>Student</th><th>Student ID (SID)</th><th>Branch</th><th>Email</th><th>Action</th></tr></thead><tbody>`+
        (list.map(s=>`<tr><td><strong>${escapeHTML(s.name)}</strong></td><td><span class="badge ${s.sid?'secure':'fragile'}">${escapeHTML(s.sid||'—')}</span></td><td>${escapeHTML(s.branch||'—')}</td><td>${escapeHTML(s.email)}</td><td><button class="button subtle danger small" data-action="remove-student" data-learner="${escapeHTML(s.id)}" data-name="${escapeHTML(s.name)}">Remove</button></td></tr>`).join('')||'<tr><td colspan="5" class="muted" style="text-align:center;padding:30px">No students have joined this classroom yet. Share the classroom code to enroll students.</td></tr>')+
        `</tbody></table></div></div>`;
    }
    if(state.quizzes.find(q=>q.skill_id===state.skill)?.mode==='mcq')return examInsights();
    const students=state.heatmap.students||[], dist=state.heatmap.state_distribution||{}, avg=students.length?Math.round(students.reduce((a,s)=>a+s.marks.percentage,0)/students.length):0;
    const count=students.filter(s=>s.state!=='Secure').length;
    const currentQuiz=state.quizzes.find(q=>q.skill_id===state.skill);
    const quizId=currentQuiz?.id||'';
    const quizTitle=currentQuiz?.title||title(state.skill);
    return header('THE TEACHER SPACE','A clearer picture of your classroom.','Find the learners who need a nudge, and understand what kind.',`<div style="display:flex;gap:10px;align-items:center"><button class="button" data-action="export" ${students.length?'':'disabled'}>↓ Export CSV</button>${quizId?`<button class="button subtle danger" data-action="delete-quiz" data-quiz-id="${quizId}" data-title="${escapeHTML(quizTitle)}">Delete quiz</button>`:''}</div>`)+
    `<div class="stats">${stat('Enrolled students',students.length,'For the selected topic','♧')}${stat('Class average',`${avg}<small>%</small>`,'Mean of current student scores','↗')}${stat('Secure learners',dist.Secure||0,'Showing confident understanding','✧')}${stat('May need support',count,'Explore each learner’s evidence','◉')}</div><div class="grid-main"><div class="panel"><div class="panel-head"><div><h3>Understanding across the class</h3><p>Current learner states</p></div><span class="badge">${students.length} learners</span></div>${['Secure','Lucky / Fragile','Careless Slip','Deep Misconception'].map((label,i)=>`<div class="bar-row"><span>${label}</span><div class="progress"><span style="width:${students.length?(dist[label]||0)/students.length*100:0}%;background:${['#8c7ae1','#e5bc71','#85aad9','#d68fa5'][i]}"></span></div><strong>${dist[label]||0}</strong></div>`).join('')}<div class="note">Diagnostic states are clues to guide support. Review the evidence before choosing an intervention.</div></div><div class="panel"><div class="panel-head"><div><h3>Patterns worth a closer look</h3><p>Confirmed misconceptions · distinct learners</p></div></div>${Object.entries(state.heatmap.misconception_heatmap||{}).map(([code,n])=>`<div class="topic-row"><span class="topic-icon">?</span><div class="topic-info"><strong>${escapeHTML(title(code))}</strong><p>${n} learner${n===1?'':'s'} · review and reteach</p></div></div>`).join('')||'<div class="empty" style="padding:30px 10px"><span class="empty-icon">✧</span><p>No confirmed misconceptions in the latest responses.</p></div>'}</div></div><div class="panel"><div class="panel-head"><div><h3>The people behind the numbers</h3><p>Search, filter, and open a learner’s full performance</p></div></div><div class="toolbar"><input id="student-search" placeholder="Search name, email, SID or branch…" aria-label="Search learners" value="${escapeHTML(state.query)}"><select id="state-filter" aria-label="Filter diagnostic state">${['all','Secure','Lucky / Fragile','Careless Slip','Deep Misconception'].map(v=>`<option value="${v}" ${v===state.filter?'selected':''}>${v==='all'?'All learning states':v}</option>`).join('')}</select><select id="student-sort" aria-label="Sort students"><option value="id">Sort by learner ID</option><option value="score" ${state.sort==='score'?'selected':''}>Highest score first</option></select></div><div class="table-wrap"><table><thead><tr><th>Learner</th><th>SID</th><th>Branch</th><th>Score</th><th>Learning state</th><th>Performance</th><th>Secure marks</th><th>Last activity</th><th>Profile</th></tr></thead><tbody id="roster-body">${rosterRows()}</tbody></table></div>${!students.length?'<button class="button primary" data-action="seed" style="margin-top:20px">Invite your students →</button>':''}</div>`;
}
const sample=[
  {item_id:'eng_1',skill_id:'english_assessment',kind:'single',stem:'Choose the correct antonym for "Meticulous":',options:[{id:'A',text:'Careless',is_correct:true},{id:'B',text:'Diligent',is_correct:false},{id:'C',text:'Thorough',is_correct:false}]},
  {item_id:'eng_2',skill_id:'english_assessment',kind:'multiple',stem:'Select all words that are synonyms of "Ephemeral":',options:[{id:'A',text:'Fleeting',is_correct:true},{id:'B',text:'Transient',is_correct:true},{id:'C',text:'Permanent',is_correct:false}]}
];
function upload() {
    if(state.account.role!=='teacher')return empty('Only your teacher can publish quizzes.','Open Practice studio to take the quizzes assigned to your class.');
    return header('MAKE ROOM FOR NEW IDEAS','Publish a quiz to your classroom.','Set the rules, choose the questions, and keep results private to your class.')+`<div class="quiz-layout"><form id="upload-form" class="panel"><div class="panel-head"><h3>Quiz questions & timing</h3><button type="button" class="text-link" data-action="sample">Load sample ↗</button></div><label class="form-field">Quiz title<input name="title" required maxlength="128" placeholder="e.g. English Grammar & Comprehension"></label><div class="form-field"><span class="eyebrow">PUBLISHING MODE</span><div class="role-tabs" style="margin:10px 0"><label><input type="radio" name="schedule_mode" value="instant" checked> ⚡ Mode 1: Instant (Always Open)</label><label><input type="radio" name="schedule_mode" value="scheduled"> 📅 Mode 2: Calendar Scheduled</label></div></div><div id="schedule-fields" class="quiz-settings" hidden style="margin-top:0"><label class="form-field">Window start (Date & Time)<input type="datetime-local" name="start_time" id="schedule-start-time"></label><label class="form-field">Window end (Date & Time)<input type="datetime-local" name="end_time" id="schedule-end-time"></label></div><div class="quiz-settings"><label class="form-field">Overall quiz time (seconds)<input name="total_time_s" required type="number" min="10" max="86400" value="300"></label><label class="form-field">Questions per student<input name="question_count" required type="number" min="1" max="200" value="1"></label><label class="form-field" hidden>Default question time (seconds)<input name="question_time_s" required type="number" min="5" max="3600" value="30"></label></div><div class="quiz-settings" style="margin-top:0"><label class="form-field">Negative marking policy<select name="negative_marks"><option value="0">No negative marking (0 penalty)</option><option value="0.25">-0.25 marks per wrong answer (1/4 penalty)</option><option value="0.33">-0.33 marks per wrong answer (1/3 penalty)</option><option value="0.50">-0.50 marks per wrong answer (1/2 penalty)</option><option value="1.00">-1.00 mark per wrong answer (full penalty)</option></select></label></div><div class="note">MCQ format: supports single-choice and multiple-correct questions (exact correct set required). In Mode 1 (Instant), the test opens immediately. In Mode 2 (Calendar Scheduled), students can only attempt during the configured start/end window. Negative marking deducts penalties for wrong answers only; skipped questions receive 0 penalty.</div><label class="file-drop"><span class="empty-icon">↥</span><strong>Choose a question bank file</strong><p>PDF up to 3 MB or JSON up to 2 MB · Review extracted answers before publishing</p><input id="json-file" type="file" accept=".pdf,.json,application/pdf,application/json"></label><label for="json-editor" class="eyebrow">QUESTION BANK JSON</label><textarea class="code-editor" id="json-editor" spellcheck="false" placeholder="Paste a JSON question array" aria-label="Question bank JSON">${escapeHTML(state.uploadText)}</textarea><div class="note">PDF format: numbered questions, one option per line (A. Text), then Answer: A or Answer: A, C. Text PDFs only; scanned pages need OCR. <a href="/static/question-bank-template.pdf" download>Download sample PDF</a>.</div><div id="question-times" style="margin-top:20px"></div><label class="form-field"><input name="approved" type="checkbox" required> I reviewed the question text and answer key, and approve the grading & publishing policy.</label><div class="upload-actions"><button class="button primary" type="submit">Publish to this class →</button><button class="button" type="button" data-action="validate">✓ Validate JSON</button><button class="button subtle" type="button" data-action="download-sample">↓ Template</button></div></form><div class="panel"><span class="eyebrow">TEACHER CONTROLS</span><h3>Your class, your quiz.</h3><ul class="checklist"><li>Only students in this class can open this quiz.</li><li>Only you can view the class performance.</li><li>Students can view their own marks only.</li><li>Timers and scheduling windows are enforced on the server.</li><li>One timed attempt per student.</li></ul><div class="note">Published MCQ keys and assigned papers are frozen. Results appear after final submission. Single-choice and multiple-select questions are graded atomically.</div></div></div>`;
}
function render() {
    $('#page-label').textContent=labels[state.page];
    document.querySelectorAll('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===state.page);if(el.dataset.page===state.page)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    if(!state.account)return;
    $('#page').innerHTML=({classes:classrooms,dashboard:state.account.role==='teacher'?teacherOverview:dashboard,quiz,profile,teacher,upload}[state.page]||classrooms)();
}
async function refresh() {
    const generation=++state.generation;
    if(state.account?.role==='teacher'&&state.classId){try{state.classStudents=await api(`/api/classes/${state.classId}/students`);}catch(e){}}
    if(!state.skill){state.questions=[];state.review=[];state.profile={};state.heatmap={students:[]};render();return;}
    const skill=encodeURIComponent(state.skill);
    state.questions=await api(`/api/items/${skill}`);
    if(state.account.role==='teacher') {
        state.heatmap=await api(`/api/teacher/heatmap/${skill}`);
        if(!state.heatmap.students.some(s=>s.learner_id===state.learner))state.learner=state.heatmap.students[0]?.learner_id||'';
    }else {state.learner=state.account.id;state.heatmap={students:[]};}
    if(!state.learner){state.profile={};state.review=[];render();return;}
    const path=`${encodeURIComponent(state.learner)}/${skill}`;
    const [profileData,review]=await Promise.all([api(`/api/profile/${path}`),api(`/api/review/${path}`)]);
    if(generation!==state.generation)return;
    state.profile=profileData;state.review=review;render();
}
async function loadSkills() {
    state.classes=await api('/api/classes');
    if(!state.classes.some(c=>c.id===state.classId))state.classId=state.classes[0]?.id||'';
    $('#class-select').innerHTML=state.classes.length?state.classes.map(c=>`<option value="${escapeHTML(c.id)}">${escapeHTML(c.name)}</option>`).join(''):'<option value="">No classrooms</option>';
    $('#class-select').value=state.classId;
    if(state.page==='classes')render();
    state.quizzes=state.classId?await api(`/api/classes/${state.classId}/quizzes`):[];
    if(!state.quizzes.some(q=>q.skill_id===state.skill))state.skill=state.quizzes[0]?.skill_id||'';
    state.skills=state.quizzes.map(q=>q.skill_id);
    $('#skill-select').innerHTML=state.quizzes.length?state.quizzes.map(q=>`<option value="${q.skill_id}">${escapeHTML(q.title)}</option>`).join(''):'<option value="">No quizzes</option>';
    $('#skill-select').value=state.skill;
}
function navigate(page) { if(!labels[page])page='dashboard'; state.page=page;render(); if(location.hash!==`#${page}`)location.hash=page; }
function showQuestionTimers(items) {
    const target=$('#question-times');if(!target)return;
    target.innerHTML='<span class="eyebrow">REVIEW THE ANSWER KEY</span>'+items.map((item,i)=>`<article class="review-card"><strong>${i+1}. ${escapeHTML(item.stem)}</strong><p>${item.kind==='multiple'?'Multiple select · exact-set grading':'Single choice'}</p>${item.options.map(o=>`<label class="form-field"><input data-key-question="${i}" data-key-option="${escapeHTML(o.id)}" type="${item.kind==='multiple'?'checkbox':'radio'}" name="key-${i}" ${o.is_correct?'checked':''}> ${escapeHTML(o.id)}. ${escapeHTML(o.text)}</label>`).join('')}</article>`).join('');
}
function parseUpload() {
    const value=$('#json-editor').value;state.uploadText=value;let items;
    try{items=JSON.parse(value);}catch{throw new Error('The JSON is not valid. Check commas, quotes, and brackets, or start with the sample template.');}
    if(!Array.isArray(items)||!items.length)throw new Error('Provide a non-empty JSON array of questions.');
    const ids=new Set();
    for(const [i,item] of items.entries()) {
        if(!item||!item.item_id||!item.skill_id||!item.stem||!Array.isArray(item.options))throw new Error(`Question ${i+1} needs item_id, skill_id, stem, and an options array.`);
        if(ids.has(item.item_id))throw new Error(`Duplicate question ID: ${item.item_id}`);ids.add(item.item_id);
        if(item.kind!=='multiple'&&item.options.filter(o=>o.is_correct===true).length!==1)throw new Error(`Question ${i+1} must have exactly one correct option.`);
        if(new Set(item.options.map(o=>o.id)).size!==item.options.length)throw new Error(`Question ${i+1} has duplicate option labels.`);
        if(item.is_probe&&!item.parent_item_id)throw new Error(`Probe ${i+1} needs parent_item_id.`);
    }return items;
}
function download(content,filename,type) {const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function exportCSV() {
    const cell=value=>`"${String(value??'').replace(/^[=+@\-\t\r]/,"'$&").replaceAll('"','""')}"`;
    const mcq=state.quizzes.find(q=>q.skill_id===state.skill)?.mode==='mcq';
    const rows=mcq?[['Name','Email','SID','Branch','Learner ID','Assessment','Status','Score','Out of','Percentage','Correct','Wrong','Penalty','Skipped'],...(state.heatmap.students||[]).map(s=>[s.display_name,s.email,s.sid,s.branch,s.learner_id,title(state.skill),s.marks.status,...(s.marks.status==='graded'?[s.marks.score,s.marks.out_of,s.marks.percentage,s.marks.correct,s.marks.wrong,s.marks.penalty||0,s.marks.skipped]:['',s.marks.out_of,'','','','',''])])]:[['Learner ID','SID','Branch','Topic','Score','Out of','Percentage','Performance percentage','Secure marks','Fragile marks','Learning state','Last updated'],...filteredStudents().map(s=>[s.learner_id,s.sid,s.branch,state.skill,s.marks.score,s.marks.out_of,s.marks.percentage,s.marks.performance_percentage,s.marks.secure_marks,s.marks.fragile_marks,s.state,s.updated_at])];
    download('\uFEFF'+rows.map(row=>row.map(cell).join(',')).join('\r\n'),'class-performance.csv','text/csv;charset=utf-8');toast(mcq?'Final assessment report downloaded.':'Class report downloaded. Current filters are included.');
}
async function action(button) {
    clearError();const name=button.dataset.action;
    if(name==='navigate')navigate(button.dataset.target);
    if(name==='practice'){navigate('quiz');}
    if(name==='start')await startTimedQuiz();if(name==='retake')toast('Each assigned quiz allows one timed attempt.');
    if(name==='seed')navigate('classes');
    if(name==='topic'){state.attempt=null;state.skill=button.dataset.skill;storage.set('btn-skill',state.skill);$('#skill-select').value=state.skill;state.quizStarted=false;await refresh();navigate('quiz');}
    if(name==='student'){state.learner=button.dataset.learner;await refresh();navigate('profile');}
    if(name==='sample'){state.uploadText=JSON.stringify(sample,null,2);render();showQuestionTimers(sample);toast('Sample loaded. You can edit it before uploading.');}
    if(name==='validate'){const items=parseUpload();showQuestionTimers(items);toast(`Looks good: ${items.length} questions passed local validation. The server checks again on upload.`);}
    if(name==='download-sample')download(JSON.stringify(sample,null,2),'question-bank-template.json','application/json');
    if(name==='export')exportCSV();
    if(name==='open-class'){state.classId=button.dataset.classId;state.attempt=null;await loadSkills();await refresh();navigate(state.account.role==='teacher'?'teacher':'quiz');}
    if(name==='copy-room-code'){await navigator.clipboard.writeText(button.dataset.code);toast('Classroom code copied. Share it with your students.');}
    if(name==='copy-invite'){await navigator.clipboard.writeText($('#invite-link').value);toast('Invitation link copied.');}
    if(name==='remove-student'){
        const studentName=button.dataset.name||'this student';
        if(confirm(`Are you sure you want to remove ${studentName} from this classroom?`)){
            await api(`/api/classes/${state.classId}/students/${button.dataset.learner}`,{method:'DELETE'});
            toast(`Student ${studentName} removed from classroom.`);
            await loadSkills();await refresh();render();
        }
    }
    if(name==='delete-class'){
        const classId=button.dataset.classId;
        const className=button.dataset.name||'this classroom';
        if(confirm(`Are you sure you want to delete classroom "${className}"? This will delete all quizzes and results in this classroom.`)){
            await api(`/api/classes/${classId}`,{method:'DELETE'});
            toast(`Classroom "${className}" deleted.`);
            if(state.classId===classId)state.classId='';
            await loadSkills();await refresh();render();
        }
    }
    if(name==='delete-quiz'){
        const quizId=button.dataset.quizId;
        const quizTitle=button.dataset.title||'this quiz';
        if(confirm(`Are you sure you want to delete quiz "${quizTitle}"? All attempts and results for this quiz will be permanently deleted.`)){
            await api(`/api/quizzes/${quizId}`,{method:'DELETE'});
            toast(`Quiz "${quizTitle}" deleted.`);
            state.skill='';
            storage.set('btn-skill','');
            await loadSkills();await refresh();render();
        }
    }
    if(name==='skip')await timedSubmit(null,'Guessing');
    if(name==='exam-question'){state.examIndex=Number(button.dataset.index);render();updateTimers();}
    if(name==='exam-clear'){const q=state.attempt.questions[state.examIndex||0];state.examAnswers[q.item_id]=[];queueDraft();render();updateTimers();}
    if(name==='exam-submit'){
        const questions=state.attempt?.questions||[];
        const total=state.attempt?.total_questions||questions.length;
        const answered=questions.length?questions.filter(q=>(state.examAnswers?.[q.item_id]||[]).length>0).length:Object.values(state.examAnswers||{}).filter(v=>Array.isArray(v)&&v.length>0).length;
        const unanswered=Math.max(0,total-answered);
        if(typeof confirm==='function'&&!confirm(`Submit assessment? You have answered ${answered} of ${total} question${total===1?'':'s'} (${unanswered} unanswered). Are you sure you want to submit?`))return;
        await submitExam();
    }
}
function applyTheme() {const dark=storage.get('btn-theme','light')==='dark';document.body.classList.toggle('dark',dark);$('#theme-button').innerHTML=`${dark?'☀':'☾'} <span>Switch to ${dark?'light':'dark'} mode</span>`;}
document.addEventListener('click',e=>{const button=e.target.closest('[data-action]');if(button)action(button).catch(showError);});
document.addEventListener('input',e=>{if(e.target.id==='json-editor')state.uploadText=e.target.value;
    if(e.target.id==='student-search'){state.query=e.target.value;$('#roster-body').innerHTML=rosterRows();}});
document.addEventListener('change',async e=>{
    try{
        if(e.target.id==='state-filter'){state.filter=e.target.value;$('#roster-body').innerHTML=rosterRows();}
        if(e.target.id==='student-sort'){state.sort=e.target.value;$('#roster-body').innerHTML=rosterRows();}
        if(e.target.id==='class-select'){state.classId=e.target.value;state.attempt=null;await loadSkills();await refresh();}
        if(e.target.id==='skill-select'){state.attempt=null;clearError();state.skill=e.target.value;storage.set('btn-skill',state.skill);state.quizStarted=false;state.selected=null;state.confidence=null;await refresh();}

        if(e.target.id==='json-file'){const file=e.target.files[0];if(file){
            if(file.name.toLowerCase().endsWith('.pdf')){
                if(file.size>3*1024*1024)throw new Error('Choose a PDF smaller than 3 MB.');
                toast('Extracting PDF questions…');const form=new FormData();form.append('file',file);
                const result=await api('/api/question-bank/import-pdf',{method:'POST',body:form});
                state.uploadText=JSON.stringify(result.items,null,2);toast(result.message);
            }else{if(file.size>2*1024*1024)throw new Error('Choose a JSON file smaller than 2 MB.');state.uploadText=await file.text();}
            $('#json-editor').value=state.uploadText;showQuestionTimers(parseUpload());
        }}
        if(e.target.name==='schedule_mode'){
            const fields=$('#schedule-fields');
            if(fields){fields.hidden=e.target.value!=='scheduled';}
        }
        if(e.target.matches('[data-key-question]')){
            const items=JSON.parse($('#json-editor').value),item=items[Number(e.target.dataset.keyQuestion)];
            item.options.forEach(o=>{if(item.kind!=='multiple')o.is_correct=o.id===e.target.dataset.keyOption;else if(o.id===e.target.dataset.keyOption)o.is_correct=e.target.checked;});
            state.uploadText=JSON.stringify(items,null,2);$('#json-editor').value=state.uploadText;
        }
        if(e.target.matches('[data-exam-option]')){
            const q=state.attempt.questions[state.examIndex||0];
            state.examAnswers[q.item_id]=[...document.querySelectorAll('[data-exam-option]:checked')].map(el=>el.value);
            queueDraft();
        }
    }catch(error){showError(error);}
});
document.addEventListener('submit',async e=>{
    if(!['quiz-form','probe-form','upload-form','auth-form','create-class-form','invite-form','join-form','join-code-form'].includes(e.target.id))return;e.preventDefault();clearError();
    try{
        if(e.target.id==='auth-form'){await authenticate(e.target);return;}
        if(e.target.id==='create-class-form'){const data=new FormData(e.target);const created=await api('/api/classes',{method:'POST',body:JSON.stringify({name:data.get('name')})});state.classId=created.id;await loadSkills();render();toast('Classroom created.');return;}
        if(e.target.id==='invite-form'){const data=new FormData(e.target);const invite=await api(`/api/classes/${state.classId}/invitations`,{method:'POST',body:JSON.stringify({email:data.get('email')})});$('#invite-link').value=location.origin+'/?invite='+encodeURIComponent(invite.token);$('#invitation-result').hidden=false;toast('Invitation ready. Copy and share the link with your student.');return;}
        if(e.target.id==='join-code-form'){const data=new FormData(e.target);const result=await api('/api/classes/join',{method:'POST',body:JSON.stringify({code:data.get('code')})});state.classId=result.class_id;state.attempt=null;await loadSkills();await refresh();navigate('classes');toast(result.message);return;}
        if(e.target.id==='join-form'){const data=new FormData(e.target);await joinClass(data.get('token'));return;}
        if(e.target.id==='quiz-form'){const data=new FormData(e.target);await timedSubmit(data.get('answer'),data.get('confidence'));}

        if(e.target.id==='upload-form'){
            const items=parseUpload(),data=new FormData(e.target),button=e.target.querySelector('[type=submit]');
            if(!state.classId)throw new Error('Create or select a classroom first.');
            const scheduleMode=data.get('schedule_mode')||'instant';
            const negativeMarks=Number(data.get('negative_marks')||0);
            let startTime=null,endTime=null;
            if(scheduleMode==='scheduled'){
                const startVal=$('#schedule-start-time')?.value;
                const endVal=$('#schedule-end-time')?.value;
                if(!startVal||!endVal)throw new Error('Please select both window start and end dates/times.');
                const startMs=new Date(startVal).getTime();
                const endMs=new Date(endVal).getTime();
                if(isNaN(startMs)||isNaN(endMs))throw new Error('Please enter valid dates and times.');
                if(endMs<=startMs)throw new Error('Assessment window end time must be after start time.');
                startTime=new Date(startMs).toISOString();
                endTime=new Date(endMs).toISOString();
            }
            button.disabled=true;
            try{
                const result=await api(`/api/classes/${state.classId}/quizzes`,{
                    method:'POST',
                    body:JSON.stringify({
                        title:data.get('title'),
                        total_time_s:Number(data.get('total_time_s')),
                        question_time_s:30,
                        mode:'mcq',
                        question_count:Number(data.get('question_count')),
                        negative_marks:negativeMarks,
                        schedule_mode:scheduleMode,
                        start_time:startTime,
                        end_time:endTime,
                        items
                    })
                });
                state.skill=result.skill_id;await loadSkills();await refresh();toast('Quiz published to your classroom.');
            }finally{button.disabled=false;}
        }
    }catch(error){showError(error);}
});
$('#probe-dialog').addEventListener('cancel',e=>e.preventDefault());
$('#theme-button').addEventListener('click',()=>{storage.set('btn-theme',document.body.classList.contains('dark')?'light':'dark');applyTheme();});
$('#refresh-button').addEventListener('click',async()=>{clearError();try{await loadSkills();await refresh();toast('Workspace refreshed.');}catch(e){showError(e);}});
$('#logout-button').addEventListener('click',async()=>{try{await api('/api/auth/logout',{method:'POST'});location.reload();}catch(e){showError(e);}});
window.addEventListener('hashchange',()=>{if(state.account)navigate(location.hash.slice(1));});
function classrooms() {
    const isTeacher=state.account.role==='teacher';
    return header(isTeacher?'YOUR TEACHING SPACE':'YOUR LEARNING SPACE',isTeacher?'Bring your classroom together.':'A place for your next chapter.',isTeacher?'Create a class, share its 8-character code, and publish timed quizzes.':'Enter your teacher’s 8-character classroom code to join and explore your assigned quizzes.')+
    `<div class="class-grid">${state.classes.map(c=>`<article class="panel class-card"><span class="topic-icon">♧</span><h3>${escapeHTML(c.name)}</h3><p class="muted">${isTeacher?'Your private classroom':'You are a member of this classroom'}</p>${isTeacher?`<div class="room-code-box"><span>CLASSROOM CODE</span><strong class="room-code">${escapeHTML(c.join_code||'')}</strong><button class="button small" data-action="copy-room-code" data-code="${escapeHTML(c.join_code||'')}" aria-label="Copy classroom code">Copy code</button></div>`:''}<button class="button primary" data-action="open-class" data-class-id="${c.id}">Open classroom →</button>${isTeacher?` <button class="button subtle danger" data-action="delete-class" data-class-id="${c.id}" data-name="${escapeHTML(c.name)}">Delete</button>`:''}</article>`).join('')||'<div class="panel empty"><h2>No classrooms yet.</h2><p>'+ (isTeacher?'Create your first class below.':'Enter the classroom code shared by your teacher below.')+'</p></div>'}</div>`+
    (isTeacher?`<div class="grid-main"><form id="create-class-form" class="panel"><span class="eyebrow">START SOMETHING GOOD</span><h2>Create a classroom</h2><label class="form-field" style="margin-top:20px">Class name<input name="name" required maxlength="128" placeholder="e.g. Grade 10 · Computer Science"></label><button class="button primary">Create class →</button></form><form id="invite-form" class="panel"><span class="eyebrow">INVITE YOUR STUDENTS</span><h2>A seat at the table.</h2><p class="muted" style="font-size:12px;margin:12px 0">Invitation for: <strong>${escapeHTML(state.classes.find(c=>c.id===state.classId)?.name||'Select a classroom above')}</strong>. The student must sign in using this exact email.</p><label class="form-field">Student email<input name="email" type="email" required placeholder="student@example.com"></label><button class="button primary" ${state.classId?'':'disabled'}>Create invitation link →</button><div id="invitation-result" class="invitation-result" hidden><p class="note">Share this link with your student. It expires in 7 days and can be used once. No email is sent automatically.</p><input id="invite-link" aria-label="Invitation link" readonly><button class="button" type="button" data-action="copy-invite">Copy link</button></div></form></div>`:
    `<form id="join-code-form" class="panel" style="margin-bottom:22px"><span class="eyebrow">GOT A CLASSROOM CODE?</span><h2>Join your classroom.</h2><p class="muted" style="margin:12px 0">Enter the 8-character code your teacher shared. You will join immediately.</p><label class="form-field">Classroom code<input name="code" class="room-code-input" required minlength="8" maxlength="8" pattern="[A-Za-z0-9]{8}" placeholder="e.g. AB2CD3EF" autocomplete="off" autocapitalize="characters" spellcheck="false" aria-label="8-character classroom code"></label><button class="button primary">Join classroom →</button></form><form id="join-form" class="panel"><span class="eyebrow">HAVE AN INVITATION LINK INSTEAD?</span><h2>Join your classroom.</h2><p class="muted" style="margin:12px 0;font-size:12px">Open your teacher’s invitation link, or paste the invitation token here. Use the student email the teacher invited.</p><label class="form-field">Invitation token<input name="token" required value="${escapeHTML(state.inviteToken)}"></label><button class="button primary">Join class →</button></form>`);
}
function teacherOverview() {
    return header('YOUR TEACHING WORKSPACE',`Welcome, ${escapeHTML(state.account.name)}.`,'Keep your classroom organised, your assessments clear, and your students supported.')+
    `<div class="stats">${stat('Your classrooms',state.classes.length,'Owned by your teacher account','♧')}${stat('Quizzes in this class',state.quizzes.length,'Visible only to class members','☷')}${stat('Learners in this quiz',state.heatmap.students?.length||0,'Private class performance','◉')}${stat('Your role','Teacher','Class owner and quiz publisher','✧')}</div><div class="grid-main"><div class="panel"><span class="eyebrow">A CLEAR START</span><h2>Set your class up for progress.</h2><ul class="checklist"><li>Create a private classroom.</li><li>Share the classroom’s 8-character join code.</li><li>Upload a PDF question bank and approve its answer key.</li><li>Assign distinct papers and review final marks.</li></ul><button class="button primary" data-action="navigate" data-target="classes">Manage classrooms →</button></div><div class="panel"><span class="eyebrow">YOUR NEXT QUIZ</span><h2>Make the rules clear.</h2><p class="muted" style="margin:16px 0">Set a title, add questions, and choose how much time students get. The server enforces the assessment deadline.</p><button class="button primary" data-action="navigate" data-target="upload">Publish a quiz →</button></div></div>`;
}
let isExamFullscreen=false;
function requestFullscreenLock(){
    try{
        const el=document.documentElement;
        if(el.requestFullscreen){el.requestFullscreen().then(()=>{isExamFullscreen=true;}).catch(()=>{});}
        else if(el.webkitRequestFullscreen){el.webkitRequestFullscreen();isExamFullscreen=true;}
    }catch(_){}
}
function exitFullscreenLock(){
    try{
        if(document.fullscreenElement&&document.exitFullscreen){document.exitFullscreen().catch(()=>{});}
        else if(document.webkitFullscreenElement&&document.webkitExitFullscreen){document.webkitExitFullscreen();}
    }catch(_){}
    isExamFullscreen=false;
}
async function startTimedQuiz() {
    const quiz=state.quizzes.find(q=>q.skill_id===state.skill);if(!quiz)throw new Error('Select an assigned quiz first.');
    state.violations=0;
    requestFullscreenLock();
    const sentAt=Date.now();state.attempt=await api(`/api/quizzes/${quiz.id}/start`,{method:'POST'});
    state.serverOffset=Date.parse(state.attempt.server_time)-(sentAt+Date.now())/2;
    state.selected=null;state.confidence=null;if(state.attempt.mode==='mcq'){state.examAnswers=state.attempt.answers||{};state.examIndex=0;}render();updateTimers();
}
async function timedSubmit(option,confidence) {
    if(state.submitting||!state.attempt||state.attempt.finished)return;
    state.submitting=true;
    document.querySelectorAll('#quiz-form button').forEach(b=>b.disabled=true);
    try{
        const sentAt=Date.now();
        state.attempt=await api(`/api/attempts/${state.attempt.id}/answer`,{method:'POST',body:JSON.stringify({item_id:state.attempt.question.item_id,chosen_option:option,confidence})});
        state.serverOffset=Date.parse(state.attempt.server_time)-(sentAt+Date.now())/2;
        state.selected=null;state.confidence=null;await refresh();
        if(state.attempt.finished){exitFullscreenLock();toast('Quiz complete. Your marks are ready.');}
    }catch(error){showError(error);state.timerRetry=Date.now()+5000;}
    finally{state.submitting=false;render();updateTimers();}
}
function clockText(seconds){seconds=Math.max(0,Math.ceil(seconds));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}
function updateTimers(){
    const attempt=state.attempt;if(!attempt||attempt.finished)return;
    const timestamp=Date.now()+state.serverOffset;
    const overall=(Date.parse(attempt.deadline)-timestamp)/1000;
    if(attempt.mode==='mcq'){if($('#overall-timer'))$('#overall-timer').textContent=clockText((Date.parse(attempt.deadline)-timestamp)/1000);if(timestamp>=Date.parse(attempt.deadline)&&!state.submitting&&Date.now()>(state.timerRetry||0))submitExam().catch(showError);return;}
    const question=(Math.min(Date.parse(attempt.question_deadline),Date.parse(attempt.deadline))-timestamp)/1000;
    if($('#question-timer'))$('#question-timer').textContent=clockText(question);
    if($('#overall-timer'))$('#overall-timer').textContent=clockText(overall);
    if($('.timer-bar'))$('.timer-bar').classList.toggle('urgent',question<=10);
    if(question<=0&&!state.submitting&&Date.now()>(state.timerRetry||0))timedSubmit(null,'Guessing');
}
let authMode='login';
let authRole=state.inviteToken?'student':storage.get('btn-role','student');
function authScreen() {
    $('.layout').hidden=true;
    let screen=$('#auth-screen');if(!screen){screen=document.createElement('div');screen.id='auth-screen';document.body.append(screen);}
    const isStudent=authRole==='student';
    const isTeacher=authRole==='teacher';
    screen.innerHTML=`<div class="auth-screen"><div class="auth-story"><span class="eyebrow">BEYOND THE NUMBER</span><h1>Every learner.<br>Every answer.<br><span style="color:#c3b7ff">A bigger story.</span></h1><p>A private space for teachers and students to learn, assess, and grow together.</p></div><div class="auth-card"><span class="eyebrow">YOUR LEARNING WORKSPACE</span><h2>${authMode==='login'?'Welcome back.':'Start your next chapter.'}</h2><p class="muted">${state.inviteToken?'You have a classroom invitation. Sign in or create a student account with your invited email.':'Sign in with your email or SID no. to access your classrooms.'}</p><div id="auth-error" class="error-text" role="alert"></div><form id="auth-form">${authMode==='register'?'<label class="form-field">Your name<input name="name" autocomplete="name" required maxlength="128"></label>':''}<div class="role-tabs"><label><input type="radio" name="role" value="student" ${authRole==='student'?'checked':''}> Student login</label><label><input type="radio" name="role" value="teacher" ${authRole==='teacher'?'checked':''}> Teacher login</label></div><fieldset id="student-details" style="border:0;padding:0;margin:0" ${isStudent?'':'hidden disabled'}><label class="form-field">Student ID (SID no.)<input name="sid" maxlength="64" placeholder="e.g. 23CSE001"></label><label class="form-field">Branch<input name="branch" maxlength="128" placeholder="e.g. Computer Science"></label><p class="muted">Optional. Enter details to save or update them for your teacher. Leave blank to keep saved details.</p></fieldset>${authMode==='register'?`<fieldset id="teacher-details" style="border:0;padding:0;margin:0" ${isTeacher?'':'hidden disabled'}><label class="form-field">Teacher authorization code<input type="password" name="teacher_code" ${isTeacher?'required':''} placeholder="Teacher authorization code" autocomplete="current-password"></label></fieldset>`:''}<label class="form-field"><span id="auth-id-label">${authMode==='login'&&isStudent?'Student ID (SID no.) or Email':'Email'}</span><input type="${authMode==='login'&&isStudent?'text':'email'}" name="email" id="auth-email-input" autocomplete="${authMode==='login'?'username':'email'}" required maxlength="254" placeholder="${authMode==='login'&&isStudent?'Enter your SID no. (e.g. 23CSE001) or email':'teacher@college.example'}"></label><label class="form-field">Password<input type="password" name="password" autocomplete="${authMode==='login'?'current-password':'new-password'}" required minlength="10" maxlength="128" placeholder="At least 10 characters"></label><button class="button primary">${authMode==='login'?'Sign in':'Create account'} →</button></form><div class="auth-switch">${authMode==='login'?'New here?':'Already have an account?'} <button class="text-link" id="auth-toggle">${authMode==='login'?'Create an account':'Sign in'}</button></div><p class="auth-notice">Teachers create classes and publish quizzes. Students join with a classroom code or invitation and can see only their own results.</p></div></div>`;
    document.querySelectorAll('#auth-form input[name=role]').forEach(input=>input.onchange=()=>{
        authRole=input.value;
        const isStudent=authRole==='student';
        const isTeacher=authRole==='teacher';
        const sFields=$('#student-details');
        if(sFields){sFields.hidden=!isStudent;sFields.disabled=!isStudent;}
        const tFields=$('#teacher-details');
        if(tFields){
            tFields.hidden=!isTeacher;
            tFields.disabled=!isTeacher;
            const codeInput=tFields.querySelector('input[name=teacher_code]');
            if(codeInput){
                codeInput.required=isTeacher;
                codeInput.disabled=!isTeacher;
            }
        }
        const label=$('#auth-id-label');
        const emailInput=$('#auth-email-input');
        if(label){label.textContent=authMode==='login'&&isStudent?'Student ID (SID no.) or Email':'Email';}
        if(emailInput){
            emailInput.type=authMode==='login'&&isStudent?'text':'email';
            emailInput.placeholder=authMode==='login'&&isStudent?'Enter your SID no. (e.g. 23CSE001) or email':'teacher@college.example';
        }
    });
    $('#auth-toggle').onclick=()=>{authMode=authMode==='login'?'register':'login';authScreen();};
}
async function authenticate(form) {
    const values=new FormData(form),data=Object.fromEntries(values),button=form.querySelector('button');button.disabled=true;$('#auth-error').textContent='';
    try{authRole=data.role;storage.set('btn-role',authRole);state.account=await api('/api/auth/'+(authMode==='login'?'login':'register'),{method:'POST',body:JSON.stringify(data)});await openWorkspace();}
    catch(e){if($('#auth-error'))$('#auth-error').textContent=e.message;else showError(e);}
    finally{button.disabled=false;}
}
async function joinClass(token) {
    const text=String(token).trim();const parsed=text.includes('?invite=')?new URL(text).searchParams.get('invite'):text;
    const result=await api('/api/invitations/accept',{method:'POST',body:JSON.stringify({token:parsed})});state.classId=result.class_id;state.inviteToken='';history.replaceState(null,'',location.pathname+'#classes');await loadSkills();await refresh();toast(result.message);
}
async function openWorkspace() {
    if($('#auth-screen'))$('#auth-screen').remove();$('.layout').hidden=false;
    const isTeacher=state.account.role==='teacher';
    $('#account-name').textContent=state.account.name;$('#account-label').textContent=state.account.email+' · '+state.account.role;
    $('.avatar').textContent=state.account.name.slice(0,2).toUpperCase();
    document.querySelectorAll('[data-page="teacher"],[data-page="upload"],[data-role-section="teacher"]').forEach(el=>el.hidden=!isTeacher);
    state.learner=isTeacher?'':state.account.id;
    navigate(location.hash.slice(1)||'classes');
    await loadSkills();await refresh();
    if(state.inviteToken&&!isTeacher){try{await joinClass(state.inviteToken);}catch(e){showError(e);navigate('classes');}}
    $('#connection').textContent='Assessment server online';$('#connection').classList.add('online');
    render();
}
function examInsights(){
    const students=state.heatmap.students||[],graded=students.filter(s=>s.marks.status==='graded');
    const average=graded.length?(graded.reduce((n,s)=>n+s.marks.percentage,0)/graded.length).toFixed(1):'—';
    const currentQuiz=state.quizzes.find(q=>q.skill_id===state.skill);
    const quizId=currentQuiz?.id||'';
    const quizTitle=currentQuiz?.title||title(state.skill);
    return header('CLASS RESULTS',escapeHTML(title(state.skill)),'Final marks are visible only to you and the student.',`<div style="display:flex;gap:10px;align-items:center"><button class="button" data-action="export" ${students.length?'':'disabled'}>↓ Export CSV</button>${quizId?`<button class="button subtle danger" data-action="delete-quiz" data-quiz-id="${quizId}" data-title="${escapeHTML(quizTitle)}">Delete quiz</button>`:''}</div>`)+`<div class="stats">${stat('Enrolled',students.length,'Students in this classroom','♧')}${stat('Submitted',graded.length,'Graded assessments','✓')}${stat('In progress',students.filter(s=>s.marks.status==='in_progress').length,'Saved student attempts','◷')}${stat('Class average',average==='—'?average:average+'%','Submitted assessments only','↗')}</div><div class="panel table-wrap"><table><thead><tr><th>Student</th><th>Email</th><th>Student ID (SID)</th><th>Branch</th><th>Status</th><th>Marks</th><th>Percentage</th><th>Correct / Wrong / Skipped</th><th>Action</th></tr></thead><tbody>${students.map(s=>`<tr><td><strong>${escapeHTML(s.display_name)}</strong></td><td>${escapeHTML(s.email)}</td><td><span class="badge ${s.sid?'secure':'fragile'}">${escapeHTML(s.sid||'—')}</span></td><td>${escapeHTML(s.branch||'—')}</td><td>${s.marks.status==='graded'?'Submitted':s.marks.status==='in_progress'?'In progress':'Not started'}</td><td>${s.marks.status==='graded'?`${s.marks.score}/${s.marks.out_of}`:'—'}</td><td>${s.marks.status==='graded'?s.marks.percentage+'%':'—'}</td><td>${s.marks.status==='graded'?`${s.marks.correct} / ${s.marks.wrong} / ${s.marks.skipped}`:'—'}</td><td><button class="button subtle danger small" data-action="remove-student" data-learner="${escapeHTML(s.learner_id)}" data-name="${escapeHTML(s.display_name||s.learner_id)}" title="Remove student from classroom">Remove</button></td></tr>`).join('')||'<tr><td colspan="9" class="muted" style="text-align:center;padding:30px">Invite students to this classroom to see their results.</td></tr>'}</tbody></table></div>`;
}
function examView(heading) {
    const a=state.attempt;
    if(a.finished){
        const r=a.result;
        const penaltyInfo=r.penalty?` · -${r.penalty} penalty`:r.negative_marks>0?` · -0.0 penalty`:'' ;
        return heading+empty('Assessment submitted.',`${r.earned}/${r.maximum} marks · ${r.percentage}% · ${r.correct} correct · ${r.wrong} wrong${penaltyInfo} · ${r.skipped} skipped`,'<button class="button primary" data-action="navigate" data-target="profile">My results →</button>');
    }
    const i=state.examIndex||0,q=a.questions[i],picks=state.examAnswers[q.item_id]||[];
    const neg=a.negative_marks||0;
    const ruleText=neg>0?`+1 correct · -${neg} per wrong answer · 0 skipped.`:'+1 correct · 0 wrong or skipped.';
    return heading+`<div class="quiz-layout"><section class="panel quiz-panel"><div class="timer-bar"><span id="draft-status" role="status">Draft saved</span><span>Time remaining: <strong id="overall-timer">…</strong></span><span class="badge slip" style="font-size:11px" title="Fullscreen lockdown & anti-cheat active">🔒 Fullscreen & Anti-Cheat Active</span></div><div class="quiz-meta"><span>QUESTION ${i+1} OF ${a.total_questions}</span><span>${q.kind==='multiple'?'Select all correct answers':'Select one answer'}</span></div><h2 class="quiz-stem">${escapeHTML(q.stem)}</h2><div class="options">${q.options.map(o=>`<label class="option"><input data-exam-option type="${q.kind==='multiple'?'checkbox':'radio'}" name="exam-answer" value="${escapeHTML(o.id)}" ${picks.includes(o.id)?'checked':''}><span class="option-text">${escapeHTML(o.text)}</span></label>`).join('')}</div><div class="quiz-bottom"><button class="button subtle" data-action="exam-clear">Clear answer</button>${i>0?`<button class="button" data-action="exam-question" data-index="${i-1}">← Previous</button>`:''}${i<a.questions.length-1?`<button class="button primary" data-action="exam-question" data-index="${i+1}">Next →</button>`:''}</div></section><aside class="panel"><h3>Your question paper</h3><p class="muted">${Object.values(state.examAnswers).filter(v=>v.length).length} answered · ${a.total_questions} total</p><div class="exam-navigation">${a.questions.map((q,j)=>`<button class="button ${j===i?'primary':''}" data-action="exam-question" data-index="${j}" aria-label="Go to question ${j+1}">${j+1}${state.examAnswers[q.item_id]?.length?' ✓':''}</button>`).join('')}</div><p class="note">${ruleText} Select all and only correct options for multiple-select questions. Submission is final. The last saved draft submits when time expires.</p><button class="button primary" data-action="exam-submit" ${state.submitting?'disabled':''}>${state.submitting?'Submitting…':'Submit assessment'}</button></aside></div>`;
}
let draftQueue=Promise.resolve();
function queueDraft() {
    const id=state.attempt.id,answers=JSON.parse(JSON.stringify(state.examAnswers));
    if($('#draft-status'))$('#draft-status').textContent='Saving…';
    draftQueue=draftQueue.catch(()=>{}).then(async()=>{
        const response=await api(`/api/attempts/${id}/draft`,{method:'PUT',body:JSON.stringify({answers})});
        if(state.attempt?.id===id&&response.finished){state.attempt=response;await refresh();}
        if($('#draft-status'))$('#draft-status').textContent='Draft saved';
    });
    draftQueue.catch(error=>{if($('#draft-status'))$('#draft-status').textContent='Save failed — retry or submit';showError(error);});
}
async function submitExam() {
    if(state.submitting||state.attempt?.finished)return;
    state.submitting=true;render();
    try{
        await draftQueue.catch(()=>{});
        state.attempt=await api(`/api/attempts/${state.attempt.id}/submit`,{method:'POST',body:JSON.stringify({answers:state.examAnswers})});
        exitFullscreenLock();
        await refresh();
    }catch(error){state.timerRetry=Date.now()+5000;showError(error);}finally{state.submitting=false;render();}
}
let isUnloading=false;
window.addEventListener('beforeunload',()=>{isUnloading=true;});
window.addEventListener('pagehide',()=>{isUnloading=true;});
function handleViolation(reason){
    if(state.submitting||!state.attempt||state.attempt.finished||state.account?.role!=='student'||state.page!=='quiz'||isUnloading)return;
    state.violations=(state.violations||0)+1;
    if(state.violations<MAX_INTEGRITY_STRIKES){
        toast(`Warning (${state.violations}/${MAX_INTEGRITY_STRIKES}): ${reason} detected! Another violation will automatically submit your assessment.`);
    }else{
        toast(`${reason} detected! Your assessment was automatically submitted.`);
        if(state.attempt.mode==='mcq')submitExam().catch(showError);
        else timedSubmit(null,'Guessing').catch(showError);
    }
}
function checkFullscreenExit(){
    const inFs=!!(document.fullscreenElement||document.webkitFullscreenElement);
    if(inFs){isExamFullscreen=true;return;}
    if(isExamFullscreen&&!inFs&&state.account?.role==='student'&&state.attempt&&!state.attempt.finished&&state.page==='quiz'&&!isUnloading){
        isExamFullscreen=false;
        handleViolation('Fullscreen exited');
    }
}
document.addEventListener('fullscreenchange',checkFullscreenExit);
document.addEventListener('webkitfullscreenchange',checkFullscreenExit);
let tabSwitchTimer=null;
document.addEventListener('visibilitychange',()=>{
    if(tabSwitchTimer){clearTimeout(tabSwitchTimer);tabSwitchTimer=null;}
    if(!isUnloading&&document.hidden&&state.account?.role==='student'&&state.attempt&&!state.attempt.finished&&state.page==='quiz'){
        tabSwitchTimer=setTimeout(()=>{
            if(!isUnloading&&document.hidden&&state.account?.role==='student'&&state.attempt&&!state.attempt.finished&&state.page==='quiz'){
                handleViolation('Tab switch');
            }
        },1000);
    }
});
['copy','cut','paste','contextmenu'].forEach(evt=>{
    document.addEventListener(evt,e=>{
        if(state.account?.role==='student'&&state.attempt&&!state.attempt.finished&&state.page==='quiz'){
            e.preventDefault();
            toast(evt==='copy'||evt==='cut'?'Copying test content is disabled.':evt==='paste'?'Pasting is disabled.':'Right-click menu is disabled during tests.');
        }
    });
});
async function init(){
    applyTheme();
    try{state.account=await api('/api/auth/me');await openWorkspace();}
    catch(e){if(e.message==='Please sign in to continue.')authScreen();else{authScreen();$('#auth-error').textContent=e.message;}}
    setInterval(updateTimers,250);
}
init();
