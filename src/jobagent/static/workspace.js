import { startInterview, interviewOccupied } from './interview.js?v=modules-v2';
import './resume-editor.js';
import { mountJobSelectors } from './job-selectors.js';

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
const sourceNames = { liepin:'猎聘', zhilian:'智联招聘', nowcoder:'牛客', manual:'用户提供' };
const stateNames = { met:'已命中', partial:'部分命中', missing:'简历未体现' };
const reportBox = document.querySelector('#match-report');
const jobsBox = document.querySelector('#job-list');
const collectionStatus = document.querySelector('#collection-status');
let resume = null;
let jobs = [];
let matching = false;
let matchInterviewJob = null;
let rubric;
let ranked = [];
let visibleJobs = 20;
let rankingVersion = 0;
const rankingStatus = document.querySelector('#ranking-status');
const moreJobs = document.querySelector('#more-jobs');
function message(target, text, error = false) {
  target.replaceChildren(el('div', text, `source-state${error ? ' error' : ''}`));
}
function renderJobs() {
  jobsBox.replaceChildren();
  const ordered = ranked.length ? ranked.map(item => item.job) : jobs;
  ordered.slice(0, visibleJobs).forEach(job => {
    const card = el('article', undefined, 'job-card');
    card.append(el('h3', job.title), el('div', [job.company, job.city].filter(Boolean).join(' · ') || sourceNames[job.source], 'job-meta'),
      el('div', job.salary || '薪资未公开', 'salary'));
    card.append(el('p', [job.education, job.experience].filter(Boolean).join(' · '), 'job-meta'));
    if (job.recruitment_type) card.append(el('span', job.recruitment_type, 'state-tag'));
    if (job.published_at) card.append(el('p', `原站时间：${job.published_at}`, 'job-meta'));
    const ranking = ranked.find(item => item.job.source === job.source && item.job.url === job.url && item.job.raw_text === job.raw_text);
    if (ranking) {
      const count = ranking.matched_skills.length + ranking.missing_skills.length;
      card.append(el('div', ranking.score === null ? '未识别到技术技能关键词' : `技能关键词覆盖 ${ranking.score.toFixed(0)}% · ${ranking.matched_skills.length}/${count}`, 'skill-rank'));
      if (ranking.matched_skills.length) card.append(el('p', `已命中：${ranking.matched_skills.join('、')}`, 'matched-keywords'));
      if (ranking.missing_skills.length) card.append(el('p', `简历技能列表未体现：${ranking.missing_skills.join('、')}`, 'job-meta'));
    }
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
  moreJobs.hidden = ordered.length <= visibleJobs;
  moreJobs.textContent = `显示更多岗位（已显示 ${Math.min(visibleJobs, ordered.length)} / ${ordered.length}）`;
}
moreJobs.addEventListener('click', () => { visibleJobs += 20; renderJobs(); });
async function rankJobs() {
  const version = ++rankingVersion;
  ranked = []; visibleJobs = 20; renderJobs();
  if (!jobs.length) { rankingStatus.textContent = ''; return; }
  if (!resume) { rankingStatus.textContent = `共 ${jobs.length} 个岗位；解析简历后可按技能排序。`; return; }
  rankingStatus.textContent = '正在按简历技能为全部岗位排序…';
  try {
    const result = await api('/jobs/rank', {resume, jobs});
    if (version !== rankingVersion) return;
    ranked = result;
    rankingStatus.textContent = `共 ${jobs.length} 个岗位，已按技能关键词覆盖率排序。支持技能别名；此排序不等于详细匹配评分，也不代表硬性条件均满足。`;
    renderJobs();
  } catch (error) {
    if (version === rankingVersion) rankingStatus.textContent = `技能排序失败：${error.message}`;
  }
}
function syncReportInterviewButtons() {
  document.querySelectorAll('#match-panel .report-interview-button').forEach(button => {
    button.disabled = !resume || !matchInterviewJob || interviewOccupied;
    button.title = !resume ? '请先解析简历' : !matchInterviewJob ? '请先选择岗位生成匹配报告'
      : interviewOccupied ? '已有面试正在进行，请先完成或结束当前面试' : `针对 ${matchInterviewJob.title} 开始模拟面试`;
  });
}
document.querySelectorAll('#match-panel .report-interview-button').forEach(button => {
  button.addEventListener('click', () => startInterview({resume, job:matchInterviewJob}));
});
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
  matchInterviewJob = job;
  syncReportInterviewButtons();
  renderJobs();
  message(reportBox, `正在对照 ${job.title} 的要求，生成匹配报告…`);
  window.dispatchEvent(new CustomEvent('module-navigate', {detail:'match-module'}));
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
window.addEventListener('resume-parsed', event => {
  resume = event.detail;
  rankJobs();
  syncReportInterviewButtons();
});
window.addEventListener('interview-changed', () => {
  renderJobs();
  syncReportInterviewButtons();
});
window.addEventListener('resume-cleared', () => {
  resume = null;
  matchInterviewJob = null;
  syncReportInterviewButtons();
  rankJobs();
  message(reportBox, '请先完成简历解析，再选择岗位生成匹配报告。');
});
document.querySelector('#job-source').addEventListener('change', event => {
  document.querySelector('#recruitment-type-field').hidden = event.target.value !== 'nowcoder';
});
document.querySelector('#job-search').addEventListener('submit', async event => {
  event.preventDefault();
  const controls = [...event.target.querySelectorAll('select,button,input')];
  const request = { role:document.querySelector('#job-role').value,
    city:document.querySelector('#job-city').value, source:document.querySelector('#job-source').value,
    limit:Number(document.querySelector('#job-limit').value),
    recruitment_type:document.querySelector('#recruitment-type').value };
  controls.forEach(control => { control.disabled = true; });
  jobs = jobs.filter(job => job.source === 'manual');
  rankJobs();
  message(collectionStatus, '正在分页读取公开岗位和完整详情，数量较多时请稍候…');
  try {
    const data = await api('/jobs/collect', request);
    collectionStatus.replaceChildren();
    data.sources.forEach(source => {
      const state = el('div', undefined, `source-state${source.status === 'success' ? '' : ' error'}`);
      state.append(el('p', `${sourceNames[source.source]}：${source.message}`));
      const actions = el('div', undefined, 'job-actions');
      Object.entries(source.search_urls).forEach(([name,url]) => {
        const link = el('a', `打开${name}查看 / 登录 ↗`);
        link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
        actions.append(link);
      });
      const paste = el('button', '粘贴岗位 JD 进行分析', 'action secondary');
      paste.type = 'button';
      paste.addEventListener('click', () => {
        document.querySelector('#manual-tab').click();
        document.querySelector('[name="job-format"][value="text"]').click();
        document.querySelector('#job-upload-text').focus();
      });
      actions.append(paste); state.append(actions);
      if (source.status === 'blocked') state.append(el('p', '请在原站自行登录或完成验证。浏览器登录不会自动恢复服务器采集；可复制岗位正文，回到此处粘贴分析。', 'job-meta'));
      collectionStatus.append(state);
    });
    jobs = [...jobs, ...data.jobs];
    await rankJobs();
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
    await rankJobs();
    message(status, resume ? '招聘信息已添加，点击下方“生成匹配报告”开始分析。' : '招聘信息已添加，请先上传并解析简历，再生成匹配报告。');
  } catch (error) {
    message(status, error instanceof TypeError ? '无法连接上传服务，请检查后端是否启动。' : error.message, true);
  } finally { button.disabled = false; }
});
try {
  const [options, rules] = await Promise.all([api('/jobs/options'), api('/matching/rubric')]);
  rubric = rules;
  mountJobSelectors(options);
} catch (error) { message(collectionStatus, `无法加载职位选项：${error.message}`, true); }
