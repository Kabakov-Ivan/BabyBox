const toast = document.getElementById('toast');

function showToast(text){
  toast.textContent = text;
  toast.classList.add('show');
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(()=>toast.classList.remove('show'),1800);
}

document.querySelectorAll('.nav-item').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
    btn.classList.add('active');
    showToast(btn.textContent.trim());
  });
});

document.querySelectorAll('.control-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    btn.classList.toggle('active');
    showToast(btn.dataset.action + (btn.classList.contains('active') ? ' включено' : ' выключено'));
  });
});

document.getElementById('recordBtn').addEventListener('click', e=>{
  const recording = e.currentTarget.dataset.recording === '1';
  e.currentTarget.dataset.recording = recording ? '0' : '1';
  e.currentTarget.textContent = recording ? '▣  Начать запись' : '●  Идёт запись';
  showToast(recording ? 'Запись остановлена' : 'Запись начата');
});

document.getElementById('micBtn').addEventListener('click', e=>{
  e.currentTarget.classList.toggle('active');
  showToast(e.currentTarget.classList.contains('active') ? 'Микрофон включён' : 'Микрофон выключен');
});

document.getElementById('themeBtn').addEventListener('click',()=>showToast('Ночной режим интерфейса'));

function updateClock(){
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
  document.getElementById('date').textContent =
    now.toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'});
}
updateClock();
setInterval(updateClock,1000);

document.querySelector('.volume input').addEventListener('input', e=>{
  e.target.parentElement.querySelector('b').textContent = e.target.value + '%';
});
