<p align="center">
      <img src="https://i.ibb.co/8LLq7MYr/big-Logo-Dark.png" alt="Project Logo" width="726">
</p>

<p align="center">
      <img src="https://img.shields.io/badge/Language-python-green" alt="tyy">
      <img src="https://img.shields.io/badge/Created-2026-blueviolet" alt="Unity Version">
      <img src="https://img.shields.io/badge/Version-1.0.0-blue" alt="Game Version">
      <img src="https://img.shields.io/badge/License-MIT-orange" alt="License">
</p>

## О сервисе

Это система «Радионяня» для дистанционного наблюдения за ребёнком. Система позволяет в реальном времени контролировать температуру, влажность и уровень качества воздуха, просматривать видео и управлять дополнительными функциями устройства через веб-панель. Также предусмотрены автоматическое включение ночника, воспроизведение колыбельных, запись видео и данных с датчиков, ведение архивов и отправка уведомлений при возникновении тревожных ситуаций.

## Что уже реализованно:
```
BabyBox/
│
├── README.md
├── LICENSE
├── .gitignore
│
└── monitor/                          ← всё приложение
    │
    ├── app/                          ← весь Python-код
    │   ├── main.py                   ← сервер, API
    │   ├── camera_stream.py          ← поток с камеры
    │   └── dht_sensor.py             ← DHT-11 (темп / влажность)
    │
    ├── requirements.txt              ← Python-зависимости
    │
    ├── templates/                    ← HTML-страницы
    │   ├── index.html                ← главная (монитор)
    │   └── wifi_setup.html           ← настройка Wi‑Fi
    │
    ├── static/                       ← фронтенд
    │   ├── style.css                 ← дизайн
    │   └── script.js                 ← интерактивность
    │
    ├── scripts/                      ← системные скрипты
    │   ├── babybox-wifi
    │   ├── babybox-boot-wifi
    │   └── install-autostart.sh      ← автозапуск
    │
    └── systemd/                      ← сервисы Linux
        ├── babybox-web.service
        └── babybox-boot-wifi.service
```
## Разработчик

[Кабаков Иван](https://github.com/Kabakov-Ivan)

[Кирилл Краснов](https://github.com/KirillKrasnov)

[Степан Никишев](https://github.com/Stepan-Nikishev)

[Максим Черемисов](https://github.com/Kabakov-Ivan)

## Лицензия

Проект BabyBox распространяется под лицензией MIT.
