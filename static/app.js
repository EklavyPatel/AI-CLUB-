'use strict';
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const title = value => String(state.quizzes?.find(q=>q.skill_id===value)?.title || value || '').replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());
const storage = {get(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } }, set(key,value) { try { localStorage.setItem(key,value); } catch {} }};
const state = {page:'dashboard', skills:[], skill:storage.get('btn-skill',''), learner:storage.get('btn-learner','student_' + Math.random().toString(36).slice(2,8)), questions:[], profile:{}, review:[], heatmap:{students:[]}, index:0, selected:null, confidence:null, quizStarted:false, skipAnswered:false, startedAt:0, submitting:false, pending:null, query:'', filter:'all', sort:'id', uploadText:'', loading:false, generation:0, account:null, classes:[], classId:'', quizzes:[], attempt:null, serverOffset:0, inviteToken:new URLSearchParams(location.search).get('invite')||''};
const labels = {classes:'My classrooms',dashboard:'Overview',quiz:'Practice studio',profile:'My performance',teacher:'Class insights',upload:'Question bank'};
const storyLabels = {secure:'Confident understanding',fragile_correct:'Correct, with uncertainty',knowledge_gap:'Concept needs practice',rushed:'Possibly rushed',unresolved:'More evidence needed',missed_condition:'A condition was missed',mistaken_rule:'A rule needs revisiting'};
function badge(value) { const cls = {'Secure':'secure','Lucky / Fragile':'fragile','Careless Slip':'slip','Deep Misconception':'deep'}[value] || ''; return `<span class="badge ${cls}">${escapeHTML(value || 'Unassessed')}</span>`; }
function toast(message) { $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('#toast').hidden=true,4500); }
function showError(error) { $('#error').textContent=error.message || String(error); $('#error').hidden=false; }
function clearError() { $('#error').hidden=true; }
async function api(path, options={}) {
    let response;
    try { response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}}); }
    catch { throw new Error('Cannot connect to the assessment server. Start uvicorn app.main:app --reload and open http://127.0.0.1:8000.'); }
    const text=await response.text(); let data;
    try { data=JSON.parse(text); } catch { throw new Error('This page needs the Python assessment server. Run uvicorn app.main:app --reload, then open http://127.0.0.1:8000 instead of Live Server.'); }
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
    return header('A LITTLE PROGRESS, EVERY DAY','Your next chapter starts here.','See where you stand. Understand what comes next.',`<span class="date-tag">${escapeHTML(new Date().toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short',year:'numeric'}))}</span>`)+
    `<div class="hero"><div class="hero-copy"><span class="eyebrow">UNDERSTANDING &gt; MEMORIZATION</span><h2>You’re more than<br><em>your last score.</em></h2><p>Turn every answer into a better understanding of how you learn. One thoughtful step at a time.</p><button class="button" data-action="practice">${m.answered?'Continue learning':'Start your first practice'} <span>↗</span></button></div><div class="hero-art" aria-hidden="true"><div class="orbit three"></div><div class="orbit"></div><div class="orbit two"></div><div class="art-core">✦</div><span class="float-chip first">✓ Build confidence</span><span class="float-chip second">↗ Make progress</span><span class="art-dot"></span></div></div>`+
    `<div class="stats">${stat('Your score',`${m.score}<small> / ${m.out_of}</small>`,'Latest answer per question','◷')}${stat('Raw marks percentage',`${m.percentage}<small>%</small>`,'Unanswered questions count as zero','↗')}${stat('Secure marks',m.secure_marks,'Correct answers tagged “Sure”','✧')}${stat('Questions attempted',`${m.answered}<small> / ${m.out_of}</small>`,`${m.unanswered} still to explore`,'☷')}</div>`+
    `<div class="grid-main"><div class="panel"><div class="panel-head"><div><h3>Your learning path</h3><p>A focused space to build your understanding</p></div><span class="badge">${state.skills.length} topics</span></div>${state.skills.length?state.skills.map(skill=>`<div class="topic-row"><span class="topic-icon">⌘</span><div class="topic-info"><strong>${escapeHTML(title(skill))}</strong><p>${skill===state.skill?`${m.answered} of ${m.out_of} questions explored`:'Ready when you are'}</p>${skill===state.skill?`<div class="progress"><span style="width:${m.out_of?m.answered/m.out_of*100:0}%"></span></div>`:''}</div><button class="button small" data-action="topic" data-skill="${escapeHTML(skill)}">${skill===state.skill&&m.answered?'Continue':'Explore'} →</button></div>`).join(''):`<div class="note">No topics yet. Load the demo classroom or add your own question bank.</div><button class="button primary" data-action="seed" style="margin-top:16px">Load demo classroom →</button>`}</div><div class="panel"><div class="panel-head"><div><h3>What’s behind your score?</h3><p>Confidence gives your marks more meaning</p></div><span class="violet">◉</span></div>${understanding()}</div></div>`+
    `<div class="panel"><div class="panel-head"><div><h3>A small step. A stronger foundation.</h3><p>Your next action, based on your actual responses</p></div><span class="badge">FOR YOU</span></div><div class="next-step"><span class="number">01</span><div><h3>${m.answered?'Keep the understanding growing':'Make your first move'}</h3><p>${escapeHTML(recommendation())}</p></div><button class="button" data-action="navigate" data-target="profile">My performance ↗</button></div></div>`;
}
function confidenceInputs(name) {return `<div class="confidence"><p>How confident do you feel?</p><div class="confidence-options">${[['Sure','✦'],['Unsure','◐'],['Guessing','?']].map(([v,icon])=>`<label class="confidence-choice"><input required type="radio" name="${name}" value="${v}" ${name==='confidence'&&state.confidence===v?'checked':''}>${icon} ${v}</label>`).join('')}</div></div>`;}
function questionHTML(question,name) {return `<h2 class="quiz-stem">${escapeHTML(question.stem)}</h2><div class="options">${question.options.map(o=>`<label class="option"><input required type="radio" name="${name}" value="${escapeHTML(o.id)}" ${name==='answer'&&state.selected===o.id?'checked':''}><span class="option-letter">${escapeHTML(o.id)}</span><span class="option-text">${escapeHTML(o.text)}</span></label>`).join('')}</div>`;}
function quiz() {
    const heading=header('THE PRACTICE STUDIO','A clear mind. A fair challenge.','Your teacher sets the deadlines. Marks and confidence performance are shown separately.');
    if(state.account.role==='teacher')return heading+empty('Quizzes are taken by students.','Publish a quiz from your question bank and review results in Class insights.','<button class="button primary" data-action="navigate" data-target="upload">Publish a quiz →</button>');
    if(!state.skill)return heading+empty('No quiz assigned yet.','Join a classroom using the link from your teacher. Published quizzes will appear here.','<button class="button primary" data-action="navigate" data-target="classes">My classrooms →</button>');
    const q=state.quizzes.find(q=>q.skill_id===state.skill);
    if(!state.attempt)return heading+`<div class="panel"><span class="eyebrow">${escapeHTML(q?.title)}</span><h2>Ready for your timed assessment?</h2><ul class="checklist"><li>${state.questions.length} questions · ${q?.total_time_s} seconds overall.</li><li>Each question has its own deadline, shown when it opens.</li><li>The server saves your timer. Refreshing does not reset it.</li><li>One attempt per quiz. Questions cannot be revisited.</li><li>Correct answers always earn 1 mark. Confidence affects only your additional performance score.</li></ul><button class="button primary" data-action="start">Start or resume quiz →</button></div>`;
    const attempt=state.attempt;
    if(attempt.finished)return heading+empty('Your quiz is complete.','Your submitted answers and marks have been saved. Unanswered or expired questions earn zero.','<button class="button primary" data-action="navigate" data-target="profile">View my results →</button>');
    return heading+`<div class="quiz-layout"><form id="quiz-form" class="panel quiz-panel"><div class="timer-bar"><span>Question: <strong id="question-timer">…</strong></span><span>Quiz remaining: <strong id="overall-timer">…</strong></span></div><div class="quiz-meta"><span>QUESTION ${attempt.current_index+1} OF ${attempt.total_questions}</span><span>${escapeHTML(q?.title)}</span></div><div class="progress"><span style="width:${attempt.current_index/attempt.total_questions*100}%"></span></div>${questionHTML(attempt.question,'answer')}${confidenceInputs('confidence')}<div class="quiz-bottom"><button class="button subtle" type="button" data-action="skip">Skip question</button><button class="button primary" type="submit" ${state.submitting?'disabled':''}>${state.submitting?'Saving…':'Save answer & continue →'}</button></div></form><div class="panel"><h3>How your score works</h3><ul class="checklist"><li>Correct + Sure + within time = 100% of this question’s performance weight.</li><li>Correct + Unsure = 85%.</li><li>Correct + Guessing = 75%.</li><li>Wrong, skipped, or expired = 0%.</li></ul><div class="note">Raw marks count every correct, on-time answer equally. One correct answer out of four always gives 1/4 (25%). The quiz timer continues when you leave this page.</div></div></div>`;
}
function profile() {
    if(!state.skill)return empty('Your results will appear here.','Join a classroom and take an assigned quiz first.');
    const m=marks();
    return header('YOUR LEARNING, IN FOCUS','There’s a story behind every score.','Look beyond the percentage. Find your strengths and your next steps.',`<button class="button primary" data-action="practice">Practice again ↗</button>`)+
    `<div class="grid-main"><div class="panel"><div class="panel-head"><div><h3>${escapeHTML(title(state.skill)||'Your assessment')}</h3><p>Latest attempts · ${escapeHTML(state.learner)}</p></div>${badge(state.profile.state)}</div><div class="big-score">${m.score}<span> / ${m.out_of}</span></div><div class="progress"><span style="width:${m.percentage}%"></span></div><div class="quiz-meta" style="margin-top:12px"><span>${m.percentage}% raw marks</span><span>${m.unanswered} unanswered</span></div><div class="note">Each on-time correct answer earns one mark. Confidence never removes a correct mark. Timed quizzes allow one attempt.</div></div><div class="panel"><div class="panel-head"><h3>Confidence & understanding</h3></div>${understanding()}</div></div><div class="panel" style="margin-bottom:22px"><span class="eyebrow">YOUR NEXT STEP</span><h3>${escapeHTML(state.profile.misconception_description||'Build from what you know.')}</h3><p class="muted" style="font-size:12px;margin-top:10px">${escapeHTML(recommendation())}</p></div><div class="panel"><div class="panel-head"><div><h3>Your answer journal</h3><p>Review your latest response to each question</p></div><span class="badge">${state.review.length} responses</span></div>${state.review.length?state.review.map((r,i)=>`<article class="review-card"><div class="review-top"><span class="eyebrow" style="margin:0">QUESTION ${i+1}</span><span class="badge ${r.correct?'secure':'fragile'}">${r.correct?'✓ Correct':'Needs practice'}</span></div><h3>${escapeHTML(r.stem)}</h3><p>Your answer: ${escapeHTML(r.chosen_option)} · ${escapeHTML(r.answer_text)}</p><div class="review-tags"><span>◉ ${escapeHTML(r.confidence)}</span><span>◷ ${(r.time_ms/1000).toFixed(1)}s</span><span>↻ ${r.attempts} attempt${r.attempts===1?'':'s'}</span><span>✦ ${escapeHTML(storyLabels[r.story]||'Evidence in progress')}</span></div></article>`).join(''):'<div class="empty"><div class="empty-icon">✎</div><h2>A fresh page.</h2><p>Your answer journal will appear here after your first practice.</p><button class="button primary" data-action="practice">Start learning →</button></div>'}</div>`;
}
function filteredStudents() {
    return (state.heatmap.students||[]).filter(s=>[s.learner_id,s.display_name,s.email].filter(Boolean).join(' ').toLowerCase().includes(state.query.toLowerCase())&&(state.filter==='all'||s.state===state.filter)).sort((a,b)=>state.sort==='score'?b.marks.percentage-a.marks.percentage:a.learner_id.localeCompare(b.learner_id));
}
function rosterRows() {return filteredStudents().map(s=>`<tr><td><div class="student-cell"><span class="mini-avatar">${escapeHTML(s.learner_id.slice(-2).toUpperCase())}</span><strong>${escapeHTML(s.display_name||s.learner_id)}</strong></div></td><td><strong>${s.marks.score}/${s.marks.out_of}</strong> <span class="muted"> · ${s.marks.percentage}%</span></td><td>${badge(s.state)}</td><td>${s.marks.performance_percentage||0}%</td><td>${s.marks.secure_marks}</td><td>${escapeHTML(s.updated_at)}</td><td><button class="text-link" data-action="student" data-learner="${escapeHTML(s.learner_id)}">View →</button></td></tr>`).join('')||'<tr><td colspan="7" class="muted" style="text-align:center;padding:30px">No students match your filters.</td></tr>';}
function teacher() {
    if(state.account.role!=='teacher')return empty('Class insights are private.','Only the classroom teacher can view class performance. You can view your own results in My performance.');
    const students=state.heatmap.students||[], dist=state.heatmap.state_distribution||{}, avg=students.length?Math.round(students.reduce((a,s)=>a+s.marks.percentage,0)/students.length):0;
    const count=students.filter(s=>s.state!=='Secure').length;
    return header('THE TEACHER SPACE','A clearer picture of your classroom.','Find the learners who need a nudge, and understand what kind.',`<button class="button" data-action="export" ${students.length?'':'disabled'}>↓ Export CSV</button>`)+
    `<div class="stats">${stat('Enrolled students',students.length,'For the selected topic','♧')}${stat('Class average',`${avg}<small>%</small>`,'Mean of current student scores','↗')}${stat('Secure learners',dist.Secure||0,'Showing confident understanding','✧')}${stat('May need support',count,'Explore each learner’s evidence','◉')}</div><div class="grid-main"><div class="panel"><div class="panel-head"><div><h3>Understanding across the class</h3><p>Current learner states</p></div><span class="badge">${students.length} learners</span></div>${['Secure','Lucky / Fragile','Careless Slip','Deep Misconception'].map((label,i)=>`<div class="bar-row"><span>${label}</span><div class="progress"><span style="width:${students.length?(dist[label]||0)/students.length*100:0}%;background:${['#8c7ae1','#e5bc71','#85aad9','#d68fa5'][i]}"></span></div><strong>${dist[label]||0}</strong></div>`).join('')}<div class="note">Diagnostic states are clues to guide support. Review the evidence before choosing an intervention.</div></div><div class="panel"><div class="panel-head"><div><h3>Patterns worth a closer look</h3><p>Confirmed misconceptions · distinct learners</p></div></div>${Object.entries(state.heatmap.misconception_heatmap||{}).map(([code,n])=>`<div class="topic-row"><span class="topic-icon">?</span><div class="topic-info"><strong>${escapeHTML(title(code))}</strong><p>${n} learner${n===1?'':'s'} · review and reteach</p></div></div>`).join('')||'<div class="empty" style="padding:30px 10px"><span class="empty-icon">✧</span><p>No confirmed misconceptions in the latest responses.</p></div>'}</div></div><div class="panel"><div class="panel-head"><div><h3>The people behind the numbers</h3><p>Search, filter, and open a learner’s full performance</p></div></div><div class="toolbar"><input id="student-search" placeholder="Search name or email…" aria-label="Search learners" value="${escapeHTML(state.query)}"><select id="state-filter" aria-label="Filter diagnostic state">${['all','Secure','Lucky / Fragile','Careless Slip','Deep Misconception'].map(v=>`<option value="${v}" ${v===state.filter?'selected':''}>${v==='all'?'All learning states':v}</option>`).join('')}</select><select id="student-sort" aria-label="Sort students"><option value="id">Sort by learner ID</option><option value="score" ${state.sort==='score'?'selected':''}>Highest score first</option></select></div><div class="table-wrap"><table><thead><tr><th>Learner</th><th>Score</th><th>Learning state</th><th>Performance</th><th>Secure marks</th><th>Last activity</th><th>Profile</th></tr></thead><tbody id="roster-body">${rosterRows()}</tbody></table></div>${!students.length?'<button class="button primary" data-action="seed" style="margin-top:20px">Invite your students →</button>':''}</div>`;
}
const sample=[{item_id:'calc_1',skill_id:'calculus_derivatives',stem:'What is the derivative of f(x) = x^3?',options:[{id:'A',text:'3x^2',is_correct:true},{id:'B',text:'3x',is_correct:false,misconception_code:'forgetting_power_decrement'},{id:'C',text:'x^2',is_correct:false,misconception_code:'omitting_coefficient'}],},{item_id:'calc_1_probe',skill_id:'calculus_derivatives',stem:'Differentiate g(x) = x^4 with respect to x.',options:[{id:'A',text:'4x^3',is_correct:true},{id:'B',text:'4x',is_correct:false,misconception_code:'forgetting_power_decrement'}],is_probe:true,parent_item_id:'calc_1'}];
function upload() {
    if(state.account.role!=='teacher')return empty('Only your teacher can publish quizzes.','Open Practice studio to take the quizzes assigned to your class.');
    return header('MAKE ROOM FOR NEW IDEAS','Publish a quiz to your classroom.','Set the rules, choose the questions, and keep results private to your class.')+`<div class="quiz-layout"><form id="upload-form" class="panel"><div class="panel-head"><h3>Quiz questions & timing</h3><button type="button" class="text-link" data-action="sample">Load sample ↗</button></div><label class="form-field">Quiz title<input name="title" required maxlength="128" placeholder="e.g. Recursion · Week 1"></label><div class="quiz-settings"><label class="form-field">Overall quiz time (seconds)<input name="total_time_s" required type="number" min="10" max="86400" value="300"></label><label class="form-field">Default question time (seconds)<input name="question_time_s" required type="number" min="5" max="3600" value="30"></label></div><div class="note">Set <code>expected_time_s</code> on a question in the JSON to override its default time. The overall quiz deadline always takes priority. Publishing creates a new quiz; existing attempts are preserved.</div><label class="file-drop"><span class="empty-icon">↥</span><strong>Choose a question bank file</strong><p>JSON format · up to 2 MB</p><input id="json-file" type="file" accept=".json,application/json"></label><label for="json-editor" class="eyebrow">QUESTION BANK JSON</label><textarea class="code-editor" id="json-editor" spellcheck="false" placeholder="Paste a JSON question array" aria-label="Question bank JSON">${escapeHTML(state.uploadText)}</textarea><div id="question-times" style="margin-top:20px"></div><div class="upload-actions"><button class="button primary" type="submit">Publish to this class →</button><button class="button" type="button" data-action="validate">✓ Validate JSON</button><button class="button subtle" type="button" data-action="download-sample">↓ Template</button></div></form><div class="panel"><span class="eyebrow">TEACHER CONTROLS</span><h3>Your class, your quiz.</h3><ul class="checklist"><li>Only students in this class can open this quiz.</li><li>Only you can view the class performance.</li><li>Students can view their own marks only.</li><li>Timers are enforced on the server.</li><li>One timed attempt per student.</li></ul><div class="note">The confidence score is an assessment rule, not a scientific measure of mastery. Keep raw marks visible when discussing results.</div></div></div>`;
}
function render() {
    $('#page-label').textContent=labels[state.page];
    document.querySelectorAll('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===state.page);if(el.dataset.page===state.page)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    if(!state.account)return;
    $('#page').innerHTML=({classes:classrooms,dashboard:state.account.role==='teacher'?teacherOverview:dashboard,quiz,profile,teacher,upload}[state.page]||classrooms)();
}
async function refresh() {
    const generation=++state.generation;
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
    state.quizzes=state.classId?await api(`/api/classes/${state.classId}/quizzes`):[];
    if(!state.quizzes.some(q=>q.skill_id===state.skill))state.skill=state.quizzes[0]?.skill_id||'';
    state.skills=state.quizzes.map(q=>q.skill_id);
    $('#skill-select').innerHTML=state.quizzes.length?state.quizzes.map(q=>`<option value="${q.skill_id}">${escapeHTML(q.title)}</option>`).join(''):'<option value="">No quizzes</option>';
    $('#skill-select').value=state.skill;
}
function navigate(page) { if(!labels[page])page='dashboard'; state.page=page;render(); if(location.hash!==`#${page}`)location.hash=page; }
function showQuestionTimers(items) {
    const target=$('#question-times');if(!target)return;
    target.innerHTML='<span class="eyebrow">PER-QUESTION TIME OVERRIDES</span>'+items.map((item,i)=>item.is_probe?'':`<label class="form-field">Question ${i+1}: ${escapeHTML(item.stem.slice(0,75))}<input data-question-time="${i}" type="number" min="1" max="3600" value="${item.expected_time_s||Number(document.querySelector('[name=question_time_s]').value)}" aria-label="Question ${i+1} time in seconds"></label>`).join('');
}
function parseUpload() {
    const value=$('#json-editor').value;state.uploadText=value;let items;
    try{items=JSON.parse(value);}catch{throw new Error('The JSON is not valid. Check commas, quotes, and brackets, or start with the sample template.');}
    if(!Array.isArray(items)||!items.length)throw new Error('Provide a non-empty JSON array of questions.');
    const ids=new Set();
    for(const [i,item] of items.entries()) {
        if(!item||!item.item_id||!item.skill_id||!item.stem||!Array.isArray(item.options))throw new Error(`Question ${i+1} needs item_id, skill_id, stem, and an options array.`);
        if(ids.has(item.item_id))throw new Error(`Duplicate question ID: ${item.item_id}`);ids.add(item.item_id);
        if(item.options.filter(o=>o.is_correct===true).length!==1)throw new Error(`Question ${i+1} must have exactly one correct option.`);
        if(new Set(item.options.map(o=>o.id)).size!==item.options.length)throw new Error(`Question ${i+1} has duplicate option labels.`);
        if(item.is_probe&&!item.parent_item_id)throw new Error(`Probe ${i+1} needs parent_item_id.`);
    }return items;
}
function download(content,filename,type) {const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function exportCSV() {
    const cell=value=>`"${String(value??'').replace(/^[=+@\-\t\r]/,"'$&").replaceAll('"','""')}"`;
    const rows=[['Learner ID','Topic','Score','Out of','Percentage','Performance percentage','Secure marks','Fragile marks','Learning state','Last updated'],...filteredStudents().map(s=>[s.learner_id,state.skill,s.marks.score,s.marks.out_of,s.marks.percentage,s.marks.performance_percentage,s.marks.secure_marks,s.marks.fragile_marks,s.state,s.updated_at])];
    download('\uFEFF'+rows.map(row=>row.map(cell).join(',')).join('\r\n'),'class-performance.csv','text/csv;charset=utf-8');toast('Class report downloaded. Current filters are included.');
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
    if(name==='copy-invite'){await navigator.clipboard.writeText($('#invite-link').value);toast('Invitation link copied.');}
    if(name==='skip')await timedSubmit(null,'Guessing');
}
function applyTheme() {const dark=storage.get('btn-theme','light')==='dark';document.body.classList.toggle('dark',dark);$('#theme-button').innerHTML=`${dark?'☀':'☾'} <span>Switch to ${dark?'light':'dark'} mode</span>`;}
document.addEventListener('click',e=>{const button=e.target.closest('[data-action]');if(button)action(button).catch(showError);});
document.addEventListener('input',e=>{if(e.target.id==='json-editor')state.uploadText=e.target.value;if(e.target.matches('[data-question-time]')){try{const items=JSON.parse($('#json-editor').value);items[Number(e.target.dataset.questionTime)].expected_time_s=Number(e.target.value);state.uploadText=JSON.stringify(items,null,2);$('#json-editor').value=state.uploadText;}catch{}}
    if(e.target.id==='student-search'){state.query=e.target.value;$('#roster-body').innerHTML=rosterRows();}});
document.addEventListener('change',async e=>{
    try{
        if(e.target.id==='state-filter'){state.filter=e.target.value;$('#roster-body').innerHTML=rosterRows();}
        if(e.target.id==='student-sort'){state.sort=e.target.value;$('#roster-body').innerHTML=rosterRows();}
        if(e.target.id==='class-select'){state.classId=e.target.value;state.attempt=null;await loadSkills();await refresh();}
        if(e.target.id==='skill-select'){state.attempt=null;clearError();state.skill=e.target.value;storage.set('btn-skill',state.skill);state.quizStarted=false;state.selected=null;state.confidence=null;await refresh();}

        if(e.target.id==='json-file'){const file=e.target.files[0];if(file){if(file.size>2*1024*1024)throw new Error('Choose a JSON file smaller than 2 MB.');state.uploadText=await file.text();$('#json-editor').value=state.uploadText;toast(`${file.name} loaded. Validate to customise question timers.`);}}
    }catch(error){showError(error);}
});
document.addEventListener('submit',async e=>{
    if(!['quiz-form','probe-form','upload-form','auth-form','create-class-form','invite-form','join-form'].includes(e.target.id))return;e.preventDefault();clearError();
    try{
        if(e.target.id==='auth-form'){await authenticate(e.target);return;}
        if(e.target.id==='create-class-form'){const data=new FormData(e.target);const created=await api('/api/classes',{method:'POST',body:JSON.stringify({name:data.get('name')})});state.classId=created.id;await loadSkills();render();toast('Classroom created.');return;}
        if(e.target.id==='invite-form'){const data=new FormData(e.target);const invite=await api(`/api/classes/${state.classId}/invitations`,{method:'POST',body:JSON.stringify({email:data.get('email')})});$('#invite-link').value=location.origin+'/?invite='+encodeURIComponent(invite.token);$('#invitation-result').hidden=false;toast('Invitation ready. Copy and share the link with your student.');return;}
        if(e.target.id==='join-form'){const data=new FormData(e.target);await joinClass(data.get('token'));return;}
        if(e.target.id==='quiz-form'){const data=new FormData(e.target);await timedSubmit(data.get('answer'),data.get('confidence'));}

        if(e.target.id==='upload-form'){
            const items=parseUpload(),data=new FormData(e.target),button=e.target.querySelector('[type=submit]');
            if(!state.classId)throw new Error('Create or select a classroom first.');
            button.disabled=true;
            try{
                const result=await api(`/api/classes/${state.classId}/quizzes`,{method:'POST',body:JSON.stringify({title:data.get('title'),total_time_s:Number(data.get('total_time_s')),question_time_s:Number(data.get('question_time_s')),items})});
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
    return header(isTeacher?'YOUR TEACHING SPACE':'YOUR LEARNING SPACE',isTeacher?'Bring your classroom together.':'A place for your next chapter.',isTeacher?'Create a class, invite students by email, and publish timed quizzes.':'Accept your teacher’s invitation and explore your assigned quizzes.')+
    `<div class="class-grid">${state.classes.map(c=>`<article class="panel class-card"><span class="topic-icon">♧</span><h3>${escapeHTML(c.name)}</h3><p class="muted">${isTeacher?'Your private classroom':'You are a member of this classroom'}</p><button class="button primary" data-action="open-class" data-class-id="${c.id}">Open classroom →</button></article>`).join('')||'<div class="panel empty"><h2>No classrooms yet.</h2><p>'+ (isTeacher?'Create your first class below.':'Join with the invitation link from your teacher.')+'</p></div>'}</div>`+
    (isTeacher?`<div class="grid-main"><form id="create-class-form" class="panel"><span class="eyebrow">START SOMETHING GOOD</span><h2>Create a classroom</h2><label class="form-field" style="margin-top:20px">Class name<input name="name" required maxlength="128" placeholder="e.g. Grade 10 · Computer Science"></label><button class="button primary">Create class →</button></form><form id="invite-form" class="panel"><span class="eyebrow">INVITE YOUR STUDENTS</span><h2>A seat at the table.</h2><p class="muted" style="font-size:12px;margin:12px 0">Invitation for: <strong>${escapeHTML(state.classes.find(c=>c.id===state.classId)?.name||'Select a classroom above')}</strong>. The student must sign in using this exact email.</p><label class="form-field">Student email<input name="email" type="email" required placeholder="student@example.com"></label><button class="button primary" ${state.classId?'':'disabled'}>Create invitation link →</button><div id="invitation-result" class="invitation-result" hidden><p class="note">Share this link with your student. It expires in 7 days and can be used once. No email is sent automatically.</p><input id="invite-link" aria-label="Invitation link" readonly><button class="button" type="button" data-action="copy-invite">Copy link</button></div></form></div>`:
    `<form id="join-form" class="panel"><span class="eyebrow">GOT AN INVITATION?</span><h2>Join your classroom.</h2><p class="muted" style="margin:12px 0;font-size:12px">Open your teacher’s invitation link, or paste the invitation token here. Use the student email the teacher invited.</p><label class="form-field">Invitation token<input name="token" required value="${escapeHTML(state.inviteToken)}"></label><button class="button primary">Join class →</button></form>`);
}
function teacherOverview() {
    return header('YOUR TEACHING WORKSPACE',`Welcome, ${escapeHTML(state.account.name)}.`,'Keep your classroom organised, your assessments clear, and your students supported.')+
    `<div class="stats">${stat('Your classrooms',state.classes.length,'Owned by your teacher account','♧')}${stat('Quizzes in this class',state.quizzes.length,'Visible only to class members','☷')}${stat('Learners in this quiz',state.heatmap.students?.length||0,'Private class performance','◉')}${stat('Your role','Teacher','Class owner and quiz publisher','✧')}</div><div class="grid-main"><div class="panel"><span class="eyebrow">A CLEAR START</span><h2>Set your class up for progress.</h2><ul class="checklist"><li>Create a private classroom.</li><li>Invite a student using their email address.</li><li>Publish questions with per-question and overall time limits.</li><li>Review raw marks alongside confidence performance.</li></ul><button class="button primary" data-action="navigate" data-target="classes">Manage classrooms →</button></div><div class="panel"><span class="eyebrow">YOUR NEXT QUIZ</span><h2>Make the rules clear.</h2><p class="muted" style="margin:16px 0">Set a title, add questions, and choose how much time students get. The server enforces both deadlines.</p><button class="button primary" data-action="navigate" data-target="upload">Publish a quiz →</button></div></div>`;
}
async function startTimedQuiz() {
    const quiz=state.quizzes.find(q=>q.skill_id===state.skill);if(!quiz)throw new Error('Select an assigned quiz first.');
    const sentAt=Date.now();state.attempt=await api(`/api/quizzes/${quiz.id}/start`,{method:'POST'});
    state.serverOffset=Date.parse(state.attempt.server_time)-(sentAt+Date.now())/2;
    state.selected=null;state.confidence=null;render();updateTimers();
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
        if(state.attempt.finished)toast('Quiz complete. Your marks are ready.');
    }catch(error){showError(error);state.timerRetry=Date.now()+5000;}
    finally{state.submitting=false;render();updateTimers();}
}
function clockText(seconds){seconds=Math.max(0,Math.ceil(seconds));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}
function updateTimers(){
    const attempt=state.attempt;if(!attempt||attempt.finished)return;
    const timestamp=Date.now()+state.serverOffset;
    const overall=(Date.parse(attempt.deadline)-timestamp)/1000;
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
    screen.innerHTML=`<div class="auth-screen"><div class="auth-story"><span class="eyebrow">BEYOND THE NUMBER</span><h1>Every learner.<br>Every answer.<br><span style="color:#c3b7ff">A bigger story.</span></h1><p>A private space for teachers and students to learn, assess, and grow together.</p></div><div class="auth-card"><span class="eyebrow">YOUR LEARNING WORKSPACE</span><h2>${authMode==='login'?'Welcome back.':'Start your next chapter.'}</h2><p class="muted">${state.inviteToken?'You have a classroom invitation. Sign in or create a student account with your invited email.':'Sign in with your email to access your classrooms.'}</p><div id="auth-error" class="error-text" role="alert"></div><form id="auth-form">${authMode==='register'?'<label class="form-field">Your name<input name="name" autocomplete="name" required maxlength="128"></label>':''}<div class="role-tabs"><label><input type="radio" name="role" value="student" ${authRole==='student'?'checked':''}> Student login</label><label><input type="radio" name="role" value="teacher" ${authRole==='teacher'?'checked':''}> Teacher login</label></div><label class="form-field">Email<input type="email" name="email" autocomplete="email" required maxlength="254"></label><label class="form-field">Password<input type="password" name="password" autocomplete="${authMode==='login'?'current-password':'new-password'}" required minlength="10" maxlength="128" placeholder="At least 10 characters"></label><button class="button primary">${authMode==='login'?'Sign in':'Create account'} →</button></form><div class="auth-switch">${authMode==='login'?'New here?':'Already have an account?'} <button class="text-link" id="auth-toggle">${authMode==='login'?'Create an account':'Sign in'}</button></div><p class="auth-notice">Teachers create classes and publish quizzes. Students join by invitation and can see only their own results.</p></div></div>`;
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
    document.querySelectorAll('[data-page="teacher"],[data-page="upload"]').forEach(el=>el.hidden=!isTeacher);
    state.learner=isTeacher?'':state.account.id;
    navigate(location.hash.slice(1)||'classes');
    await loadSkills();await refresh();
    if(state.inviteToken&&!isTeacher){try{await joinClass(state.inviteToken);}catch(e){showError(e);navigate('classes');}}
    $('#connection').textContent='Assessment server online';$('#connection').classList.add('online');
}
async function init(){
    applyTheme();
    try{state.account=await api('/api/auth/me');await openWorkspace();}
    catch(e){if(e.message==='Please sign in to continue.')authScreen();else{authScreen();$('#auth-error').textContent=e.message;}}
    setInterval(updateTimers,250);
}
init();
