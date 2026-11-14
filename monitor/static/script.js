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

// ~2.5s poll × 24 ≈ последняя минута показаний
const SPARK_POINTS = 24;
const sparkHistory = {
  temp_c: [],
  humidity_pct: [],
  co2_ppm: []
};

function linePathFromValues(values, width = 100, height = 24, minSpan = 0.4) {
  if (!values.length) return '';
  const padY = Math.max(3, height * 0.08);
  let min = Math.min(...values);
  let max = Math.max(...values);
  // Чуть растягиваем шкалу, чтобы мелкие изменения были видны
  if (max - min < minSpan) {
    const mid = (min + max) / 2;
    min = mid - minSpan / 2;
    max = mid + minSpan / 2;
  }
  const range = max - min || 1;
  const stepX = values.length === 1 ? 0 : width / (values.length - 1);
  const points = values.map((value, index) => {
    const x = index * stepX;
    const y = padY + (height - padY * 2) * (1 - (value - min) / range);
    return [x, y];
  });
  if (points.length === 1) {
    const [, y] = points[0];
    return `M0 ${y.toFixed(2)} L${width} ${y.toFixed(2)}`;
  }
  let d = `M${points[0][0].toFixed(2)} ${points[0][1].toFixed(2)}`;
  for (let i = 1; i < points.length; i += 1) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const cx = (x0 + x1) / 2;
    d += ` Q${cx.toFixed(2)} ${y0.toFixed(2)} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }
  return d;
}

function drawSpark(key) {
  const path = $(`[data-spark="${key}"]`);
  if (!path) return;
  path.setAttribute('d', linePathFromValues(sparkHistory[key] || [], 100, 24, 0.4));
}

function pushSparkSample(key, value) {
  const num = Number(value);
  if (!Number.isFinite(num) || !sparkHistory[key]) return;
  const hist = sparkHistory[key];
  hist.push(num);
  if (hist.length > SPARK_POINTS) hist.shift();
  drawSpark(key);
}

function clearSparks() {
  Object.keys(sparkHistory).forEach(key => {
    sparkHistory[key] = [];
    drawSpark(key);
  });
}

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
  if (live) pushSparkSample(key, value);
  else if (sparkHistory[key]) {
    sparkHistory[key] = [];
    drawSpark(key);
  }
}

function restoreEmptyReadings() {
  clearSparks();
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

let reportTimer = null;

function setView(view) {
  homePanels.forEach(panel => { if (panel) panel.hidden = view !== 'home'; });
  Object.entries(viewScreens).forEach(([name, panel]) => {
    if (panel) panel.hidden = view !== name;
  });
  navLinks.forEach(link => link.classList.toggle('active', link.dataset.view === view));
  document.body.dataset.view = view;
  history.replaceState(null, '', `#${view === 'home' ? 'dashboard' : view}`);
  if (view === 'recordings' && typeof loadMediaGallery === 'function') loadMediaGallery();
  if (view !== 'recordings' && typeof closeMediaViewer === 'function') closeMediaViewer();
  // Reports polling is started later from ensureReportsForView() after helpers exist.
  if (typeof ensureReportsForView === 'function') ensureReportsForView(view);
}

navLinks.forEach(link => link.addEventListener('click', event => {
  event.preventDefault();
  setView(link.dataset.view);
}));

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
    if (!name) return;
    setSettingsPane(name === 'autonight' ? 'autonight' : name);
    if (name === 'profile') loadProfile();
    if (name === 'lullaby') loadLullabyChoices();
    if (name === 'pin') loadPinStatus();
  });
});

$('#clearEventsBtn')?.addEventListener('click', clearEvents);
setSettingsPane('profile');

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

function closeMediaViewer() {
  const viewer = $('#mediaViewer');
  const stage = $('#mediaViewerStage');
  if (!viewer || !stage) return;
  stage.querySelectorAll('video').forEach(video => {
    try {
      video.pause();
      video.removeAttribute('src');
      video.load();
    } catch {}
  });
  stage.replaceChildren();
  viewer.hidden = true;
  document.body.classList.remove('media-viewer-open');
}

