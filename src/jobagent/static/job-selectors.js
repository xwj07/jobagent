export function filterOptions(items, query) {
  const needle = query.trim().toLowerCase();
  return items.filter(item => [item.label, item.group, item.keyword, item.pinyin]
    .filter(Boolean).join(' ').toLowerCase().includes(needle));
}

export function mountJobSelectors(options) {
  for (const [kind, items, defaultValue, placeholder] of [
    ['role', options.roles, 'python', '请选择目标职位'],
    ['city', options.cities, 'hangzhou', '请选择工作城市'],
  ]) {
    const select = document.querySelector(`#job-${kind}`);
    const search = document.querySelector(`#job-${kind}-search`);
    const count = document.querySelector(`#job-${kind}-count`);
    function render(selected) {
      const matches = filterOptions(items, search.value);
      select.replaceChildren();
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = matches.length ? placeholder : '没有匹配选项，请更换搜索词';
      select.append(empty);
      const groups = new Map();
      const ordered = kind === 'city' ? [...matches.filter(item => item.hot), ...matches.filter(item => !item.hot)] : matches;
      for (const item of ordered) {
        const groupName = kind === 'city' && item.hot ? '热门城市' : item.group;
        if (!groups.has(groupName)) {
          const group = document.createElement('optgroup');
          group.label = groupName;
          groups.set(groupName, group);
          select.append(group);
        }
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = item.label;
        groups.get(groupName).append(option);
      }
      select.value = matches.some(item => item.id === selected) ? selected : '';
      count.textContent = search.value.trim()
        ? `找到 ${matches.length} / ${items.length} 个选项，请从下拉列表选择`
        : `共 ${items.length} 个选项 · ${kind === 'role' ? '按职能分类' : '热门城市 / 拼音字母'}`;
    }
    search.addEventListener('input', () => render(select.value));
    render(defaultValue);
  }
}
