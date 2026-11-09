const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const DESIGN_WIDTH = 1440;
const DESIGN_HEIGHT = 810;

function updateUiScale() {
  const fluid = window.matchMedia('(max-width: 900px)').matches;
  const scale = fluid ? 1 : Math.min(window.innerWidth / DESIGN_WIDTH, window.innerHeight / DESIGN_HEIGHT);
  document.documentElement.style.setProperty('--ui-scale', String(scale));
}
updateUiScale();
window.addEventListener('resize', updateUiScale);

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
  const streamClock = $('#streamClock');
  if (streamClock) streamClock.textContent = now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}
updateClock();
setInterval(updateClock, 1000);

const emptyReadings = {
  temp_c: '—', humidity_pct: '—', co2_ppm: '—'
};

function setReading(key, value, live = false) {
  const target = $(`[data-reading="${key}"]`);
  if (!target || value === undefined || value === null || value === '') return;
  const display = String(value);
  target.textContent = display;
  const reportTarget = $(`[data-report="${key}"]`);
  if (reportTarget) reportTarget.textContent = display;
  const state = $(`[data-state="${key}"]`);
  if (state) {
    state.textContent = live ? 'Онлайн' : 'Офлайн';
    state.classList.toggle('live-state', live);
  }
}

function restoreEmptyReadings() {
  Object.entries(emptyReadings).forEach(([key, value]) => setReading(key, value, false));
}

function createEventRow(title, detail, tone = '') {
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
  return row;
}

function addEvent(title, detail, tone = '') {
  const list = $('#eventList');
  if (!list) return;
  const row = createEventRow(title, detail, tone);
  list.prepend(row);
  const settingsList = $('#settingsEventList');
  settingsList?.querySelector('.empty-events')?.remove();
  settingsList?.prepend(row.cloneNode(true));
  const count = $('#dailyEventCount');
  if (count) count.textContent = list.querySelectorAll('.event-row').length;
}

function clearEvents() {
  $('#eventList')?.replaceChildren();
  const settingsList = $('#settingsEventList');
  if (settingsList) {
    settingsList.replaceChildren();
    const empty = document.createElement('div');
    empty.className = 'empty-events';
    empty.textContent = 'Событий пока нет';
    settingsList.append(empty);
  }
  const count = $('#dailyEventCount');
  if (count) count.textContent = '0';
}

// Переключение экранов приложения.
const navLinks = $$('.nav-item');
const homePanels = [$('.page-heading', $('#dashboard')), $('.camera-panel'), $('.side-stack')];
const viewScreens = {
  reports: $('#reports'),
  recordings: $('#recordings'),
  settings: $('#settings')
};

function setView(view) {
  homePanels.forEach(panel => { if (panel) panel.hidden = view !== 'home'; });
  Object.entries(viewScreens).forEach(([name, panel]) => {
    if (panel) panel.hidden = view !== name;
  });
  navLinks.forEach(link => link.classList.toggle('active', link.dataset.view === view));
  document.body.dataset.view = view;
  history.replaceState(null, '', `#${view === 'home' ? 'dashboard' : view}`);
  if (view === 'recordings' && typeof loadMediaGallery === 'function') loadMediaGallery();
}

navLinks.forEach(link => link.addEventListener('click', event => {
  event.preventDefault();
  setView(link.dataset.view);
}));

const hashView = location.hash.replace('#', '');
setView(['reports', 'recordings', 'settings'].includes(hashView) ? hashView : 'home');

function setSettingsPane(name) {
  $$('.settings-menu-item[data-settings]').forEach(item => {
    item.classList.toggle('active', item.dataset.settings === name);
  });
  $$('.settings-pane').forEach(pane => {
    const active = pane.dataset.pane === name;
    pane.classList.toggle('active', active);
    pane.hidden = !active;
  });
}

$$('.settings-menu-item[data-settings]').forEach(item => {
  if (item.disabled) return;
  item.addEventListener('click', event => {
    if (event.target.closest('.switch')) return;
    const name = item.dataset.settings;
    if (!name || name === 'pin') return;
    setSettingsPane(name === 'autonight' ? 'autonight' : name);
  });
});

