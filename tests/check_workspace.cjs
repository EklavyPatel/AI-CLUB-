const fs = require('fs'), vm = require('vm');
const nodes = new Map();
const node = key => {
    if (!nodes.has(key)) nodes.set(key, {innerHTML:'',textContent:'',hidden:true,value:'30',
        classList:{toggle(){},contains(){return false},add(){}},addEventListener(){},
        setAttribute(){},removeAttribute(){},querySelector(){return node('button')},
        remove(){},append(){},click(){}});
    return nodes.get(key);
};
const context = vm.createContext({console, document:{querySelector:node,querySelectorAll:()=>[],
    addEventListener(){},body:node('body'),createElement:()=>node('created')},
    window:{addEventListener(){}},location:{hash:'',search:'',origin:'http://localhost:8000'},
    localStorage:{getItem(){return null},setItem(){}},setTimeout(){},clearTimeout(){},
    setInterval(){},URL,URLSearchParams,Blob,FormData,
    fetch:async()=>({ok:true,text:async()=>'[]'})});
vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/init\(\);\s*$/,''), context);
vm.runInContext(`
state.account={id:'teacher',role:'teacher',name:'Teacher',email:'teacher@example.com'};
state.classId='class1';state.classes=[{id:'class1',name:'Private class'}];
state.skill='python_recursion';state.skills=['python_recursion'];
state.quizzes=[{id:'quiz1',skill_id:state.skill,title:'Recursion',total_time_s:300}];
state.questions=[{item_id:'q1',stem:'Example <script>alert(1)</script>',options:[{id:'A',text:'Answer <b>A</b>'}]}];
state.profile={state:'Secure',marks:{score:1,out_of:1,percentage:100,performance_percentage:100,secure_marks:1,fragile_marks:0,wrong:0,answered:1,unanswered:0}};
state.review=[{item_id:'q1',stem:'Example',chosen_option:'A',answer_text:'Answer',correct:true,confidence:'Sure',time_ms:1000,story:'secure',attempts:1}];
state.heatmap={students:[{learner_id:'student_101',display_name:'Alex',email:'alex@example.com',state:'Secure',marks:state.profile.marks,updated_at:'2026-10-28'}],state_distribution:{Secure:1}};
for(const page of Object.keys(labels)){navigate(page);if(!$('#page').innerHTML.length)throw new Error('Empty teacher page '+page);}
state.account={id:'student_101',role:'student',name:'Alex'};
state.attempt={id:'attempt',current_index:0,total_questions:1,question:state.questions[0],finished:false,
    deadline:new Date(Date.now()+300000).toISOString(),question_deadline:new Date(Date.now()+30000).toISOString()};
navigate('quiz');updateTimers();
if($('#page').innerHTML.includes('<script>alert'))throw new Error('Unsafe question rendering');
if(!$('#page').innerHTML.includes('&lt;script&gt;'))throw new Error('Missing escaped content');
if(!$('#question-timer').textContent.includes(':'))throw new Error('Question timer missing');
if(!$('#overall-timer').textContent.includes(':'))throw new Error('Quiz timer missing');
navigate('teacher');if(!$('#page').innerHTML.includes('private'))throw new Error('Teacher view not guarded');
navigate('upload');if(!$('#page').innerHTML.includes('Only your teacher'))throw new Error('Upload view not guarded');
state.account.role='teacher';state.query='alex';state.filter='Secure';
if(filteredStudents().length!==1)throw new Error('Name search failed');
state.query='no-match';if(filteredStudents().length!==0)throw new Error('Search filter failed');
state.query='';state.filter='Deep Misconception';if(filteredStudents().length!==0)throw new Error('State filter failed');
navigate('upload');$('#json-editor').value=JSON.stringify(sample);
if(parseUpload().length!==2)throw new Error('Template invalid');
showQuestionTimers(sample);if(!$('#question-times').innerHTML.includes('data-question-time'))throw new Error('Per-question time editor missing');
$('#json-editor').value='{}';let rejected=false;try{parseUpload()}catch{rejected=true}if(!rejected)throw new Error('Invalid upload accepted');
authScreen();if(!$('#auth-screen').innerHTML.includes('Teacher login'))throw new Error('Teacher login missing');
if(!$('#auth-screen').innerHTML.includes('Student login'))throw new Error('Student login missing');
`, context);
console.log('Workspace checks passed: teacher/student views, login choices, escaped questions, both timers, roster filters, uploads, question time editor.');
