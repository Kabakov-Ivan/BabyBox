const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const toast = $('#toast');
let toastTimer;
function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function updateClock() {
  const now = new Date();
  $('#clock').textContent = now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  $('#date').textContent = now.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
  $('#streamClock').textContent = now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}
updateClock();
setInterval(updateClock, 1000);

const emptyReadings = {
  temp_c: '—', humidity_pct: '—', co2_ppm: '—', noise_db: '—', motion: '—', respiration_bpm: '—'
};

function setReading(key, value, live = false) {
  const target = $(`[data-reading="${key}"]`);
  if (!target || value === undefined || value === null || value === '') return;
  const display = key === 'motion'
    ? (value === true || value === 1 || value === 'true' || value === 'yes' || value === 'Да' ? 'Да' : 'Нет')
    : String(value);
  target.textContent = display;
  const reportTarget = $(`[data-report="${key}"]`);
  if (reportTarget) reportTarget.textContent = display;
  const state = $(`[data-state="${key}"]`);
  if (state) {
    state.textContent = live ? 'От устройства' : 'Нет данных';
    state.classList.toggle('live-state', live);
  }
}

function restoreEmptyReadings() {
  Object.entries(emptyReadings).forEach(([key, value]) => setReading(key, value, false));
}

function addEvent(title, detail, tone = '') {
  $('#eventList .empty-events')?.remove();
  const row = document.createElement('div');
  row.className = 'event-row';
  const time = document.createElement('time');
  time.className = 'event-time';
  time.textContent = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const mark = document.createElement('span');
  mark.className = `event-mark ${tone}`.trim();
  mark.textContent = tone === 'orange' ? '♨' : tone === 'cyan' ? '≈' : '⌖';
  const copy = document.createElement('div');
  copy.className = 'event-copy';
  const heading = document.createElement('b');
  heading.textContent = title;
  const caption = document.createElement('small');
  caption.textContent = detail;
  copy.append(heading, caption);
  row.append(time, mark, copy);
  $('#eventList').prepend(row);
  const reportRow = row.cloneNode(true);
  $('#reportEventList')?.querySelector('.empty-events')?.remove();
  $('#reportEventList')?.prepend(reportRow);
  $('#dailyEventCount').textContent = $('#eventList').querySelectorAll('.event-row').length;
}

$('#clearEventsBtn').addEventListener('click', () => {
  $('#eventList').replaceChildren();
  $('#reportEventList')?.replaceChildren();
  $('#dailyEventCount').textContent = '0';
  const empty = document.createElement('div');
  empty.className = 'empty-events';
  empty.textContent = 'Новых событий пока нет';
  $('#eventList').append(empty);
  $('#reportEventList')?.append(empty.cloneNode(true));
});

// Переключение экранов приложения.
const navLinks = $$('.nav-item');
const dashboardHeading = $('.page-heading', $('#dashboard'));
const homePanels = [dashboardHeading, $('.top-grid'), $('.bottom-grid')];
const recordingsPanel = $('.recordings-panel');
const reportsPanel = $('#reports');
function setView(view) {
  homePanels.forEach(panel => { if (panel) panel.hidden = view !== 'home'; });
  recordingsPanel.hidden = view !== 'recordings';
  reportsPanel.hidden = view !== 'reports';
  navLinks.forEach(link => link.classList.toggle('active', link.dataset.view === view));
  document.body.dataset.view = view;
  history.replaceState(null, '', `#${view === 'home' ? 'dashboard' : view}`);
}
navLinks.forEach(link => link.addEventListener('click', event => {
  event.preventDefault(); setView(link.dataset.view);
}));
setView(location.hash === '#reports' ? 'reports' : location.hash === '#recordings' ? 'recordings' : 'home');