function openMediaViewer(item) {
  const viewer = $('#mediaViewer');
  const stage = $('#mediaViewerStage');
  if (!viewer || !stage) return;

  closeMediaViewer();

  const title = $('#mediaViewerTitle');
  const meta = $('#mediaViewerMeta');
  if (title) title.textContent = item.kind === 'photo' ? 'Снимок' : 'Видео';
  if (meta) {
    meta.textContent = [formatMediaDate(item.created_at || item.mtime), formatBytes(item.size), item.name]
      .filter(Boolean)
      .join(' · ');
  }

  if (item.kind === 'photo') {
    const image = document.createElement('img');
    image.className = 'media-viewer-media';
    image.src = item.url;
    image.alt = item.name || 'Снимок';
    stage.append(image);
  } else {
    const video = document.createElement('video');
    video.className = 'media-viewer-media';
    video.src = item.url;
    video.controls = true;
    video.playsInline = true;
    video.autoplay = true;
    stage.append(video);
  }

  viewer.hidden = false;
  document.body.classList.add('media-viewer-open');
}

$('#mediaViewerClose')?.addEventListener('click', closeMediaViewer);
$('#mediaViewerBackdrop')?.addEventListener('click', closeMediaViewer);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !$('#mediaViewer')?.hidden) closeMediaViewer();
});

function renderMediaItem(item) {
  const article = document.createElement('article');
  article.className = `recording-item is-${item.kind}`;
  article.dataset.name = item.name;
  article.tabIndex = 0;
  article.setAttribute('role', 'button');
  article.setAttribute('aria-label', `${item.kind === 'photo' ? 'Снимок' : 'Видео'}: открыть`);

  const previewWrap = document.createElement('div');
  previewWrap.className = 'recording-preview-wrap';
  const preview = document.createElement(item.kind === 'photo' ? 'img' : 'video');
  preview.className = 'recording-preview';
  preview.src = item.url;
  if (item.kind === 'photo') {
    preview.alt = item.name;
    preview.loading = 'lazy';
  } else {
    preview.muted = true;
    preview.playsInline = true;
    preview.preload = 'metadata';
    preview.removeAttribute('controls');
  }
  const playMark = document.createElement('span');
  playMark.className = 'recording-play-mark';
  playMark.hidden = item.kind === 'photo';
  playMark.setAttribute('aria-hidden', 'true');
  playMark.textContent = '▶';
  previewWrap.append(preview, playMark);

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
  const remove = document.createElement('button');
  remove.className = 'text-button danger';
  remove.type = 'button';
  remove.textContent = 'Удалить';
  remove.addEventListener('click', event => {
    event.stopPropagation();
    deleteMediaItem(item.name);
  });
  actions.append(remove);

  const open = () => openMediaViewer(item);
  article.addEventListener('click', open);
  article.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      open();
    }
  });

  article.append(previewWrap, meta, actions);
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
    if (!$('#mediaViewer')?.hidden) closeMediaViewer();
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
  const localAudio = $('#lullabyAudio');
  if (localAudio && !localAudio.paused) localAudio.pause();
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
let pollFails = 0;

function normalizeApiBase(value) {
  const trimmed = (value || '').trim().replace(/\/+$/, '');
  if (!trimmed) return '';
  try {
    const parsed = new URL(trimmed);
    if (!['http:', 'https:'].includes(parsed.protocol)) return '';
    // Тот же хост, что и страница — всегда ходим относительным /api/status
    if (parsed.origin === window.location.origin) return '';
    return trimmed;
  } catch {
    return '';
  }
}

apiBase = normalizeApiBase(apiBase);
if (apiBase) {
  localStorage.setItem('radio-nanny-api-url', apiBase);
  if ($('#apiUrl')) $('#apiUrl').value = apiBase;
} else {
  localStorage.removeItem('radio-nanny-api-url');
  if ($('#apiUrl')) $('#apiUrl').value = '';
}

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
    if (!foundKey) return;
    const raw = payload[foundKey];
    if (raw === undefined || raw === null || raw === '') return;
    if (typeof raw === 'number' && !Number.isFinite(raw)) return;
    setReading(key, raw, true);
  });

  if (Object.hasOwn(payload, 'light')) {
    const lightBtn = $('.control-tile[data-action="light"]');
    if (lightBtn) {
      const on = Boolean(payload.light);
      setControlState(lightBtn, on);
      cameraStage?.classList.toggle('light-on', on);
    }
  }
}

function statusEndpoint() {
  // Пустой apiBase = тот же хост, с которого открыт сайт (Raspberry Pi).
  return apiBase ? `${apiBase}/api/status` : '/api/status';
}