$('#openEventsFromReports')?.addEventListener('click', () => {
  setView('settings');
  setSettingsPane('events');
});

$('#clearEventsBtn')?.addEventListener('click', clearEvents);

function setAutoNightlight(enabled, announce = true) {
  localStorage.setItem('radio-nanny-auto-nightlight', enabled ? '1' : '0');
  ['#autoNightlightBtn', '#autoNightlightBtnDetail'].forEach(selector => {
    const btn = $(selector);
    if (!btn) return;
    btn.setAttribute('aria-checked', String(enabled));
  });
  if (enabled) applyAutoNightlight();
}

function applyAutoNightlight() {
  // Режим ждёт сигнал освещённости с устройства: ночник включается, когда в комнате гаснет свет.
  if (localStorage.getItem('radio-nanny-auto-nightlight') !== '1') return;
}

['#autoNightlightBtn', '#autoNightlightBtnDetail'].forEach(selector => {
  $(selector)?.addEventListener('click', event => {
    event.stopPropagation();
    const enabled = $(selector).getAttribute('aria-checked') !== 'true';
    setAutoNightlight(enabled);
    setSettingsPane('autonight');
  });
});

setAutoNightlight(localStorage.getItem('radio-nanny-auto-nightlight') === '1', false);

// Тема сохраняется в этом браузере.
const savedTheme = localStorage.getItem('radio-nanny-theme');
if (savedTheme === 'light') document.body.dataset.theme = 'light';
$('#themeBtn').addEventListener('click', () => {
  const light = document.body.dataset.theme !== 'light';
  document.body.dataset.theme = light ? 'light' : 'dark';
  localStorage.setItem('radio-nanny-theme', light ? 'light' : 'dark');
});

