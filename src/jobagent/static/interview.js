import { voice } from './voice.js';

const node = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text != null) item.textContent = text;
  if (className) item.className = className;
  return item;
};
const status = document.querySelector('#interview-status');
const plan = document.querySelector('#interview-plan');
const turns = document.querySelector('#interview-turns');
const form = document.querySelector('#interview-answer-form');
const answer = document.querySelector('#interview-answer');
const reportBox = document.querySelector('#interview-report');
const levels = {1:'基础', 2:'进阶', 3:'挑战'};
let current = null;
let pending = false;
export let interviewOccupied = Boolean(localStorage.getItem('jobagent-interview'));

function announce(text, error = false) {
  status.textContent = text;
  status.className = `source-state${error ? ' error' : ''}`;
}
function setPending(value) {
  pending = value;
  interviewOccupied = value || current?.status === 'active';
  syncControls();
  window.dispatchEvent(new Event('interview-changed'));
}
function syncControls() {
  form.querySelectorAll('button,textarea,input').forEach(control => { control.disabled = pending || voice.busy; });
  voice.sync(pending);
}
window.addEventListener('voice-state', syncControls);
async function request(url, body) {
  const response = await fetch(url, body === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(e => e.msg).join('；') : data.detail);
  return data;
}
function feedbackList(parent, title, items) {
  parent.append(node('h4', title));
  const list = node('ul');
  items.forEach(text => list.append(node('li', text)));
  parent.append(list);
}
function render() {
  plan.replaceChildren(); turns.replaceChildren(); reportBox.replaceChildren();
  current.plan.forEach((topic, index) => {
    const item = node('div', undefined, 'dimension');
    item.append(node('strong', `${index + 1}. ${topic.title}`), node('p', topic.goal));
    plan.append(item);
  });
  current.turns.forEach((turn, index) => {
    if (current.status === 'completed' && turn.answer === null) return;
    const card = node('article', undefined, 'interview-turn');
    card.append(node('p', `第 ${index + 1} 题 · ${current.plan[turn.topic_index].title} · ${levels[turn.difficulty]}${turn.follow_up ? ' · 追问' : ''}`, 'job-meta'),
      node('h3', turn.question));
    if (turn.answer !== null) {
      if (turn.answer_mode === 'voice') card.append(node('p', '语音回答 · 模型理解的文字', 'job-meta'));
      card.append(node('div', turn.answer, 'candidate-answer'));
    }
    turns.append(card);
  });
  form.hidden = current.status !== 'active';
  announce(`${current.job_title} · ${current.status === 'active' ? '面试进行中，请回答下方问题。' : '面试已结束，可选择岗位开始新的面试。'}`);
  if (current.report) {
    const report = current.report;
    const header = node('div', undefined, 'score-header');
    header.append(node('div', `${report.total_score.toFixed(1)} / 100`, 'big-score'),
      node('p', `已回答 ${report.answered_topics} / ${report.total_topics} 个主题`));
    reportBox.append(header);
    const dimensions = node('div', undefined, 'dimension-grid');
    report.dimensions.forEach(d => {
      const item = node('div', undefined, 'dimension');
      item.append(node('span', `${d.label} · ${d.weight}%`), node('strong', d.score.toFixed(1)));
      dimensions.append(item);
    });
    const rubric = node('details');
    rubric.append(node('summary', '查看面试评分细则'), node('p', report.rule),
      node('p', '各维度：0 无有效信息；25 零散且关键错误；50 基本正确但缺关键细节；75 正确具体且有理由；100 完整准确且解释边界与权衡。'));
    reportBox.append(dimensions, rubric);
    report.topics.forEach(topic => {
      const card = node('article', undefined, 'requirement');
      card.append(node('h3', `${topic.title} · ${topic.score.toFixed(1)} 分${topic.assessed ? '' : '（未回答）'}`));
      topic.evidence.forEach(quote => card.append(node('blockquote', `回答依据：${quote}`)));
      if (topic.strengths.length) feedbackList(card, '表现较好', topic.strengths);
      feedbackList(card, '改进与练习', topic.improvements);
      feedbackList(card, '本题考察要点', topic.expected_points);
      reportBox.append(card);
    });
  }
}
export async function startInterview(input) {
  if (interviewOccupied) return;
  setPending(true);
  announce('正在根据简历与岗位制定问题计划…');
  document.querySelector('#interview-panel').scrollIntoView({behavior:'smooth', block:'start'});
  try {
    current = await request('/interviews', input);
    localStorage.setItem('jobagent-interview', current.id);
    answer.value = '';
    voice.clear();
    render();
  } catch (error) {
    announce(error instanceof TypeError ? '无法连接面试服务，请检查后端是否启动。' : error.message, true);
  } finally { setPending(false); }
}
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (pending || voice.busy) return;
  if (voice.mode === 'voice' && !voice.audio) {
    announce('请先录制回答，停止后试听并提交。', true); return;
  }
  if (voice.mode === 'text' && !answer.value.trim()) return;
  setPending(true);
  announce('正在分析回答并决定下一步…');
  try {
    if (voice.mode === 'voice') {
      const body = new FormData(); body.append('file', voice.audio, 'answer.wav');
      const response = await fetch(`/interviews/${current.id}/audio`, {method:'POST', body});
      const data = await response.json();
      if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(e => e.msg).join('；') : data.detail);
      current = data;
    } else {
      current = await request(`/interviews/${current.id}/answers`, {answer:answer.value});
    }
    answer.value = '';
    voice.clear();
    render();
    const last = turns.lastElementChild;
    if (last) last.scrollIntoView({behavior:'smooth', block:'center'});
  } catch (error) {
    announce(error instanceof TypeError ? (voice.mode === 'voice' ? '无法连接面试服务，录音仍保留，可重新提交。' : '无法连接面试服务，回答仍保留在输入框中。') : error.message, true);
  } finally { setPending(false); }
});
document.querySelector('#finish-interview').addEventListener('click', async () => {
  if (pending || voice.busy) return;
  setPending(true);
  announce('正在汇总已提交回答的评分…');
  try {
    current = await request(`/interviews/${current.id}/finish`, {});
    render();
    reportBox.scrollIntoView({behavior:'smooth', block:'start'});
  } catch (error) { announce(error.message, true); }
  finally { setPending(false); }
});
const saved = localStorage.getItem('jobagent-interview');
if (saved) {
  try { current = await request(`/interviews/${saved}`); render(); }
  catch (error) { announce(`无法恢复面试：${error.message}`, true); }
  finally { setPending(false); }
}
