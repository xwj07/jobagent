import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const source=await readFile(new URL('../src/jobagent/static/job-selectors.js',import.meta.url),'utf8');
const {filterOptions}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const catalog=JSON.parse(await readFile(new URL('../src/jobagent/data/job_catalog.json',import.meta.url),'utf8'));
assert.equal(filterOptions(catalog.roles,'').length,catalog.roles.length);
assert(filterOptions(catalog.roles,'会计').some(item=>item.label==='会计'));
assert(filterOptions(catalog.roles,'人力资源').some(item=>item.label==='招聘专员/助理'));
assert(filterOptions(catalog.roles,'PYTHON').some(item=>item.id==='python'));
assert.deepEqual(filterOptions(catalog.cities,'nanjing').map(item=>item.label),['南京']);
assert(filterOptions(catalog.cities,'苏州').some(item=>item.label==='苏州'));
assert.equal(filterOptions(catalog.cities,'不存在的城市12345').length,0);
console.log('Catalog search passed: role, category, city name, pinyin, empty results.');