function setSitePalette(palette) {
  const next = palette === 'graphite' ? 'graphite' : 'blue';
  if (next === 'blue') delete document.body.dataset.palette;
  else document.body.dataset.palette = next;
  localStorage.setItem('radio-nanny-palette', next);
  $$('.theme-choice').forEach(btn => {
    const active = btn.dataset.palette === next;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = next === 'graphite' ? '#14171b' : '#0b1423';
}

$$('.theme-choice').forEach(btn => {
  btn.addEventListener('click', () => setSitePalette(btn.dataset.palette));
});
setSitePalette(localStorage.getItem('radio-nanny-palette') || 'blue');

// Локальный MJPEG с /stream (CSI-камера на устройстве).
const cameraStage = $('#cameraStage');
const streamPlaceholder = $('#streamPlaceholder');
const mjpegStream = $('#mjpegStream');
const videoStream = $('#videoStream');
const streamError = $('#streamError');
const LOCAL_STREAM_URL = '/stream';
let streamType = 'mjpeg';
let streamConnected = false;
let mediaRecording = false;
let mediaBusy = false;

function setCameraAudioEnabled(enabled) {
  const muteBtn = $('#cameraMuteBtn');
  const volume = $('#cameraVolume');
  if (muteBtn) muteBtn.disabled = !enabled;
  if (volume) volume.disabled = !enabled;
}

function applyCameraVolume() {
  const slider = $('#cameraVolume');
  if (!slider || !videoStream) return;
  const value = Number(slider.value);
  videoStream.volume = Math.max(0, Math.min(1, value / 100));
  const label = $('#cameraVolumeValue');
  if (label) label.textContent = `${value}%`;
}

function setCameraMuted(muted) {
  if (!videoStream) return;
  videoStream.muted = muted;
  const muteBtn = $('#cameraMuteBtn');
  if (!muteBtn) return;
  muteBtn.setAttribute('aria-pressed', String(muted));
  muteBtn.setAttribute('aria-label', muted ? 'Включить звук камеры' : 'Выключить звук камеры');
  muteBtn.title = muted ? 'Звук выключен' : 'Звук включён';
}

function setRecordButtons(recording) {
  const label = recording ? '■ Остановить' : '● Начать запись';
  const pressed = String(!!recording);
  ['#recordBtn', '#cameraRecordBtn'].forEach(selector => {
    const btn = $(selector);
    if (!btn) return;
    if (selector === '#recordBtn') btn.textContent = label;
    btn.setAttribute('aria-pressed', pressed);
    btn.classList.toggle('is-recording', !!recording);
    btn.setAttribute('aria-label', recording ? 'Остановить запись видео' : 'Начать запись видео');
    btn.title = recording ? 'Остановить запись' : 'Запись видео';
  });
}

function setCameraStatus(state, live = false) {
  $('#cameraState').textContent = state;
  $('#cameraDot')?.classList.toggle('is-live', live);
  $('#qualityTag').textContent = live ? (mediaRecording ? 'REC' : 'Прямой эфир') : 'ОЖИДАНИЕ';
  $('#qualityTag').classList.toggle('is-live', live);
  $('#qualityTag').classList.toggle('is-recording', live && mediaRecording);
  $('#snapshotBtn').disabled = !live || mediaBusy;
  const canRecord = live || mediaRecording;
  $('#recordBtn').disabled = !canRecord || mediaBusy;
  $('#cameraRecordBtn').disabled = !canRecord || mediaBusy;
  setCameraAudioEnabled(false);
  streamConnected = live;
  setRecordButtons(mediaRecording);
}

function showCameraPlaceholder() {
  streamConnected = false;
  mjpegStream.hidden = true;
  if (videoStream) {
    videoStream.hidden = true;
    videoStream.pause();
    videoStream.removeAttribute('src');
    videoStream.load();
  }
  streamPlaceholder.hidden = false;
  streamError.hidden = true;
  setCameraStatus('Источник не подключён', false);
}

function startLocalStream() {
  streamType = 'mjpeg';
  streamError.hidden = true;
  setCameraStatus('Подключение…', false);
  if (videoStream) {
    videoStream.hidden = true;
    videoStream.pause();
    videoStream.removeAttribute('src');
    videoStream.load();
  }
  mjpegStream.hidden = false;
  mjpegStream.src = `${LOCAL_STREAM_URL}?t=${Date.now()}`;
}

mjpegStream.addEventListener('load', () => {
  streamPlaceholder.hidden = true;
  streamError.hidden = true;
  setCameraStatus('', true);
});
mjpegStream.addEventListener('error', () => {
  showCameraPlaceholder();
});

async function initCamera() {
  showCameraPlaceholder();
  try {
    const response = await fetch('/api/camera', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (payload?.available === false && payload?.error) {
      showCameraPlaceholder();
      return;
    }
    startLocalStream();
  } catch {
    // Нет API — всё равно пробуем локальный /stream; при ошибке останется картинка.
    startLocalStream();
  }
}

initCamera();

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen?.();
  else cameraStage.requestFullscreen?.().catch(() => showToast('Полный экран недоступен в этом браузере.'));
}
$('#cameraFullscreenBtn')?.addEventListener('click', toggleFullscreen);

$('#cameraMuteBtn')?.addEventListener('click', () => {
  if (!streamConnected || streamType !== 'video') return;
  const enablingSound = videoStream.muted;
  setCameraMuted(!enablingSound);
  if (enablingSound) applyCameraVolume();
});

$('#cameraVolume')?.addEventListener('input', event => {
  const value = Number(event.currentTarget.value);
  $('#cameraVolumeValue').textContent = `${value}%`;
  if (!streamConnected || streamType !== 'video') return;
  applyCameraVolume();
  if (value === 0) setCameraMuted(true);
  else if (videoStream.muted) setCameraMuted(false);
});

function formatBytes(size) {
  if (!Number.isFinite(size) || size < 0) return '';
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} КБ`;
  return `${(size / (1024 * 1024)).toFixed(1)} МБ`;
}

function formatMediaDate(value) {
  const date = new Date(typeof value === 'number' ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function emptyMediaState() {
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.innerHTML = `
    <span aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/></svg></span>
    <b>Записей пока нет</b>
    <small>Сделайте снимок или запись с камеры — файлы появятся здесь.</small>
  `;
  return empty;
}

function renderMediaItem(item) {
  const article = document.createElement('article');
  article.className = `recording-item is-${item.kind}`;
  article.dataset.name = item.name;

  const preview = document.createElement(item.kind === 'photo' ? 'img' : 'video');
  preview.className = 'recording-preview';
  preview.src = item.url;
  if (item.kind === 'photo') {
    preview.alt = item.name;
    preview.loading = 'lazy';
  } else {
    preview.controls = true;
    preview.playsInline = true;
    preview.preload = 'metadata';
  }

  const meta = document.createElement('div');
  meta.className = 'recording-meta';
  const title = document.createElement('b');
  title.textContent = item.kind === 'photo' ? 'Снимок' : 'Видео';
  const details = document.createElement('small');
  details.textContent = [formatMediaDate(item.created_at || item.mtime), formatBytes(item.size)]
    .filter(Boolean)
    .join(' · ');
  meta.append(title, details);

  const actions = document.createElement('div');
  actions.className = 'recording-actions';
  const open = document.createElement('a');
  open.className = 'text-button';
  open.href = item.url;
  open.target = '_blank';
  open.rel = 'noopener';
  open.textContent = 'Открыть';
  const remove = document.createElement('button');
  remove.className = 'text-button danger';
  remove.type = 'button';
  remove.textContent = 'Удалить';
  remove.addEventListener('click', () => deleteMediaItem(item.name));
  actions.append(open, remove);

  article.append(preview, meta, actions);
  return article;
}

function renderMediaGallery(items) {
  const list = $('#recordingList');
  if (!list) return;
  list.replaceChildren();
  if (!items.length) {
    list.append(emptyMediaState());
    return;
  }
  items.forEach(item => list.append(renderMediaItem(item)));
}

async function loadMediaGallery(showFailure = false) {
  try {
    const response = await fetch('/api/media', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    renderMediaGallery(payload.items || []);
    return true;
  } catch {
    if (showFailure) showToast('Не удалось загрузить галерею записей.');
    return false;
  }
}

async function deleteMediaItem(name) {
  if (!name) return;
  if (!window.confirm('Удалить этот файл из записей?')) return;
  try {
    const response = await fetch(`/api/media/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    showToast('Файл удалён');
    addEvent('Файл удалён', name, '');
    await loadMediaGallery();
  } catch (error) {
    showToast(error.message || 'Не удалось удалить файл');
  }
}