// Тема сохраняется в этом браузере.
const savedTheme = localStorage.getItem('radio-nanny-theme');
if (savedTheme === 'light') document.body.dataset.theme = 'light';
$('#themeBtn').textContent = document.body.dataset.theme === 'light' ? '☀' : '☾';
$('#themeBtn').addEventListener('click', () => {
  const light = document.body.dataset.theme !== 'light';
  document.body.dataset.theme = light ? 'light' : 'dark';
  localStorage.setItem('radio-nanny-theme', light ? 'light' : 'dark');
  $('#themeBtn').textContent = light ? '☀' : '☾';
});

// Подключение изображения или видео по адресу камеры.
const cameraStage = $('#cameraStage');
const streamPlaceholder = $('#streamPlaceholder');
const mjpegStream = $('#mjpegStream');
const videoStream = $('#videoStream');
const streamError = $('#streamError');
let cameraUrl = '';
let streamType = 'mjpeg';
let streamConnected = false;

function setCameraStatus(state, live = false) {
  $('#cameraState').textContent = state;
  $('#overlayCameraState').textContent = live ? 'Прямой эфир' : state;
  $('#cameraDot').classList.toggle('is-live', live);
  $('#cameraDot').classList.toggle('live-indicator', true);
  $('#qualityTag').textContent = live ? (streamType === 'mjpeg' ? 'MJPEG' : 'ВИДЕО') : 'ОЖИДАНИЕ';
  $('#qualityTag').classList.toggle('is-live', live);
  $('#cameraDot').classList.toggle('is-live', live);
  $('#videoAudioBtn').disabled = !live || streamType !== 'video';
  $('#snapshotBtn').disabled = !live;
  $('#recordBtn').disabled = !live || streamType !== 'video' || !window.MediaRecorder;
  streamConnected = live;
}

function showCameraPlaceholder(message) {
  streamConnected = false;
  mjpegStream.hidden = true;
  videoStream.hidden = true;
  streamPlaceholder.hidden = false;
  streamError.hidden = true;
  $('#cameraNote').textContent = message || 'Для настоящей трансляции нужен адрес видеопотока с вашей камеры.';
  setCameraStatus('Источник не подключён', false);
}

function connectCamera(url, type, persist = true) {
  const cleanedUrl = url.trim();
  if (!cleanedUrl) {
    showCameraPlaceholder('Добавьте адрес видеопотока в настройках.');
    return;
  }
  try {
    const parsed = new URL(cleanedUrl);
    if (!['http:', 'https:', 'blob:'].includes(parsed.protocol)) throw new Error('Unsupported protocol');
  } catch {
    showToast('Проверь адрес камеры: нужен полный адрес, начинающийся с http:// или https://');
    return;
  }

  cameraUrl = cleanedUrl;
  streamType = type;
  if (persist) {
    localStorage.setItem('radio-nanny-camera-url', cameraUrl);
    localStorage.setItem('radio-nanny-stream-type', streamType);
  }
  $('#streamUrl').value = cameraUrl;
  $('#streamType').value = streamType;
  $('#quickStreamUrl').value = cameraUrl;
  $('#quickStreamType').value = streamType;
  streamPlaceholder.hidden = true;
  streamError.hidden = true;
  $('#cameraNote').textContent = 'Ожидаю первый кадр от камеры. Если он не появится, проверьте адрес и доступность устройства в сети.';
  setCameraStatus('Подключение…', false);

  if (type === 'video') {
    mjpegStream.hidden = true;
    videoStream.hidden = false;
    videoStream.muted = true;
    videoStream.src = cameraUrl;
    videoStream.load();
    videoStream.play().catch(() => {});
  } else {
    videoStream.pause();
    videoStream.removeAttribute('src');
    videoStream.load();
    mjpegStream.hidden = false;
    mjpegStream.src = cameraUrl;
  }
}

