import { startInterview, interviewOccupied } from './interview.js?v=voice-v1';
import './resume-editor.js';

const el = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const api = async (url, body) => {
  const response = await fetch(url, body === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('；') : data.detail);
  return data;
};
const sourceNames = { boss:'BOSS 直聘', zhilian:'智联招聘', manual:'用户提供' };
const stateNames = { met:'已命中', partial:'部分命中', missing:'简历未体现' };
const reportBox = document.querySelector('#match-report');
const jobsBox = document.querySelector('#job-list');
const collectionStatus = document.querySelector('#collection-status');
let resume = null;
let jobs = [];
let matching = false;
let rubric;
function message(target, text, error = false) {
  target.replaceChildren(el('div', text, `source-state${error ? ' error' : ''}`));
}
function renderJobs() {
  jobsBox.replaceChildren();
  jobs.forEach(job => {
    const card = el('article', undefined, 'job-card');
    card.append(el('h3', job.title), el('div', [job.company, job.city].filter(Boolean).join(' · ') || sourceNames[job.source], 'job-meta'),
      el('div', job.salary || '薪资未公开', 'salary'));
    const details = el('details');
    details.append(el('summary', '查看完整岗位描述'), el('p', job.raw_text, 'jd-text'));
    const actions = el('div', undefined, 'job-actions');
    const link = el(job.url ? 'a' : 'span', job.url ? `${sourceNames[job.source]}原文 ↗` : sourceNames[job.source], 'job-meta');
    if (job.url) {
      link.href = job.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    }
    const button = el('button', resume ? '生成匹配报告' : '请先解析简历', 'action');
    button.disabled = !resume || matching;
    button.addEventListener('click', () => matchJob(job));
    actions.append(link, button);
    const interview = el('button', '开始模拟面试', 'action');
    interview.disabled = !resume || interviewOccupied;
    interview.addEventListener('click', () => startInterview({resume, job}));
    actions.append(interview);
    card.append(details, actions);
    jobsBox.append(card);
  });
}
function renderReport(report, job) {
  reportBox.replaceChildren();
  const header = el('div', undefined, 'score-header');
  const score = el('div', report.total_score.toFixed(1), 'big-score');
  score.append(el('small', ' / 100'));
  const description = el('div');
  description.append(el('h3', job.title), el('p', report.summary));
  header.append(score, description);
  const dimensions = el('div', undefined, 'dimension-grid');
  report.dimensions.forEach(item => {
    const box = el('div', undefined, 'dimension');
    box.append(el('span', `${item.label} · 权重 ${item.weight.toFixed(1)}%`),
      el('strong', item.score.toFixed(1)));
    dimensions.append(box);
  });
  const rules = el('details');
  rules.append(el('summary', '查看评分细则'), el('p', rubric.rule, 'jd-text'));
  reportBox.append(header, dimensions, rules,
    el('p', '“简历未体现”表示材料没有足够证据，不代表你实际不具备能力。', 'workflow-note'));
  report.requirements.forEach(item => {
    const row = el('article', undefined, 'requirement');
    const title = el('h4');
    title.append(el('span', stateNames[item.status], `state-tag ${item.status}`),
      document.createTextNode(item.requirement));
    row.append(title, el('p', item.required ? '硬性要求' : '优先 / 加分项', 'job-meta'),
      el('blockquote', `岗位原文：${item.jd_evidence}`), el('p', item.explanation));
    if (item.resume_evidence.length) row.append(el('blockquote', `简历依据：${item.resume_evidence.join('；')}`));
    if (item.suggestion) row.append(el('p', `补足建议：${item.suggestion}`, 'advice'));
    reportBox.append(row);
  });
  const saved = el('p', '配对与报告已保存到本地评估集。', 'job-meta');
  const evaluation = el('a', ' 前往独立人工标注 ↗');
  evaluation.href = '/evaluation';
  saved.append(evaluation);
  reportBox.append(saved);
}
async function matchJob(job) {
  matching = true;
  renderJobs();
  message(reportBox, `正在对照 ${job.title} 的要求，生成匹配报告…`);
  document.querySelector('#match-panel').scrollIntoView({ behavior:'smooth', block:'start' });
  try {
    const report = await api('/matches', { resume, job });
    renderReport(report, job);
  } catch (error) {
    message(reportBox, error instanceof TypeError ? '无法连接匹配服务，请检查后端是否启动。' : error.message, true);
  } finally {
    matching = false;
    renderJobs();
  }
}
window.addEventListener('resume-parsed', event => { resume = event.detail; renderJobs(); });
window.addEventListener('interview-changed', renderJobs);
window.addEventListener('resume-cleared', () => {
  resume = null;
  renderJobs();
  message(reportBox, '请先完成简历解析，再选择岗位生成匹配报告。');
});
document.querySelector('#job-search').addEventListener('submit', async event => {
  event.preventDefault();
  const controls = [...event.target.querySelectorAll('select,button')];
  const request = { role:document.querySelector('#job-role').value,
    city:document.querySelector('#job-city').value, source:document.querySelector('#job-source').value };
  controls.forEach(control => { control.disabled = true; });
  jobs = jobs.filter(job => job.source === 'manual');
  renderJobs();
  message(collectionStatus, '正在读取所选平台的公开岗位信息…');
  try {
    const data = await api('/jobs/collect', request);
    collectionStatus.replaceChildren();
    data.sources.forEach(source => collectionStatus.append(el('div',
      `${sourceNames[source.source]}：${source.message}`, `source-state${source.status === 'success' ? '' : ' error'}`)));
    jobs = [...jobs, ...data.jobs];
    renderJobs();
    if (!jobs.length) collectionStatus.append(el('p', '本次未获取到完整 JD。', 'none'));
  } catch (error) {
    message(collectionStatus, error instanceof TypeError ? '无法连接采集服务。' : error.message, true);
  } finally {
    controls.forEach(control => { control.disabled = false; });
  }
});
for (const mode of ['online', 'manual']) {
  document.querySelector(`#${mode}-tab`).addEventListener('click', () => {
    for (const value of ['online', 'manual']) {
      document.querySelector(`#${value}-tab`).setAttribute('aria-selected', String(value === mode));
      document.querySelector(`#${value}-jobs`).hidden = value !== mode;
    }
  });
}
document.querySelectorAll('[name="job-format"]').forEach(radio => radio.addEventListener('change', () => {
  const fileMode = radio.value === 'file';
  const file = document.querySelector('#job-upload-file');
  const text = document.querySelector('#job-upload-text');
  file.disabled = !fileMode; file.required = fileMode;
  text.disabled = fileMode; text.required = !fileMode;
  document.querySelector('#job-file-area').hidden = !fileMode;
  document.querySelector('#job-text-area').hidden = fileMode;
}));
document.querySelector('#job-upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#add-job-button');
  const status = document.querySelector('#job-upload-status');
  button.disabled = true;
  message(status, '正在读取招聘信息…');
  const body = new FormData(event.target);
  body.delete('job-format');
  try {
    const response = await fetch('/jobs/upload', {method:'POST', body});
    const job = await response.json();
    if (!response.ok) throw new Error(Array.isArray(job.detail) ? job.detail.map(item => item.msg).join('；') : job.detail);
    jobs.unshift(job);
    renderJobs();
    message(status, resume ? '招聘信息已添加，点击下方“生成匹配报告”开始分析。' : '招聘信息已添加，请先上传并解析简历，再生成匹配报告。');
  } catch (error) {
    message(status, error instanceof TypeError ? '无法连接上传服务，请检查后端是否启动。' : error.message, true);
  } finally { button.disabled = false; }
});
try {
  const [options, rules] = await Promise.all([api('/jobs/options'), api('/matching/rubric')]);
  rubric = rules;
  [['#job-role', options.roles], ['#job-city', options.cities]].forEach(([selector, items]) => {
    items.forEach(item => {
      const option = el('option', item.label);
      option.value = item.id;
      document.querySelector(selector).append(option);
    });
  });
} catch (error) { message(collectionStatus, `无法加载职位选项：${error.message}`, true); }
