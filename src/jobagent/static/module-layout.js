const main = document.querySelector('main');
const workspace = document.querySelector('.workspace');
const jobs = document.querySelector('.workflow');
const match = document.querySelector('#match-panel');
const interview = document.querySelector('#interview-panel');
const modules = [
  {id:'resume-module', label:'整理简历', note:'看见你的积累，迈出下一步', content:workspace},
  {id:'jobs-module', label:'发现岗位', note:'找到值得尝试的机会', content:jobs},
  {id:'match-module', label:'匹配分析', note:'看清优势，也找到成长方向', content:match},
  {id:'interview-module', label:'模拟面试', note:'每一次练习，都更从容一点', content:interview},
];
let current = 0;
const go = (index, fromScroll = false) => {
  const backwards = index < current;
  current = index;
  modules.forEach((module, position) => {
    const active = position === current;
    module.stage.hidden = !active;
    module.button.classList.toggle('active', active);
    if (active) module.button.setAttribute('aria-current', 'step');
    else module.button.removeAttribute('aria-current');
  });
  main.scrollTop = fromScroll && backwards ? main.scrollHeight : 0;
  modules[index].stage.querySelector('h1').focus({preventScroll:true});
};
const nav = document.createElement('nav');
nav.className = 'module-minimap';
nav.setAttribute('aria-label', '工作区模块导航');
const caption = document.createElement('p');
caption.className = 'minimap-caption';
caption.textContent = '你的求职工作台';
nav.append(caption);
document.body.classList.add('module-workspace');
document.body.insertBefore(nav, main);
const hero = [main.querySelector('.eyebrow'), main.querySelector('h1'), main.querySelector('.intro')];
hero.forEach(node => node.remove());
main.querySelector('footer').remove();
main.setAttribute('aria-label', '求职工作区');

modules.forEach((module, index) => {
  const stage = document.createElement('section');
  module.stage = stage;
  stage.id = module.id;
  stage.className = 'module-stage';
  stage.setAttribute('aria-labelledby', `${module.id}-title`);
  const header = document.createElement('div');
  header.className = 'module-heading';
  const kicker = document.createElement('span');
  kicker.className = 'module-kicker';
  kicker.textContent = `YOUR NEXT STEP · 0${index + 1} / 04`;
  const title = document.createElement('h1');
  title.id = `${module.id}-title`;
  title.tabIndex = -1;
  title.textContent = module.label;
  const note = document.createElement('p');
  note.textContent = module.note;
  header.append(kicker, title, note);
  const body = document.createElement('div');
  body.className = 'module-body';
  body.setAttribute('aria-label', `${module.label}内容`);
  body.append(module.content);
  stage.append(header, body);
  const edge = (target, direction) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `module-edge ${direction}`;
    button.textContent = direction === 'previous' ? `↑ 上一模块 · ${modules[target].label}` : `下一模块 · ${modules[target].label} ↓`;
    button.addEventListener('click', () => go(target));
    return button;
  };
  if (index > 0) stage.prepend(edge(index - 1, 'previous'));
  if (index < modules.length - 1) stage.append(edge(index + 1, 'next'));
  main.append(stage);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'minimap-item';
  button.setAttribute('aria-controls', module.id);
  button.setAttribute('aria-label', `0${index + 1} ${module.label}`);
  const preview = document.createElement('span');
  preview.className = `minimap-preview preview-${index}`;
  preview.setAttribute('aria-hidden', 'true');
  for (let line = 0; line < 4; line++) preview.append(document.createElement('i'));
  const label = document.createElement('span');
  label.className = 'minimap-label';
  label.textContent = module.label;
  const number = document.createElement('span');
  number.className = 'minimap-number';
  number.textContent = `0${index + 1}`;
  button.append(preview, number, label);
  button.addEventListener('click', () => go(index));
  module.button = button;
  nav.append(button);
});
const boundaryDirection = direction => {
  if (direction > 0 && main.scrollHeight - main.clientHeight - main.scrollTop <= 2 && current < modules.length - 1) return 1;
  if (direction < 0 && main.scrollTop <= 2 && current > 0) return -1;
  return 0;
};
const isEditing = target => target.closest('input,textarea,select,audio');
let wheelTimer;
let wheelStartDirection = 0;
let wheelSwitched = false;
main.addEventListener('wheel', event => {
  if (event.ctrlKey || isEditing(event.target) || !event.deltaY) return;
  if (!wheelTimer) wheelStartDirection = boundaryDirection(event.deltaY);
  clearTimeout(wheelTimer);
  wheelTimer = setTimeout(() => {
    wheelTimer = undefined;
    wheelSwitched = false;
  }, 180);
  if (wheelSwitched) {
    event.preventDefault();
    return;
  }
  const direction = boundaryDirection(event.deltaY);
  if (direction && direction === wheelStartDirection) {
    event.preventDefault();
    wheelSwitched = true;
    go(current + direction, true);
  }
}, {passive:false});
main.addEventListener('keydown', event => {
  if (isEditing(event.target)) return;
  const direction = ['PageDown','ArrowDown'].includes(event.key) ? 1 : ['PageUp','ArrowUp'].includes(event.key) ? -1 : 0;
  const step = boundaryDirection(direction);
  if (step) {
    event.preventDefault();
    go(current + step, true);
  }
});
let touchStartY;
let touchTop;
let touchBottom;
main.addEventListener('touchstart', event => {
  touchStartY = event.touches[0].clientY;
  touchTop = boundaryDirection(-1);
  touchBottom = boundaryDirection(1);
}, {passive:true});
main.addEventListener('touchend', event => {
  if (isEditing(event.target)) return;
  const distance = touchStartY - event.changedTouches[0].clientY;
  if (distance > 60 && touchBottom) go(current + 1, true);
  else if (distance < -60 && touchTop) go(current - 1, true);
}, {passive:true});
main.tabIndex = 0;
go(0);
window.addEventListener('module-navigate', event => go(modules.findIndex(module => module.id === event.detail)));