mjpegStream.addEventListener('load', () => {
  if (streamType !== 'mjpeg') return;
  streamPlaceholder.hidden = true;
  streamError.hidden = true;
  setCameraStatus('Прямой эфир', true);
  $('#cameraNote').textContent = 'Поток камеры отображается в браузере.';
});
mjpegStream.addEventListener('error', () => {
  if (streamType !== 'mjpeg') return;
  streamError.hidden = false;
  setCameraStatus('Не удалось подключиться', false);
});
videoStream.addEventListener('loadeddata', () => {
  if (streamType !== 'video') return;
  streamPlaceholder.hidden = true;
  streamError.hidden = true;
  setCameraStatus('Прямой эфир', true);
  $('#cameraNote').textContent = 'Поток камеры отображается в браузере.';
});
videoStream.addEventListener('error', () => {
  if (streamType !== 'video') return;
  streamError.hidden = false;
  setCameraStatus('Не удалось подключиться', false);
});

const connectDialog = $('#connectDialog');
function openCameraDialog() {
  $('#quickStreamUrl').value = $('#streamUrl').value || cameraUrl;
  $('#quickStreamType').value = $('#streamType').value || streamType;
  connectDialog.showModal();
}
$('#connectCameraBtn').addEventListener('click', openCameraDialog);
$('#cameraForm').addEventListener('submit', event => {
  event.preventDefault();
  connectCamera($('#streamUrl').value, $('#streamType').value);
});
$('#quickCameraForm').addEventListener('submit', event => {
  event.preventDefault();
  connectCamera($('#quickStreamUrl').value, $('#quickStreamType').value);
  connectDialog.close();
});

const savedCameraUrl = localStorage.getItem('radio-nanny-camera-url');
const savedStreamType = localStorage.getItem('radio-nanny-stream-type');
if (savedCameraUrl) {
  $('#streamUrl').value = savedCameraUrl;
  $('#streamType').value = savedStreamType || 'mjpeg';
  connectCamera(savedCameraUrl, savedStreamType || 'mjpeg', false);
} else {
  showCameraPlaceholder();
}

function toggleFullscreen() {
  const target = cameraStage;
  if (document.fullscreenElement) document.exitFullscreen?.();
  else target.requestFullscreen?.().catch(() => showToast('Полный экран недоступен в этом браузере.'));
}
$('#fullscreenBtn').addEventListener('click', toggleFullscreen);
$('#cameraFullscreenBtn').addEventListener('click', toggleFullscreen);

$('#videoAudioBtn').addEventListener('click', () => {
  if (streamType !== 'video' || !streamConnected) return;
  videoStream.muted = !videoStream.muted;
  $('#videoAudioBtn').textContent = videoStream.muted ? '♪' : '♫';
  $('#videoAudioBtn').setAttribute('aria-label', videoStream.muted ? 'Включить звук видео' : 'Выключить звук видео');
});

$('#nightVisionBtn').addEventListener('click', event => {
  const button = event.currentTarget;
  const enabled = button.getAttribute('aria-pressed') !== 'true';
  button.setAttribute('aria-pressed', String(enabled));
  cameraStage.classList.toggle('night-on', enabled);
  const nightTile = $('.control-tile[data-action="night_mode"]');
  nightTile.setAttribute('aria-pressed', String(enabled));
  nightTile.querySelector('.control-state').textContent = enabled ? 'Включён' : 'Выключен';
  showToast(enabled ? 'Ночной режим отображения включён' : 'Ночной режим отображения выключен');
});

