import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, {
    events: {}, value:'', checked:false, hidden:false,
    addEventListener(name, handler) { this.events[name] = handler; },
    pause() {}, removeAttribute() {},
  });
  return elements.get(selector);
}
const modes = [{...element('voice'), value:'voice', checked:true},
  {...element('text'), value:'text', checked:false}];
globalThis.document = {querySelector:element, querySelectorAll:() => modes};
globalThis.window = {MediaRecorder:true, dispatchEvent() {}};
let tracksStopped = 0;
let stopTask;
Object.defineProperty(globalThis, 'navigator', {value:{mediaDevices:{
  async getUserMedia() { return {getTracks:() => [{stop() { tracksStopped++; }}]}; },
}}, configurable:true});
globalThis.MediaRecorder = class {
  start() {}
  stop() {
    this.ondataavailable({data:new Blob(['encoded browser audio'])});
    stopTask = this.onstop();
  }
};
globalThis.AudioContext = class {
  async decodeAudioData() {
    return {getChannelData:() => new Float32Array([-1, 0, 1]), sampleRate:16000, duration:1};
  }
  async close() {}
};
const source = await readFile(new URL('../src/jobagent/static/voice.js', import.meta.url), 'utf8');
const {voice, encodeWav} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

const wav = Buffer.from(await encodeWav(new Float32Array([-1, 0, 1]), 16000).arrayBuffer());
assert.equal(wav.toString('ascii', 0, 4), 'RIFF');
assert.equal(wav.toString('ascii', 8, 12), 'WAVE');
assert.equal(wav.readUInt32LE(24), 16000);
assert.equal(wav.readUInt16LE(22), 1);
assert.equal(wav.readUInt32LE(40), 6);
assert.deepEqual([wav.readInt16LE(44), wav.readInt16LE(46), wav.readInt16LE(48)], [-32768, 0, 32767]);

voice.sync(false);
assert.equal(element('#text-answer-panel').hidden, true);
assert.equal(element('#submit-interview-answer').textContent, '提交语音回答 ↗');
await element('#start-recording').events.click();
assert.equal(voice.stage, 'recording');
element('#stop-recording').events.click();
await stopTask;
assert.equal(voice.stage, 'idle');
assert.equal(voice.audio.type, 'audio/wav');
assert.equal(tracksStopped, 1);
assert.equal(element('#voice-preview').hidden, false);
const recorded = voice.audio;
modes[0].checked = false; modes[1].checked = true; voice.sync(false);
assert.equal(element('#interview-answer').required, true);
assert.equal(element('#voice-answer-panel').hidden, true);
assert.equal(voice.audio, recorded);
voice.clear();
assert.equal(voice.audio, null);

navigator.mediaDevices.getUserMedia = async () => {
  throw Object.assign(new Error('denied'), {name:'NotAllowedError'});
};
await element('#start-recording').events.click();
assert.equal(voice.stage, 'idle');
assert.match(element('#voice-status').textContent, /麦克风权限未获允许/);
console.log('Voice checks passed: WAV, recording lifecycle, mode switch, permission error.');