async function saveSnapshot() {
  if (!streamConnected || mediaBusy) return;
  mediaBusy = true;
  setCameraStatus($('#cameraState').textContent, streamConnected);
  try {
    const response = await fetch('/api/media/snapshot', { method: 'POST' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    showToast('Снимок сохранён во вкладке «Записи»');
    addEvent('Снимок сохранён', 'Файл в галерее BabyBox', 'cyan');
    await loadMediaGallery();
  } catch (error) {
    showToast(error.message || 'Не удалось сохранить снимок');
  } finally {
    mediaBusy = false;
    setCameraStatus($('#cameraState').textContent, streamConnected);
  }
}

async function toggleMediaRecording() {
  if (mediaBusy) return;
  mediaBusy = true;
  setCameraStatus($('#cameraState').textContent, streamConnected);
  try {
    if (mediaRecording) {
      const response = await fetch('/api/media/record/stop', { method: 'POST' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      mediaRecording = false;
      showToast('Видео сохранено во вкладке «Записи»');
      addEvent('Запись сохранена', 'Видео в галерее BabyBox', 'green');
      await loadMediaGallery();
    } else {
      if (!streamConnected) {
        showToast('Сначала дождитесь прямого эфира камеры');
        return;
      }
      const response = await fetch('/api/media/record/start', { method: 'POST' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      mediaRecording = true;
      showToast('Идёт запись видео…');
      addEvent('Началась запись видео', 'Сохранение на BabyBox', 'orange');
    }
  } catch (error) {
    showToast(error.message || 'Ошибка записи видео');
  } finally {
    mediaBusy = false;
    setCameraStatus(mediaRecording ? 'Идёт запись…' : (streamConnected ? '' : 'Источник не подключён'), streamConnected);
  }
}

$('#snapshotBtn').addEventListener('click', saveSnapshot);
$('#recordBtn')?.addEventListener('click', toggleMediaRecording);
$('#cameraRecordBtn')?.addEventListener('click', toggleMediaRecording);
$('#refreshMediaBtn')?.addEventListener('click', () => {
  loadMediaGallery(true).then(ok => {
    if (ok) showToast('Галерея обновлена');
  });
});
loadMediaGallery();

const DEFAULT_VOLUME = 0.35;
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
    masterGain.gain.value = DEFAULT_VOLUME;
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

function setDeviceConnection(online) {
  apiOnline = online;
  // Карточка в сайдбаре — постоянная заглушка «Устройство 1 / Онлайн».
  $('#deviceDot')?.classList.add('online');
  if ($('#deviceState')) $('#deviceState').textContent = 'Онлайн';
}

function applyDevicePayload(payload) {
  const aliases = {
    temp_c: ['temp_c', 'temperature', 'temperature_c'],
    humidity_pct: ['humidity_pct', 'humidity'],
    co2_ppm: ['co2_ppm', 'co2']
  };
  Object.entries(aliases).forEach(([key, possibleKeys]) => {
    const foundKey = possibleKeys.find(name => Object.hasOwn(payload, name));
    if (foundKey) setReading(key, payload[foundKey], true);
  });
}

function statusEndpoint() {
  // Пустой apiBase = тот же хост, с которого открыт сайт (Raspberry Pi).
  return apiBase ? `${apiBase}/api/status` : '/api/status';
}

async function pollDevice(showFailure = false) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4500);
  try {
    const response = await fetch(statusEndpoint(), { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    applyDevicePayload(payload);
    setDeviceConnection(true);
    return true;
  } catch {
    setDeviceConnection(false);
    restoreEmptyReadings();
    if (showFailure) showToast('Не получилось получить /api/status. Проверь адрес, работу программы и доступ браузера к API.');
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function startPolling(announce = false) {
  clearInterval(apiTimer);
  pollDevice(announce).then(connected => {
    if (announce && connected) showToast('Показания устройства подключены.');
  });
  apiTimer = setInterval(() => pollDevice(false), 2500);
}

$('#deviceForm').addEventListener('submit', event => {
  event.preventDefault();
  const value = $('#apiUrl').value.trim().replace(/\/+$/, '');
  if (!value) {
    apiBase = '';
    localStorage.removeItem('radio-nanny-api-url');
    startPolling(true);
    showToast('Показания с этого устройства.');
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
  startPolling(true);
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

function setControlState(button, enabling) {
  button.setAttribute('aria-pressed', String(enabling));
  const state = button.querySelector('.control-state');
  if (!state) return;
  const action = button.dataset.action;
  if (action === 'lullaby') state.textContent = enabling ? 'Играет' : 'Выключена';
  else if (action === 'light') state.textContent = enabling ? 'Включён' : 'Выключен';
  else state.textContent = enabling ? 'Включён' : 'Выключен';
}

$$('.control-tile:not(:disabled)').forEach(button => {
  button.addEventListener('click', async () => {
    const action = button.dataset.action;
    if (action === 'alarm') return;
    const enabling = button.getAttribute('aria-pressed') !== 'true';

    if (action === 'lullaby') {
      stopPreview();
      if (!enabling) {
        setControlState(button, false);
        addEvent('Колыбельная: выключено', apiOnline ? 'Команда отправлена устройству' : 'Изменение в интерфейсе');
        if (apiOnline) await sendCommand(action, false);
        return;
      }
    }

    if (apiOnline) {
      const accepted = await sendCommand(action, enabling, { volume: Math.round(DEFAULT_VOLUME * 100) });
      if (!accepted) return;
    } else if (action === 'lullaby' && enabling) {
      try {
        playLullaby();
      } catch {
        showToast('Звуковое воспроизведение недоступно в этом браузере.');
        return;
      }
    }

    setControlState(button, enabling);
    if (action === 'light') cameraStage.classList.toggle('light-on', enabling);

    const label = action === 'lullaby' ? 'Колыбельная' : 'Ночник';
    addEvent(`${label}: ${enabling ? 'включено' : 'выключено'}`, apiOnline ? 'Команда отправлена устройству' : 'Изменение в интерфейсе', enabling ? 'green' : '');
  });
});

setDeviceConnection(false);
startPolling(false);
