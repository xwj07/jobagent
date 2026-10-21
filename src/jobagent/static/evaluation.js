const el = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const read = async url => {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail);
  return data;
};
const status = document.querySelector('#annotation-status');
const selector = document.querySelector('#case-selector');
let rules;
function showStatus(message, error = false) {
  status.textContent = message;
  status.className = `status${error ? ' error' : ''}`;
  status.hidden = false;
}
function metric(label, value) {
  const card = el('div', undefined, 'metric-card');
  card.append(el('span', label), el('strong', value));
  return card;
}
async function refreshMetrics() {
  const data = await read('/evaluation/summary');
  document.querySelector('#progress').replaceChildren(
    metric('人工标注进度', `${data.labelled_pairs} / ${data.target}`),
    metric('已收集配对', data.total_pairs),
    metric('待标注', data.total_pairs - data.labelled_pairs),
    metric('阶段', data.target_reached ? '已达样本目标' : '标注准备中'));
  const box = document.querySelector('#metrics');
  box.replaceChildren();
  if (!data.groups.length) box.append(el('p', '尚无人工标签，暂不生成指标。完成标注后自动计算。', 'muted'));
  data.groups.forEach(group => {
    box.append(el('h3', `${group.model} · ${group.rubric_version} · ${group.pairs} 组${group.pairs < 50 ? '（试算，尚不足50组）' : ''}`));
    const grid = el('div', undefined, 'metric-grid');
    const percent = value => value === null ? '不可计算' : `${(value * 100).toFixed(1)}%`;
    grid.append(metric('Gap Precision', percent(group.precision)), metric('Gap Recall', percent(group.recall)),
      metric('Gap F1', percent(group.f1)), metric('Spearman ρ', group.spearman === null ? '不可计算' : group.spearman.toFixed(3)));
    box.append(grid, el('p', `正确识别 ${group.tp} 项 · 误报 ${group.fp} 项 · 漏报 ${group.fn} 项。按配对累计技能项，不同模型与评分版本分开统计。`, 'muted'));
    if (group.spearman === null) box.append(el('p', 'Spearman 至少需要两组配对，且双方评分都不能全部相同。', 'muted'));
  });
}
async function refreshCases(selectedId) {
  const cases = await read('/evaluation/cases');
  selector.replaceChildren();
  const placeholder = el('option', cases.length ? '请选择一组配对' : '暂无配对，请先生成岗位匹配报告');
  placeholder.value = '';
  selector.append(placeholder);
  cases.forEach(item => {
    const option = el('option', `${item.labelled ? '已标注' : '待标注'} · ${item.name || '未注明姓名'} × ${item.title}${item.company ? ` · ${item.company}` : ''}`);
    option.value = item.case_id;
    selector.append(option);
  });
  if (selectedId) selector.value = selectedId;
}
function resumeText(resume) {
  const lines = [`姓名：${resume.name || '未提供'}`, `求职意向：${resume.target_role || '未提供'}`, '\n教育经历'];
  resume.education.forEach(item => lines.push([item.school, item.major, item.degree, item.start_date, item.end_date].filter(Boolean).join(' · ')));
  lines.push('\n工作经历');
  resume.work_experience.forEach(item => lines.push([item.company, item.title, item.start_date, item.end_date].filter(Boolean).join(' · '), ...item.responsibilities));
  lines.push('\n项目经历');
  resume.projects.forEach(item => lines.push([item.name, item.role].filter(Boolean).join(' · '), item.technologies.join('、'), ...item.responsibilities, ...item.achievements));
  lines.push('\n技能');
  resume.skills.forEach(item => lines.push(`${item.name}：${item.evidence}`));
  return lines.join('\n');
}
selector.addEventListener('change', async () => {
  const content = document.querySelector('#case-content');
  content.hidden = true;
  status.hidden = true;
  if (!selector.value) return;
  try {
    const data = await read(`/evaluation/cases/${selector.value}`);
    document.querySelector('#human-resume').textContent = resumeText(data.resume);
    document.querySelector('#human-job').textContent = data.job.raw_text;
    const annotation = data.annotation;
    document.querySelector('#annotator').value = annotation?.annotator || '';
    document.querySelector('#skill-gaps').value = annotation?.skill_gaps.join('\n') || '';
    document.querySelector('#annotation-notes').value = annotation?.notes || '';
    document.querySelector('#human-total').textContent = '';
    const dimensions = document.querySelector('#human-dimensions');
    dimensions.replaceChildren();
    rules.dimensions.forEach(item => {
      const row = el('div', undefined, 'dimension-input');
      const label = el('label');
      const checkbox = el('input');
      checkbox.type = 'checkbox';
      checkbox.dataset.category = item.category;
      const saved = annotation?.dimensions.find(dimension => dimension.category === item.category);
      checkbox.checked = annotation ? Boolean(saved) : true;
      const score = el('input');
      score.type = 'number'; score.min = '0'; score.max = '100'; score.step = '0.01';
      score.required = checkbox.checked; score.disabled = !checkbox.checked;
      score.value = saved ? saved.score : '';
      score.setAttribute('aria-label', `${item.label}满足率`);
      checkbox.addEventListener('change', () => { score.disabled = !checkbox.checked; score.required = checkbox.checked; });
      label.append(checkbox, document.createTextNode(`${item.label}（${item.weight}%）`));
      row.append(label, score); dimensions.append(row);
    });
    content.hidden = false;
  } catch (error) { showStatus(error.message, true); }
});
document.querySelector('#annotation-form').addEventListener('submit', async event => {
  event.preventDefault();
  const dimensions = [...document.querySelectorAll('.dimension-input')].filter(row => row.querySelector('[type=checkbox]').checked)
    .map(row => ({ category:row.querySelector('[type=checkbox]').dataset.category, score:Number(row.querySelector('[type=number]').value) }));
  if (!dimensions.length) { showStatus('请至少选择一个 JD 实际包含要求的维度。', true); return; }
  const button = document.querySelector('#save-annotation');
  button.disabled = true;
  try {
    const response = await fetch(`/evaluation/cases/${selector.value}/annotation`, {
      method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
        annotator:document.querySelector('#annotator').value.trim(), dimensions,
        skill_gaps:document.querySelector('#skill-gaps').value.split('\n').map(value => value.trim()).filter(Boolean),
        notes:document.querySelector('#annotation-notes').value,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('；') : data.detail);
    showStatus('人工标注已保存。');
    document.querySelector('#human-total').textContent = `人工综合评分：${data.human_score.toFixed(1)} / 100`;
    await Promise.all([refreshMetrics(), refreshCases(selector.value)]);
  } catch (error) { showStatus(error.message, true); }
  finally { button.disabled = false; }
});
try {
  rules = await read('/matching/rubric');
  document.querySelector('#rubric-rule').textContent = rules.rule;
  await Promise.all([refreshMetrics(), refreshCases()]);
} catch (error) { showStatus(`无法加载评估资料：${error.message}`, true); }
