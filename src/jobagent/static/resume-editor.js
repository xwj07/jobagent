const sections = [
  ['education', '教育经历', [
    ['school', '学校'], ['major', '专业'], ['degree', '学历'],
    ['start_date', '开始时间'], ['end_date', '结束时间'],
  ]],
  ['work_experience', '工作经历', [
    ['company', '公司'], ['title', '职位'], ['start_date', '开始时间'],
    ['end_date', '结束时间'], ['responsibilities', '工作职责（每行一项）', 'list'],
  ]],
  ['projects', '项目经历', [
    ['name', '项目名称'], ['role', '项目角色'], ['technologies', '使用技术（每行一项）', 'list'],
    ['responsibilities', '项目职责（每行一项）', 'list'],
    ['achievements', '项目成果（每行一项）', 'list'],
  ]],
  ['skills', '专业技能', [
    ['name', '技能名称', 'required'], ['evidence', '具体经历或掌握依据', 'text'],
  ]],
];
const form = document.querySelector('#resume-editor');
const fields = document.querySelector('#resume-editor-fields');
const edit = document.querySelector('#edit-resume');
const preview = document.querySelector('#result');
const status = document.querySelector('#resume-edit-status');
let saved;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function field(key, title, value, kind) {
  const label = node('label', title);
  const control = document.createElement(kind === 'list' || kind === 'text' ? 'textarea' : 'input');
  control.dataset.field = key;
  control.dataset.kind = kind || 'optional';
  control.value = Array.isArray(value) ? value.join('\n') : value || '';
  if (control.tagName === 'TEXTAREA') control.rows = 3;
  control.required = kind === 'required';
  label.append(control);
  return label;
}
function addEntry(container, definitions, value = {}) {
  const entry = node('fieldset', undefined, 'resume-edit-entry');
  entry.append(node('legend', '条目'));
  definitions.forEach(([key, title, kind]) => entry.append(field(key, title, value[key], kind)));
  const remove = node('button', '删除此条', 'remove-entry');
  remove.type = 'button';
  remove.addEventListener('click', () => entry.remove());
  entry.append(remove);
  container.append(entry);
}
function renderEditor() {
  fields.replaceChildren();
  const basics = node('section', undefined, 'resume-edit-group');
  basics.append(node('h3', '基本信息'), field('name', '姓名', saved.name),
    field('target_role', '求职意向', saved.target_role));
  fields.append(basics);
  sections.forEach(([key, title, definitions]) => {
    const section = node('section', undefined, 'resume-edit-group');
    section.append(node('h3', title));
    const entries = node('div', undefined, 'resume-edit-entries');
    entries.dataset.section = key;
    saved[key].forEach(value => addEntry(entries, definitions, value));
    const add = node('button', `添加${title}`, 'action secondary');
    add.type = 'button';
    add.addEventListener('click', () => {
      addEntry(entries, definitions);
      entries.lastElementChild.querySelector('input,textarea').focus();
    });
    section.append(entries, add);
    fields.append(section);
  });
}
function closeEditor() {
  form.hidden = true; preview.hidden = false; edit.hidden = false;
}
function readEntry(container) {
  return Object.fromEntries([...container.querySelectorAll('[data-field]')].map(control => {
    const text = control.value.trim();
    return [control.dataset.field, control.dataset.kind === 'list'
      ? text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
      : control.dataset.kind === 'optional' ? text || null : text];
  }));
}
window.addEventListener('resume-parsed', event => {
  saved = structuredClone(event.detail);
  edit.hidden = false; form.hidden = true; status.hidden = true;
});
window.addEventListener('resume-cleared', () => {
  saved = null; edit.hidden = true; form.hidden = true; status.hidden = true;
});
edit.addEventListener('click', () => {
  renderEditor(); form.hidden = false; preview.hidden = true; edit.hidden = true; status.hidden = true;
  fields.querySelector('input').focus();
});
document.querySelector('#cancel-resume-edit').addEventListener('click', closeEditor);
form.addEventListener('submit', event => {
  event.preventDefault();
  const updated = readEntry(fields.querySelector('.resume-edit-group'));
  fields.querySelectorAll('[data-section]').forEach(container => {
    updated[container.dataset.section] = [...container.children].map(readEntry);
  });
  closeEditor();
  // Matching and new interviews receive the edited snapshot through the parsing event.
  window.dispatchEvent(new Event('resume-cleared'));
  window.dispatchEvent(new CustomEvent('resume-edited', {detail:updated}));
  window.dispatchEvent(new CustomEvent('resume-parsed', {detail:updated}));
  status.textContent = '修改已保存，新的匹配分析和模拟面试将使用这份简历。';
  status.hidden = false;
});