$('#snapshotBtn').addEventListener('click', () => {
  try {
    const canvas = document.createElement('canvas');
    canvas.width = streamType === 'video' ? videoStream.videoWidth : mjpegStream.naturalWidth;
    canvas.height = streamType === 'video' ? videoStream.videoHeight : mjpegStream.naturalHeight;
    if (!canvas.width || !canvas.height) throw new Error('No frame');
    const context = canvas.getContext('2d');
    context.drawImage(streamType === 'video' ? videoStream : mjpegStream, 0, 0, canvas.width, canvas.height);
    const link = document.createElement('a');
    link.download = `radio-nanny-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
    addEvent('Снимок сохранён', 'Файл скачан в браузере', 'cyan');
  } catch {
    showToast('Камера не разрешает сохранить снимок. Проверьте поддержку CORS на потоке.');
  }
});

// Запись видео сохраняется локально в браузере, если источник — видео и браузер поддерживает MediaRecorder.
let recorder = null;
let recordedChunks = [];
let recordingStartedAt = 0;
$('#recordBtn').addEventListener('click', () => {
  if (recorder?.state === 'recording') {
    recorder.stop();
    return;
  }
  try {
    const capture = videoStream.captureStream?.() || videoStream.mozCaptureStream?.();
    if (!capture) throw new Error('Video capture is unavailable');
    const preferredType = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'].find(type => MediaRecorder.isTypeSupported(type));
    recorder = new MediaRecorder(capture, preferredType ? { mimeType: preferredType } : undefined);
    recordedChunks = [];
    recordingStartedAt = Date.now();
    recorder.addEventListener('dataavailable', event => { if (event.data.size) recordedChunks.push(event.data); });
    recorder.addEventListener('stop', saveRecording);
    recorder.start(1000);
    $('#recordBtn').textContent = '■ Остановить запись';
    addEvent('Началась запись видео', 'Файл сохранится на этом устройстве', 'orange');
  } catch {
    showToast('Этот видеопоток или браузер не поддерживает запись.');
  }
});

function saveRecording() {
  const blob = new Blob(recordedChunks, { type: recorder.mimeType || 'video/webm' });
  if (!blob.size) {
    showToast('Видеопоток не передал данные для записи.');
    $('#recordBtn').textContent = '● Начать запись';
    return;
  }
  const url = URL.createObjectURL(blob);
  const fileName = `radio-nanny-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`;
  const item = document.createElement('article');
  item.className = 'recording-item';
  const thumb = document.createElement('span');
  thumb.className = 'recording-thumb';
  thumb.textContent = '▶';
  const meta = document.createElement('span');
  meta.className = 'recording-meta';
  const title = document.createElement('b');
  title.textContent = new Date(recordingStartedAt).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const duration = document.createElement('small');
  duration.textContent = `${Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000))} сек · локальный файл`;
  const download = document.createElement('a');
  download.href = url;
  download.download = fileName;
  download.textContent = 'Скачать';
  meta.append(title, duration);
  item.append(thumb, meta, download);
  const list = $('#recordingList');
  list.querySelector('.empty-state')?.remove();
  list.prepend(item);
  $('#recordBtn').textContent = '● Начать запись';
  addEvent('Запись сохранена', 'Файл скачивается из раздела «Записи»', 'green');
  showToast('Запись готова. Скачай её в разделе «Записи».');
}

// Звуковые примеры воспроизводятся в браузере. При подключении API команды отправляются плате.
let audioContext = null;
let masterGain = null;
let audioNodes = [];
let audioTimer = null;
function prepareAudio() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) throw new Error('Web Audio is unavailable');
  if (!audioContext) {
    audioContext = new AudioContextClass();
    masterGain = audioContext.createGain();
    masterGain.gain.value = Number($('#volumeSlider').value) / 100;
    masterGain.connect(audioContext.destination);
  }
  if (audioContext.state === 'suspended') audioContext.resume();
  return audioContext;
}

function stopPreview() {
  clearInterval(audioTimer);
  audioTimer = null;
  audioNodes.forEach(node => { try { node.stop(); } catch {} });
  audioNodes = [];
}

function playWhiteNoise() {
  const context = prepareAudio();
  const buffer = context.createBuffer(1, context.sampleRate * 2, context.sampleRate);
  const channel = buffer.getChannelData(0);
  for (let i = 0; i < channel.length; i++) channel[i] = (Math.random() * 2 - 1) * .28;
  const source = context.createBufferSource();
  const tone = context.createBiquadFilter();
  tone.type = 'lowpass';
  tone.frequency.value = 900;
  source.buffer = buffer;
  source.loop = true;
  source.connect(tone).connect(masterGain);
  source.start();
  audioNodes.push(source);
}

function playLullaby() {
  const context = prepareAudio();
  const oscillator = context.createOscillator();
  const envelope = context.createGain();
  const notes = [261.63, 329.63, 392, 329.63, 293.66, 349.23, 392, 349.23];
  const noteDuration = .62;
  const sequenceDuration = notes.length * noteDuration;
  oscillator.type = 'sine';
  oscillator.connect(envelope).connect(masterGain);
  const scheduleSequence = () => {
    const startAt = context.currentTime + .04;
    notes.forEach((note, index) => {
      const at = startAt + index * noteDuration;
      oscillator.frequency.setValueAtTime(note, at);
      envelope.gain.setValueAtTime(0, at);
      envelope.gain.linearRampToValueAtTime(.32, at + .07);
      envelope.gain.linearRampToValueAtTime(0, at + .52);
    });
  };
  scheduleSequence();
  oscillator.start();
  audioTimer = setInterval(scheduleSequence, sequenceDuration * 1000);
  audioNodes.push(oscillator);
}

let apiBase = localStorage.getItem('radio-nanny-api-url') || '';
let apiOnline = false;
let apiTimer = null;
if (apiBase) $('#apiUrl').value = apiBase;

function setDeviceConnection(online, message) {
  apiOnline = online;
  $('#connectionPill').classList.toggle('is-offline', !online);
  $('#connectionText').textContent = online ? 'Устройство онлайн' : (message || 'Нет связи');
  $('#deviceDot').classList.toggle('online', online);
  $('#deviceState').textContent = online ? 'Устройство онлайн' : 'Нет подключения';
  $('#dataLabel').classList.toggle('live', online);
  $('#dataLabel').innerHTML = online ? '<i></i>Показания с устройства' : '<i></i>Ожидание данных устройства';
  $('#eventsSubtitle').textContent = online ? 'События за сутки' : 'События за сутки';
  $('#controlsNote').textContent = online
    ? 'Команды отправляются контроллеру через настроенный API.'
    : 'Звук воспроизводится в браузере. Команды на устройство отправляются только после подключения программы.';
}

function applyDevicePayload(payload) {
  const aliases = {
    temp_c: ['temp_c', 'temperature', 'temperature_c'],
    humidity_pct: ['humidity_pct', 'humidity'],
    co2_ppm: ['co2_ppm', 'co2'],
    noise_db: ['noise_db', 'noise'],
    motion: ['motion', 'movement'],
    respiration_bpm: ['respiration_bpm', 'breathing_rate']
  };
  Object.entries(aliases).forEach(([key, possibleKeys]) => {
    const foundKey = possibleKeys.find(name => Object.hasOwn(payload, name));
    if (foundKey) setReading(key, payload[foundKey], true);
  });
  const battery = payload.battery_pct ?? payload.battery;
  $('.battery').textContent = Number.isFinite(Number(battery)) ? `${Math.round(Number(battery))}%` : 'онлайн';
  const timestamp = payload.timestamp || payload.updated_at;
  if (timestamp) $('#dataLabel').title = `Последнее обновление: ${timestamp}`;
}

async function pollDevice(showFailure = false) {
  if (!apiBase) return false;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4500);
  try {
    const response = await fetch(`${apiBase}/api/status`, { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    applyDevicePayload(payload);
    setDeviceConnection(true);
    return true;
  } catch (error) {
    setDeviceConnection(false, 'Нет связи');
  restoreEmptyReadings();
    $('.battery').textContent = '—';
    if (showFailure) showToast('Не получилось получить /api/status. Проверь адрес, работу программы и доступ браузера к API.');
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function startPolling() {
  clearInterval(apiTimer);
  pollDevice(true).then(connected => {
    if (connected) showToast('Показания устройства подключены.');
  });
  apiTimer = setInterval(() => pollDevice(false), 2500);
}

$('#deviceForm').addEventListener('submit', event => {
  event.preventDefault();
  const value = $('#apiUrl').value.trim().replace(/\/+$/, '');
  if (!value) {
    clearInterval(apiTimer);
    apiTimer = null;
    apiBase = '';
    apiOnline = false;
    localStorage.removeItem('radio-nanny-api-url');
    restoreEmptyReadings();
    setDeviceConnection(false, 'Нет связи');
    $('.battery').textContent = '—';
    showToast('Подключение к устройству отключено.');
    return;
  }
  try {
    const parsed = new URL(value);
    if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Unsupported protocol');
  } catch {
    showToast('Укажи полный адрес API, например http://192.168.4.1:5000');
    return;
  }
  apiBase = value;
  localStorage.setItem('radio-nanny-api-url', apiBase);
  startPolling();
});

async function sendCommand(action, enabled, extra = {}) {
  if (!apiOnline) return false;
  try {
    const response = await fetch(`${apiBase}/api/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, enabled, ...extra })
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return true;
  } catch {
    showToast('Не удалось отправить команду. Проверь подключение к контроллеру.');
    return false;
  }
}

