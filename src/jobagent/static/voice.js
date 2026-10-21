const start = document.querySelector('#start-recording');
const stop = document.querySelector('#stop-recording');
const status = document.querySelector('#voice-status');
const preview = document.querySelector('#voice-preview');
const modeInputs = [...document.querySelectorAll('[name="answer-mode"]')];
let recorder;
let stream;
let previewUrl;

// Encode the browser's decoded mono samples as PCM WAV for direct model input.
export function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset, text) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  write(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); write(8, 'WAVE');
  write(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); write(36, 'data'); view.setUint32(40, samples.length * 2, true);
  samples.forEach((value, i) => {
    const sample = Math.max(-1, Math.min(1, value));
    view.setInt16(44 + i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
  });
  return new Blob([buffer], {type:'audio/wav'});
}
function message(text, error = false) {
  status.textContent = text;
  status.className = error ? 'source-state error' : 'job-meta';
}
function changed() { window.dispatchEvent(new Event('voice-state')); }
export const voice = {
  audio: null,
  stage: 'idle',
  get busy() { return this.stage !== 'idle'; },
  get mode() { return modeInputs.find(input => input.checked).value; },
  sync(pending) {
    document.querySelector('#voice-answer-panel').hidden = this.mode !== 'voice';
    document.querySelector('#text-answer-panel').hidden = this.mode !== 'text';
    document.querySelector('#interview-answer').required = this.mode === 'text';
    document.querySelector('#submit-interview-answer').textContent = this.mode === 'voice' ? '提交语音回答 ↗' : '提交回答 ↗';
    start.disabled = pending || this.busy;
    stop.disabled = pending || this.stage !== 'recording';
    start.textContent = this.audio ? '重新录音' : '开始录音';
  },
  clear() {
    this.audio = null;
    preview.pause(); preview.removeAttribute('src'); preview.hidden = true;
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    message('点击开始录音后，请允许浏览器使用麦克风。');
  },
};
modeInputs.forEach(input => input.addEventListener('change', () => { preview.pause(); changed(); }));
start.addEventListener('click', async () => {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    message('当前浏览器不支持麦克风录音。请在支持录音的浏览器中通过 HTTPS 或 localhost 打开工作台。', true);
    return;
  }
  voice.stage = 'requesting'; changed();
  message('正在请求麦克风权限…');
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1}});
    recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      voice.stage = 'encoding'; changed();
      message('正在整理录音…');
      const context = new AudioContext({sampleRate:16000});
      try {
        const decoded = await context.decodeAudioData(await new Blob(chunks).arrayBuffer());
        voice.audio = encodeWav(decoded.getChannelData(0), decoded.sampleRate);
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(voice.audio);
        preview.src = previewUrl; preview.hidden = false;
        message(`录音完成（${Math.round(decoded.duration)} 秒），可试听后提交给模型。`);
      } catch (error) { message(`无法读取录音：${error.message}`, true); }
      finally { await context.close(); voice.stage = 'idle'; changed(); }
    };
    recorder.onerror = event => {
      message(`录音失败：${event.error?.message || '麦克风录音中断'}`, true);
      stream.getTracks().forEach(track => track.stop());
      voice.stage = 'idle'; changed();
    };
    voice.clear(); recorder.start(); voice.stage = 'recording';
    message('正在录音…请自然作答，完成后点击“停止录音”。');
  } catch (error) {
    stream?.getTracks().forEach(track => track.stop());
    voice.stage = 'idle';
    const reasons = {
      NotAllowedError:'麦克风权限未获允许，请在浏览器站点设置中允许访问麦克风。',
      NotFoundError:'未找到麦克风，请连接麦克风后重新录音。',
      NotReadableError:'无法读取麦克风，设备可能正被其他应用占用。',
    };
    message(reasons[error.name] || `无法开始录音：${error.message}`, true);
  }
  changed();
});
stop.addEventListener('click', () => {
  voice.stage = 'encoding'; changed(); message('正在停止录音…'); recorder.stop();
});