function reportEndpoint() {
  return apiBase ? `${apiBase}/api/reports/today` : '/api/reports/today';
}

function formatReportValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function drawReportChart(key, series) {
  const path = $(`[data-report-chart="${key}"]`);
  if (!path) return;
  const values = (series || [])
    .map(point => Number(point?.v))
    .filter(value => Number.isFinite(value));
  path.setAttribute('d', linePathFromValues(values, 640, 120, key === 'humidity_pct' ? 2 : 0.6));
}

function applyDayReport(payload) {
  if (!payload || typeof payload !== 'object') return;
  const label = $('#reportDateLabel');
  if (label && payload.date) {
    try {
      const date = new Date(`${payload.date}T12:00:00`);
      label.textContent = date.toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
      });
    } catch {
      label.textContent = payload.date;
    }
  }

  ['temp_c', 'humidity_pct'].forEach(key => {
    const block = payload[key] || {};
    const current = $(`[data-report="${key}"]`);
    const min = $(`[data-report-min="${key}"]`);
    const max = $(`[data-report-max="${key}"]`);
    if (current) current.textContent = formatReportValue(block.current);
    if (min) min.textContent = formatReportValue(block.min);
    if (max) max.textContent = formatReportValue(block.max);
    drawReportChart(key, block.series || []);
  });
}