$$('.control-tile').forEach(button => {
  button.addEventListener('click', async () => {
    const action = button.dataset.action;
    const enabling = button.getAttribute('aria-pressed') !== 'true';
    const audioAction = action === 'lullaby' || action === 'white_noise';
    if (audioAction) {
      stopPreview();
      $$('.control-tile[data-action="lullaby"], .control-tile[data-action="white_noise"]').forEach(item => {
        item.setAttribute('aria-pressed', 'false');
        if (item.querySelector('small')) item.querySelector('small').textContent = item.dataset.action === 'lullaby' ? 'Запустить мелодию' : 'Мягкий фоновый звук';
      });
    }

    if (apiOnline) {
      const accepted = await sendCommand(action, enabling, { volume: Number($('#volumeSlider').value) });
      if (!accepted) return;
    } else if (audioAction && enabling) {
      try {
        if (action === 'white_noise') playWhiteNoise();
        else playLullaby();
      } catch {
        showToast('Звуковое воспроизведение недоступно в этом браузере.');
        return;
      }
    }

    button.setAttribute('aria-pressed', String(enabling));
    const state = button.querySelector('.control-state');
    if (state) state.textContent = enabling ? 'Включён' : 'Выключен';
    const label = action === 'lullaby' ? 'Колыбельная' : action === 'white_noise' ? 'Белый шум' : action === 'light' ? 'Свет' : 'Ночной режим';
    if (action === 'light') cameraStage.classList.toggle('light-on', enabling);
    if (action === 'night_mode') {
      $('#nightVisionBtn').setAttribute('aria-pressed', String(enabling));
      cameraStage.classList.toggle('night-on', enabling);
    }
    addEvent(`${label}: ${enabling ? 'включено' : 'выключено'}`, apiOnline ? 'Команда отправлена устройству' : 'Изменение в интерфейсе', enabling ? 'green' : '');
    showToast(`${label} ${enabling ? (apiOnline ? 'включено на устройстве' : 'включено') : 'выключено'}`);
  });
});

$('#volumeSlider').addEventListener('input', event => {
  const value = Number(event.currentTarget.value);
  $('#volumeValue').textContent = `${value}%`;
  if (masterGain && audioContext) masterGain.gain.setTargetAtTime(value / 100, audioContext.currentTime, .04);
});
$('#volumeSlider').addEventListener('change', async event => {
  if (apiOnline) await sendCommand('volume', true, { volume: Number(event.currentTarget.value) });
});

setDeviceConnection(false, apiBase ? 'Проверка связи' : 'Нет связи');
if (apiBase) startPolling();
