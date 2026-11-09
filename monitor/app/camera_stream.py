"""CSI / ribbon-cable camera → MJPEG frames for the web panel."""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Generator, Optional

log = logging.getLogger(__name__)

BOUNDARY = b"frame"


class StreamingOutput(io.BufferedIOBase):
    """Latest JPEG frame shared between the encoder and HTTP clients."""

    def __init__(self) -> None:
        self.frame: Optional[bytes] = None
        self.seq = 0
        self.condition = threading.Condition()

    def write(self, buf: bytes) -> int:  # type: ignore[override]
        # Copy: picamera2 reuses the encoder buffer between frames.
        data = bytes(buf)
        with self.condition:
            self.frame = data
            self.seq += 1
            self.condition.notify_all()
        return len(data)


class CameraStream:
    """Lazy Picamera2 (libcamera) capture for Raspberry Pi CSI cameras."""

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        fps: int = 15,
        quality: int = 75,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality
        self._lock = threading.Lock()
        self._picam2 = None
        self._output: Optional[StreamingOutput] = None
        self._started = False
        self._error: Optional[str] = None
        self._recording = False
        self._record_stop = threading.Event()
        self._record_thread: Optional[threading.Thread] = None
        self._record_path: Optional[Path] = None
        self._record_error: Optional[str] = None
        self._record_started_at: Optional[float] = None

    @property
    def available(self) -> bool:
        return self._started and self._error is None

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def recording(self) -> bool:
        return self._recording

    def status(self) -> dict:
        return {
            "available": self.available,
            "started": self._started,
            "error": self._error,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "stream_url": "/stream",
            "stream_type": "mjpeg",
            "recording": self._recording,
            "record_error": self._record_error,
        }

    def start(self) -> bool:
        with self._lock:
            if self._started and self._error is None:
                return True
            if self._started and self._error:
                self._stop_unlocked()

            try:
                from picamera2 import Picamera2
                from picamera2.encoders import JpegEncoder
                from picamera2.outputs import FileOutput
            except ImportError as exc:
                self._error = (
                    "picamera2 не установлен. На Raspberry Pi: "
                    "sudo apt install -y python3-picamera2 "
                    "и пересоздайте venv с --system-site-packages."
                )
                log.error("%s (%s)", self._error, exc)
                return False

            try:
                picam2 = Picamera2()
                config = picam2.create_video_configuration(
                    main={"size": (self.width, self.height)},
                    controls={"FrameRate": float(self.fps)},
                )
                picam2.configure(config)
                output = StreamingOutput()
                encoder = JpegEncoder(q=self.quality)
                picam2.start_recording(encoder, FileOutput(output))
                self._picam2 = picam2
                self._output = output
                self._started = True
                self._error = None
                log.info(
                    "Camera started %sx%s @ %s fps",
                    self.width,
                    self.height,
                    self.fps,
                )
                return True
            except Exception as exc:
                self._error = f"Не удалось открыть камеру: {exc}"
                log.exception("Camera start failed")
                self._stop_unlocked()
                return False

    def _stop_unlocked(self) -> None:
        if self._recording:
            self._record_stop.set()
            thread = self._record_thread
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=5)
            self._recording = False
            self._record_thread = None
        if self._picam2 is not None:
            try:
                self._picam2.stop_recording()
            except Exception:
                pass
            try:
                self._picam2.close()
            except Exception:
                pass
        self._picam2 = None
        self._output = None
        self._started = False

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def wait_frame(self, timeout: float = 2.0) -> Optional[bytes]:
        if not self.start() or self._output is None:
            return None
        with self._output.condition:
            ok = self._output.condition.wait(timeout=timeout)
            if not ok and self._output.frame is None:
                return None
            return self._output.frame

    def capture_jpeg(self, timeout: float = 2.0) -> Optional[bytes]:
        """Return one fresh JPEG from the live stream."""
        frame = self.wait_frame(timeout=timeout)
        if frame:
            return frame
        if self._output and self._output.frame:
            return self._output.frame
        return None

    def start_clip(self, path: Path) -> tuple[bool, str]:
        """Record live JPEG frames into a video file (stream keeps running)."""
        if self._recording:
            return False, "Запись уже идёт"
        if not self.start() or self._output is None:
            return False, self._error or "Камера недоступна"

        path.parent.mkdir(parents=True, exist_ok=True)
        self._record_stop.clear()
        self._record_error = None
        self._record_path = path
        self._record_started_at = time.monotonic()
        self._recording = True
        self._record_thread = threading.Thread(
            target=self._record_loop,
            args=(path,),
            daemon=True,
            name="babybox-record",
        )
        self._record_thread.start()
        return True, "Запись началась"

    def stop_clip(self) -> tuple[bool, Optional[Path], str]:
        if not self._recording and not (
            self._record_thread and self._record_thread.is_alive()
        ):
            # Thread may have just finished finalizing — still collect the file.
            if self._record_path and self._record_path.exists() and not self._record_error:
                path = self._record_path
                self._record_path = None
                return True, path, "Запись сохранена"
            return False, None, self._record_error or "Запись не активна"

        self._record_stop.set()
        thread = self._record_thread
        if thread and thread.is_alive():
            thread.join(timeout=45)
        path = self._record_path
        error = self._record_error
        self._recording = False
        self._record_thread = None
        self._record_path = None
        self._record_started_at = None
        if error:
            if path and path.exists():
                path.unlink(missing_ok=True)
            return False, None, error
        if path is None or not path.exists() or path.stat().st_size < 256:
            if path and path.exists():
                path.unlink(missing_ok=True)
            return False, None, "Файл записи пустой или повреждён"
        return True, path, "Запись сохранена"

    def _next_frame(self, output: StreamingOutput, last_seq: int, timeout: float = 1.0):
        with output.condition:
            if output.seq == last_seq:
                output.condition.wait(timeout=timeout)
            if output.seq == last_seq or output.frame is None:
                return last_seq, None
            return output.seq, output.frame

    def _encode_mjpeg_file(self, src: Path, dest: Path) -> tuple[bool, str]:
        """Turn a raw MJPEG bitstream into a browser-playable file."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            # Keep raw MJPEG if ffmpeg is missing — still openable by some players.
            try:
                src.replace(dest.with_suffix(".mjpeg"))
                self._record_path = dest.with_suffix(".mjpeg")
                return True, ""
            except Exception as exc:
                return False, f"ffmpeg не найден и не удалось сохранить MJPEG: {exc}"

        attempts = [
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "mjpeg", "-framerate", str(self.fps), "-i", str(src),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(dest),
            ],
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "mjpeg", "-framerate", str(self.fps), "-i", str(src),
                "-c:v", "mpeg4", "-q:v", "5", str(dest),
            ],
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "mjpeg", "-framerate", str(self.fps), "-i", str(src),
                "-c:v", "copy", str(dest.with_suffix(".avi")),
            ],
        ]
        errors: list[str] = []
        for cmd in attempts:
            out = Path(cmd[-1])
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except Exception as exc:
                errors.append(str(exc))
                continue
            if result.returncode == 0 and out.exists() and out.stat().st_size > 256:
                if out != dest:
                    self._record_path = out
                return True, ""
            detail = (result.stderr or result.stdout or "").strip()
            errors.append(detail or f"ffmpeg code {result.returncode}")
            out.unlink(missing_ok=True)

        return False, errors[-1] if errors else "Не удалось закодировать видео"

    def _record_loop(self, path: Path) -> None:
        assert self._output is not None
        output = self._output
        raw_path = path.with_suffix(".mjpeg.part")
        frames = 0
        last_seq = output.seq

        try:
            with raw_path.open("wb") as raw:
                while not self._record_stop.is_set():
                    last_seq, frame = self._next_frame(output, last_seq, timeout=0.5)
                    if frame is None:
                        continue
                    raw.write(frame)
                    frames += 1
                # Grab one last frame after stop, if a newer one arrived.
                last_seq, frame = self._next_frame(output, last_seq, timeout=0.05)
                if frame is not None:
                    raw.write(frame)
                    frames += 1

            if frames == 0:
                self._record_error = "Пока шла запись кадров не было"
                raw_path.unlink(missing_ok=True)
                return

            ok, detail = self._encode_mjpeg_file(raw_path, path)
            if not ok:
                self._record_error = detail
                path.unlink(missing_ok=True)
        except Exception as exc:
            log.exception("Recording failed")
            self._record_error = f"Ошибка записи: {exc}"
            path.unlink(missing_ok=True)
        finally:
            raw_path.unlink(missing_ok=True)
            self._recording = False

    def mjpeg_generator(self) -> Generator[bytes, None, None]:
        if not self.start() or self._output is None:
            message = (self._error or "Камера недоступна").encode("utf-8")
            yield (
                b"--" + BOUNDARY + b"\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
                + message
                + b"\r\n"
            )
            return

        output = self._output
        last_frame: Optional[bytes] = None
        idle_since = time.monotonic()

        while True:
            with output.condition:
                notified = output.condition.wait(timeout=1.0)
                frame = output.frame

            if frame is None:
                if time.monotonic() - idle_since > 5:
                    self._error = "Камера не отдаёт кадры"
                    break
                continue

            idle_since = time.monotonic()
            if frame is last_frame and not notified:
                continue
            last_frame = frame
            yield (
                b"--" + BOUNDARY + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                + frame
                + b"\r\n"
            )


camera = CameraStream()