async function loadDayReport() {
  try {
    const response = await fetch(reportEndpoint(), { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    applyDayReport(await response.json());
  } catch {
    // keep previous report values
  }
}

function startReportPolling() {
  clearInterval(reportTimer);
  loadDayReport();
  reportTimer = setInterval(loadDayReport, 30000);
}

function stopReportPolling() {
  clearInterval(reportTimer);
  reportTimer = null;
}

function ensureReportsForView(view) {
  if (view === 'reports') startReportPolling();
  else stopReportPolling();
}

const hashView = location.hash.replace('#', '');
setView(['reports', 'recordings', 'settings'].includes(hashView) ? hashView : 'home');

async function pollDevice(showFailure = false) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4500);
  try {
    const response = await fetch(statusEndpoint(), { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    applyDevicePayload(payload);
    pollFails = 0;
    setDeviceConnection(true);
    return true;
  } catch {
    pollFails += 1;
    setDeviceConnection(false);
    // Не мигаем «нет данных» на каждом сбое — только после нескольких подряд.
    if (pollFails >= 3) restoreEmptyReadings();
    if (showFailure) showToast('Не получилось получить /api/status. Проверь адрес, работу программы и доступ браузера к API.');
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function startPolling(announce = false) {
  clearInterval(apiTimer);
  pollFails = 0;
  pollDevice(announce).then(connected => {
    if (announce && connected) showToast('Показания устройства подключены.');
  });
  apiTimer = setInterval(() => pollDevice(false), 4000);
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
  apiBase = normalizeApiBase(value);
  if (apiBase) localStorage.setItem('radio-nanny-api-url', apiBase);
  else localStorage.removeItem('radio-nanny-api-url');
  startPolling(true);
  showToast(apiBase ? 'Подключено к удалённому API.' : 'Показания с этого устройства.');
});

function controlEndpoint() {
  return apiBase ? `${apiBase}/api/control` : '/api/control';
}

async function sendCommand(action, enabled, extra = {}) {
  try {
    const response = await fetch(controlEndpoint(), {
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

    if (action === 'light') {
      const accepted = await sendCommand(action, enabling);
      if (!accepted) return;
      setControlState(button, enabling);
      cameraStage?.classList.toggle('light-on', enabling);
      addEvent(`Ночник: ${enabling ? 'включено' : 'выключено'}`, 'Команда отправлена устройству', enabling ? 'green' : '');
      return;
    }

    if (action === 'lullaby') {
      stopPreview();
      const audio = $('#lullabyAudio');
      if (!enabling) {
        audio?.pause();
        setControlState(button, false);
        addEvent('Колыбельная: выключено', 'Воспроизведение остановлено на этом устройстве');
        return;
      }
      if (audio?.src) {
        try {
          audio.currentTime = 0;
          await audio.play();
        } catch {
          showToast('Не удалось запустить воспроизведение на этом устройстве.');
          return;
        }
      } else {
        try { playLullaby(); }
        catch { showToast('Звуковое воспроизведение недоступно в этом браузере.'); return; }
      }
      setControlState(button, true);
      addEvent('Колыбельная: играет', 'Воспроизведение на этом устройстве', 'green');
      return;
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

    const label = action === 'lullaby' ? 'Колыбельная' : 'Ночник';
    addEvent(`${label}: ${enabling ? 'включено' : 'выключено'}`, apiOnline ? 'Команда отправлена устройству' : 'Изменение в интерфейсе', enabling ? 'green' : '');
  });
});

setDeviceConnection(false);
startPolling(false);

// Настройки владельца, выбранной мелодии и локальная блокировка панели.
const profileForm = $('#profileForm');
const profileAvatarInput = $('#profileAvatar');
const profileAvatarPreview = $('#profileAvatarPreview');
const profileAvatarFallback = $('#profileAvatarFallback');
const profileEditBtn = $('#profileEditBtn');
const profileCancelBtn = $('#profileCancelBtn');
const profileSaveBtn = $('#profileSaveBtn');
let selectedAvatarFile = null;
let profileSnapshot = null;
let profileEditing = true;

function setFormStatus(id, message, error = false) {
  const target = $(id);
  if (!target) return;
  target.textContent = message;
  target.classList.toggle('is-error', error);
}

function profileHasContent(profile = {}) {
  return Boolean(
    String(profile.first_name || '').trim()
    || String(profile.last_name || '').trim()
    || String(profile.email || '').trim()
    || profile.avatar_url
    || profile.avatar
  );
}

function applyProfileFields(profile = {}) {
  $('#profileFirstName').value = profile.first_name || '';
  $('#profileLastName').value = profile.last_name || '';
  $('#profileEmail').value = profile.email || '';
  if (profile.avatar_url) {
    profileAvatarPreview.src = `${profile.avatar_url}${profile.avatar_url.includes('?') ? '&' : '?'}t=${Date.now()}`;
    profileAvatarPreview.hidden = false;
    profileAvatarFallback.hidden = true;
  } else {
    profileAvatarPreview.removeAttribute('src');
    profileAvatarPreview.hidden = true;
    profileAvatarFallback.hidden = false;
  }
}

function setProfileEditing(enabled, { hasSaved = Boolean(profileSnapshot) } = {}) {
  profileEditing = enabled;
  profileForm?.classList.toggle('is-readonly', !enabled);
  ['#profileFirstName', '#profileLastName', '#profileEmail'].forEach(selector => {
    const input = $(selector);
    if (!input) return;
    input.readOnly = !enabled;
    input.disabled = false;
  });
  if (profileAvatarInput) profileAvatarInput.disabled = !enabled;
  if (profileSaveBtn) profileSaveBtn.hidden = !enabled;
  if (profileCancelBtn) profileCancelBtn.hidden = !enabled || !hasSaved;
  if (profileEditBtn) profileEditBtn.hidden = enabled || !hasSaved;
}

async function loadProfile() {
  try {
    const response = await fetch('/api/profile', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Не удалось прочитать профиль');
    const profile = data.profile || {};
    selectedAvatarFile = null;
    if (profileAvatarInput) profileAvatarInput.value = '';
    const hasContent = data.saved === true || profileHasContent(profile);
    profileSnapshot = hasContent ? {
      first_name: profile.first_name || '',
      last_name: profile.last_name || '',
      email: profile.email || '',
      avatar_url: profile.avatar_url || null,
    } : null;
    applyProfileFields(profileSnapshot || {});
    // Пустой профиль сразу открыт для ввода; заполненный — через «Редактировать».
    setProfileEditing(!hasContent, { hasSaved: hasContent });
    setFormStatus(
      '#profileSaveStatus',
      hasContent
        ? 'Профиль загружен с устройства BabyBox.'
        : 'Профиль пока не заполнен — заполните и сохраните.'
    );
  } catch (error) {
    profileSnapshot = null;
    setProfileEditing(true, { hasSaved: false });
    setFormStatus('#profileSaveStatus', error.message || 'Папка профиля недоступна — данные не сохранены.', true);
  }
}

profileEditBtn?.addEventListener('click', () => {
  setProfileEditing(true, { hasSaved: Boolean(profileSnapshot) });
  setFormStatus('#profileSaveStatus', 'Редактирование. Изменения сохранятся на BabyBox.');
  $('#profileFirstName')?.focus();
});

profileCancelBtn?.addEventListener('click', () => {
  selectedAvatarFile = null;
  if (profileAvatarInput) profileAvatarInput.value = '';
  applyProfileFields(profileSnapshot || {});
  setProfileEditing(false, { hasSaved: Boolean(profileSnapshot) });
  setFormStatus('#profileSaveStatus', 'Изменения отменены.');
});

profileAvatarInput?.addEventListener('change', () => {
  if (!profileEditing) return;
  selectedAvatarFile = profileAvatarInput.files?.[0] || null;
  if (!selectedAvatarFile) return;
  if (selectedAvatarFile.size > 4 * 1024 * 1024) {
    selectedAvatarFile = null;
    profileAvatarInput.value = '';
    showToast('Размер фото не должен превышать 4 МБ.');
    return;
  }
  profileAvatarPreview.src = URL.createObjectURL(selectedAvatarFile);
  profileAvatarPreview.hidden = false;
  profileAvatarFallback.hidden = true;
});

profileForm?.addEventListener('submit', async event => {
  event.preventDefault();
  if (!profileEditing) return;
  const body = new FormData(profileForm);
  if (selectedAvatarFile) body.set('avatar', selectedAvatarFile);
  profileSaveBtn.disabled = true;
  try {
    const response = await fetch('/api/profile', { method: 'POST', body });
    const data = await response.json();
    if (!response.ok || !data.saved) throw new Error(data.error || 'Профиль не сохранён');
    selectedAvatarFile = null;
    if (profileAvatarInput) profileAvatarInput.value = '';
    const profile = data.profile || {};
    profileSnapshot = {
      first_name: profile.first_name || '',
      last_name: profile.last_name || '',
      email: profile.email || '',
      avatar_url: profile.avatar_url || null,
    };
    applyProfileFields(profileSnapshot);
    const hasContent = profileHasContent(profileSnapshot);
    setProfileEditing(!hasContent, { hasSaved: hasContent });
    setFormStatus('#profileSaveStatus', 'Сохранено на устройстве BabyBox.');
    showToast('Данные владельца сохранены на BabyBox.');
  } catch (error) {
    setFormStatus('#profileSaveStatus', error.message || 'Не удалось сохранить профиль.', true);
  } finally {
    profileSaveBtn.disabled = false;
  }
});

let lullabyChoices = [];
let defaultLullaby = null;
const lullabyAudio = $('#lullabyAudio');

function setDefaultLullaby(filename) {
  defaultLullaby = filename;
  const selected = lullabyChoices.find(item => item.name === filename) || lullabyChoices[0];
  if (selected && lullabyAudio) {
    lullabyAudio.src = selected.url;
    lullabyAudio.load();
  }
  $$('.lullaby-choice').forEach(card => {
    const isDefault = card.dataset.file === filename;
    card.classList.toggle('is-default', isDefault);
    const badge = $('.lullaby-default-badge', card);
    if (badge) badge.hidden = !isDefault;
  });
}

async function loadLullabyChoices() {
  const list = $('#lullabyList');
  if (!list) return;
  try {
    const response = await fetch('/api/sounds', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Не удалось загрузить мелодии');
    lullabyChoices = data.sounds || [];
    list.replaceChildren();
    if (!lullabyChoices.length) {
      list.innerHTML = '<div class="empty-state">Аудиофайлы не найдены в папке sounds.</div>';
      return;
    }
    lullabyChoices.forEach((sound, index) => {
      const card = document.createElement('article');
      card.className = 'lullaby-choice';
      card.dataset.file = sound.name;
      const title = document.createElement('b');
      const titles = { 'lullaby-stars.wav': 'Звёзды', 'lullaby-moon.wav': 'Лунный свет', 'lullaby-dream.wav': 'Тихий сон' };
      title.textContent = titles[sound.name] || sound.name.replace(/[-_.]/g, ' ');
      const badge = document.createElement('small');
      badge.className = 'lullaby-default-badge';
      badge.textContent = 'По умолчанию';
      badge.hidden = true;
      const preview = document.createElement('button');
      preview.type = 'button'; preview.className = 'button button-secondary'; preview.textContent = 'Прослушать';
      preview.addEventListener('click', async () => {
        lullabyAudio.src = sound.url;
        try { lullabyAudio.currentTime = 0; await lullabyAudio.play(); }
        catch { showToast('Не удалось воспроизвести аудиофайл.'); }
      });
      const makeDefault = document.createElement('button');
      makeDefault.type = 'button'; makeDefault.className = 'button button-primary'; makeDefault.textContent = 'Выбрать по умолчанию';
      makeDefault.addEventListener('click', async () => {
        try {
          const saved = await fetch('/api/sounds', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file: sound.name }) });
          const result = await saved.json();
          if (!saved.ok || !result.saved) throw new Error(result.error || 'Не удалось сохранить мелодию');
          setDefaultLullaby(sound.name);
          showToast('Мелодия сохранена по умолчанию.');
        } catch (error) { showToast(error.message || 'Не удалось сохранить мелодию.'); }
      });
      card.append(title, badge, preview, makeDefault);
      list.append(card);
    });
    defaultLullaby = data.default || lullabyChoices[0].name;
    setDefaultLullaby(defaultLullaby);
  } catch (error) {
    list.innerHTML = '';
    const message = document.createElement('div');
    message.className = 'empty-state'; message.textContent = error.message || 'Не удалось загрузить аудиофайлы.';
    list.append(message);
  }
}

lullabyAudio?.addEventListener('ended', () => {
  stopPreview();
  const button = $('.control-tile[data-action="lullaby"]');
  if (button) setControlState(button, false);
});

$('#securityNotificationsBtn')?.addEventListener('click', event => {
  const button = event.currentTarget;
  button.setAttribute('aria-checked', String(button.getAttribute('aria-checked') !== 'true'));
});

async function loadPinStatus() {
  try {
    const response = await fetch('/api/pin/status', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'PIN-хранилище недоступно');
    $('#currentPinField').hidden = !data.configured;
    setFormStatus('#pinSaveStatus', data.configured ? 'PIN настроен. Для замены укажите текущий код.' : 'Задайте PIN из 4–8 цифр для блокировки панели.');
  } catch (error) {
    setFormStatus('#pinSaveStatus', error.message || 'Папка безопасности недоступна.', true);
  }
}

$('#pinForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const pin = $('#newPin').value;
  if (pin !== $('#confirmPin').value) {
    setFormStatus('#pinSaveStatus', 'PIN-коды не совпадают.', true);
    return;
  }
  try {
    const response = await fetch('/api/pin/set', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin, current_pin: $('#currentPin').value }) });
    const data = await response.json();
    if (!response.ok || !data.saved) throw new Error(data.error || 'Не удалось сохранить PIN');
    $('#pinForm').reset();
    await loadPinStatus();
    showToast('PIN-код сохранён.');
  } catch (error) { setFormStatus('#pinSaveStatus', error.message || 'Не удалось сохранить PIN.', true); }
});

const lockScreen = $('#lockScreen');
$('#lockBtn')?.addEventListener('click', async () => {
  try {
    const response = await fetch('/api/pin/status', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.configured) {
      showToast(data.error || 'Сначала задайте PIN в Настройках.');
      setView('settings'); setSettingsPane('pin'); await loadPinStatus();
      return;
    }
    lockScreen.hidden = false;
    document.body.dataset.locked = 'true';
    $('#unlockPin').value = '';
    $('#unlockStatus').textContent = '';
    $('#unlockPin').focus();
  } catch { showToast('PIN-хранилище недоступно на устройстве.'); }
});

$('#unlockForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const response = await fetch('/api/pin/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: $('#unlockPin').value }) });
    const data = await response.json();
    if (!response.ok || !data.unlocked) throw new Error(data.error || 'PIN-код не подошёл');
    lockScreen.hidden = true;
    document.body.dataset.locked = 'false';
    $('#unlockPin').value = '';
  } catch (error) {
    $('#unlockStatus').textContent = error.message || 'PIN-код не подошёл.';
    $('#unlockPin').value = '';
    $('#unlockPin').focus();
  }
});

$$('.pin-pad [data-pin-digit]').forEach(button => button.addEventListener('click', () => {
  const input = $('#unlockPin');
  if (input.value.length < 8) input.value += button.dataset.pinDigit;
}));
$$('.pin-pad [data-pin-action="clear"]').forEach(button => button.addEventListener('click', () => { $('#unlockPin').value = ''; }));
$$('.pin-pad [data-pin-action="backspace"]').forEach(button => button.addEventListener('click', () => { $('#unlockPin').value = $('#unlockPin').value.slice(0, -1); }));

loadLullabyChoices();
loadProfile();
loadPinStatus();
