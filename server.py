#!/usr/bin/env python3
"""Startpage server: serves startpage.html plus the live stats and music controls it shows.

Runs the same way everywhere:
  Windows (double-click startpage.pyw or this file): tray icon, now-playing + media
      controls, stats. Open http://localhost:8787
  Docker / NAS: stats only (a container can't see a desktop's media session).

Endpoints (one port, default 8787):
  /            the start page
  /stats       CPU / RAM (psutil) and GPU (nvidia-smi, NVIDIA only)
  /media       now playing: title, artist, album art (Windows)
  /media/<cmd> POST prev | play_pause | next
  /spectrum    live audio bands for the music visualizer (Windows: loopback capture of
               whatever your speakers are playing; installs numpy + PyAudioWPatch on first use)

Settings come from environment variables or an optional config.json next to this file:
  host         address to listen on (default 127.0.0.1; the Docker image sets 0.0.0.0)
  port         default 8787
  open_url     address the tray menu opens instead of http://localhost:<port> (e.g. http://tyke.start)
  cors_origin  a page address allowed to use this server from another host, e.g.
               "http://192.168.1.50:8787" (needed when the page is on a NAS but the
               music helper runs on your desktop; set host to 0.0.0.0 there too)
Problems are written to stats_server.log next to this file.
"""
import asyncio
import base64
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "startpage.html")
WIN = sys.platform == "win32"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # hides console flashes on Windows
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0)


def _config():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_cfg = _config()
HOST = os.environ.get("HOST") or _cfg.get("host") or "127.0.0.1"
PORT = int(os.environ.get("PORT") or _cfg.get("port") or 8787)
CORS_ORIGIN = (os.environ.get("CORS_ORIGIN") or _cfg.get("cors_origin") or "").rstrip("/")
# address the tray menu opens (e.g. "http://tyke.start" once that name points at this machine); default localhost
OPEN_URL = (os.environ.get("OPEN_URL") or _cfg.get("open_url") or "").rstrip("/")


def _relaunch_hidden():
    """If running under python.exe on Windows, restart under pythonw.exe and exit."""
    if not WIN:
        return
    exe = sys.executable
    if not exe.lower().endswith("python.exe"):
        return
    pyw = exe[:-len("python.exe")] + "pythonw.exe"
    if os.path.exists(pyw):
        subprocess.Popen([pyw, os.path.abspath(__file__)], creationflags=DETACHED | NO_WINDOW,
                         close_fds=True)
        sys.exit(0)


_relaunch_hidden()

ICON_B64 = "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"


# ---------- dependency auto-install (Windows double-click convenience) ----------
def log_error():
    try:
        import traceback
        with open(os.path.join(HERE, "stats_server.log"), "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
    except Exception:
        pass


def ensure(module, pip_name=None):
    try:
        return __import__(module)
    except ImportError:
        pass
    if not (WIN or os.environ.get("AUTO_INSTALL")):
        return None  # in Docker the packages come from requirements.txt
    pkgs = pip_name if isinstance(pip_name, list) else [pip_name or module]
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *pkgs],
            creationflags=NO_WINDOW,
        )
        return __import__(module)
    except Exception:
        return None


psutil = ensure("psutil")
PIL_Image = None
pystray = None
if WIN:
    if ensure("PIL", "pillow"):
        from PIL import Image as PIL_Image
        pystray = ensure("pystray")


# ---------- stats ----------
_stats = {"cpu": None, "ram": None, "gpu": None}


def gpu():
    if not shutil.which("nvidia-smi"):
        return None
    try:
        q = "name,utilization.gpu,memory.used,memory.total,temperature.gpu"
        out = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"],
            text=True, timeout=2, creationflags=NO_WINDOW,
        ).splitlines()[0]
        name, util, mem_used, mem_total, temp = [x.strip() for x in out.split(",")]
        return {
            "name": name,
            "util": float(util),
            "mem_used": float(mem_used),
            "mem_total": float(mem_total),
            "temp": float(temp),
        }
    except Exception:
        return None


def sampler():
    """Refresh the numbers every ~2s so requests never block and many tabs share one sample."""
    while True:
        try:
            if psutil:
                _stats["cpu"] = psutil.cpu_percent(interval=1)
                _stats["ram"] = psutil.virtual_memory().percent
            _stats["gpu"] = gpu()
        except Exception:
            pass
        time.sleep(1)


# ---------- media (Windows "now playing" + controls) ----------
WINRT_PKGS = [
    "winrt-runtime",
    "winrt-Windows.Foundation",
    "winrt-Windows.Foundation.Collections",
    "winrt-Windows.Storage.Streams",
    "winrt-Windows.Media.Control",
]
_W = {}
_loop = None
_art = {"key": None, "data": None, "id": None}


def _media_thread():
    """Own thread + event loop for the async Windows media API."""
    global _loop
    try:
        ensure("winrt.windows.media.control", WINRT_PKGS)
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )
        from winrt.windows.storage.streams import DataReader
    except Exception:
        log_error()
        return
    _W["Manager"], _W["DataReader"] = Manager, DataReader
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop = loop
    loop.run_forever()


async def _session():
    if "mgr" not in _W:
        _W["mgr"] = await _W["Manager"].request_async()
    return _W["mgr"].get_current_session()


async def _read_thumb(ref):
    try:
        stream = await ref.open_read_async()
        size = int(stream.size)
        if not size:
            return None
        reader = _W["DataReader"](stream)
        await reader.load_async(size)
        buf = bytearray(size)
        reader.read_bytes(buf)
        return bytes(buf)
    except Exception:
        return None


async def _now_playing():
    s = await _session()
    if not s:
        return {"supported": True, "active": False}
    p = await s.try_get_media_properties_async()
    info = s.get_playback_info()
    out = {
        "supported": True,
        "active": True,
        "title": p.title or "",
        "artist": p.artist or "",
        "album": p.album_title or "",
        "playing": int(info.playback_status) == 4,
        "art": None,
    }
    try:
        t = s.get_timeline_properties()
        out["pos"] = t.position.total_seconds()
        out["dur"] = (t.end_time - t.start_time).total_seconds()
    except Exception:
        pass
    key = f"{out['title']}|{out['artist']}|{out['album']}"
    if p.thumbnail and (_art["key"] != key or not _art["data"]):
        _art["key"] = key
        _art["data"] = await _read_thumb(p.thumbnail)
        _art["id"] = hashlib.md5(key.encode("utf-8", "replace")).hexdigest()[:10]
    if p.thumbnail and _art["key"] == key and _art["data"]:
        out["art"] = "/media/art?k=" + _art["id"]
    return out


async def _control(cmd):
    s = await _session()
    if not s:
        return False
    fn = {
        "play_pause": s.try_toggle_play_pause_async,
        "next": s.try_skip_next_async,
        "prev": s.try_skip_previous_async,
    }[cmd]
    return bool(await fn())


def _run_media(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=4)


def _media_key(cmd):
    import ctypes
    vk = {"prev": 0xB1, "play_pause": 0xB3, "next": 0xB0}[cmd]
    u = ctypes.windll.user32
    u.keybd_event(vk, 0, 0, 0)
    u.keybd_event(vk, 0, 2, 0)


def media_info():
    if not WIN:
        return {"supported": False, "active": False}
    if _loop is None:
        return {"supported": False, "active": False, "starting": True}
    try:
        return _run_media(_now_playing())
    except Exception:
        return {"supported": True, "active": False}


def media_command(cmd):
    if cmd not in ("prev", "play_pause", "next"):
        return False
    if _loop is not None:
        try:
            if _run_media(_control(cmd)):
                return True
        except Exception:
            pass
    if WIN:  # fallback: simulate the keyboard media keys
        _media_key(cmd)
        return True
    return False


# ---------- audio spectrum (Windows) ----------
# Feeds the visualizer on the music panel. Starts the first time the page asks for it.
NB = 28
_aud = {"state": "off", "bands": [0.0] * NB, "t": 0.0}


def _audio_thread():
    try:
        np = ensure("numpy")
        pa = ensure("pyaudiowpatch", "PyAudioWPatch")
        if not (WIN and np and pa):
            _aud["state"] = "fail"
            return
        p = pa.PyAudio()
        api = p.get_host_api_info_by_type(pa.paWASAPI)
        dev = p.get_device_info_by_index(api["defaultOutputDevice"])
        if not dev.get("isLoopbackDevice"):
            for lb in p.get_loopback_device_info_generator():
                if dev["name"] in lb["name"]:
                    dev = lb
                    break
        rate, ch = int(dev["defaultSampleRate"]), int(dev["maxInputChannels"])
        edges = np.geomspace(40, 14000, NB + 1)

        def on_audio(data, frames, tinfo, status):
            try:
                a = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                if ch > 1:
                    a = a[: len(a) // ch * ch].reshape(-1, ch).mean(axis=1)
                n = len(a)
                if n < 256:
                    return (None, pa.paContinue)
                mag = np.abs(np.fft.rfft(a * np.hanning(n))) / (n / 4.0)
                df = rate / float(n)
                out = []
                for i in range(NB):
                    lo = int(edges[i] / df)
                    hi = max(lo + 1, int(edges[i + 1] / df))
                    v = float(mag[lo:hi].max()) if lo < len(mag) else 0.0
                    db = 20.0 * np.log10(v + 1e-6) + i * 0.7  # tilt up the highs a little
                    out.append(float(min(1.0, max(0.0, (db + 70.0) / 60.0))))
                _aud["bands"], _aud["t"] = out, time.time()
            except Exception:
                pass
            return (None, pa.paContinue)

        stream = p.open(format=pa.paInt16, channels=ch, rate=rate, input=True,
                        frames_per_buffer=2048, input_device_index=dev["index"],
                        stream_callback=on_audio)
        stream.start_stream()
        _aud["state"] = "ok"
        while stream.is_active():
            time.sleep(1)
        _aud["state"] = "fail"
    except Exception:
        _aud["state"] = "fail"
        log_error()


def spectrum_info():
    if _aud["state"] == "off":
        _aud["state"] = "starting"
        threading.Thread(target=_audio_thread, daemon=True).start()
    # The loopback stream sends nothing while the PC is silent, so stale data means silence.
    live = time.time() - _aud["t"] < 0.3
    return {"ok": _aud["state"] == "ok", "starting": _aud["state"] == "starting",
            "bands": _aud["bands"] if live else [0.0] * NB}


# ---------- http ----------
class Handler(BaseHTTPRequestHandler):
    def _origin_allowed(self):
        """Browsers send Origin on cross-site requests. Accept our own page and cors_origin only,
        so a random website can't poke the media buttons."""
        o = (self.headers.get("Origin") or "").rstrip("/")
        return not o or urlparse(o).netloc == self.headers.get("Host") or o == CORS_ORIGIN

    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        o = (self.headers.get("Origin") or "").rstrip("/")
        if CORS_ORIGIN and o == CORS_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(b"")

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/index.html", "/startpage.html"):
            try:
                with open(PAGE, "rb") as f:
                    self._send(f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(b"startpage.html not found", "text/plain", 404)
        elif path == "/stats":
            self._send(json.dumps(_stats).encode())
        elif path == "/media":
            self._send(json.dumps(media_info()).encode())
        elif path == "/spectrum":
            self._send(json.dumps(spectrum_info()).encode())
        elif path == "/media/art":
            data = _art["data"]
            if not data:
                self._send(b"", code=404)
                return
            self._send(data, "image/png" if data[:4] == b"\x89PNG" else "image/jpeg")
        else:
            self._send(b"not found", "text/plain", 404)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if not self._origin_allowed():
            self._send(b"{}", code=403)
        elif path.startswith("/media/"):
            self._send(json.dumps({"ok": media_command(path.split("/")[-1])}).encode())
        else:
            self._send(b"{}", code=404)

    def log_message(self, *args):
        pass


# ---------- tray (Windows) ----------
def load_icon():
    return PIL_Image.open(io.BytesIO(base64.b64decode(ICON_B64)))


def _run_key():
    import winreg
    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_ALL_ACCESS,
    )


def startup_enabled():
    if not WIN:
        return False
    import winreg
    try:
        with _run_key() as k:
            winreg.QueryValueEx(k, "StartpageStats")
            return True
    except OSError:
        return False


def toggle_startup():
    import winreg
    with _run_key() as k:
        if startup_enabled():
            winreg.DeleteValue(k, "StartpageStats")
        else:
            exe = sys.executable
            pyw = exe.lower().replace("python.exe", "pythonw.exe")
            if os.path.exists(pyw):
                exe = pyw
            script = os.path.abspath(__file__)
            winreg.SetValueEx(k, "StartpageStats", 0, winreg.REG_SZ, f'"{exe}" "{script}"')


def run_tray():
    base = OPEN_URL or f"http://localhost:{PORT}"

    def open_page(icon=None, item=None):
        webbrowser.open(base + "/")

    def open_stats(icon=None, item=None):
        webbrowser.open(base + "/stats")

    def on_startup(icon, item):
        toggle_startup()

    def quit_app(icon, item):
        icon.stop()

    def cmd(name):
        return lambda icon, item: media_command(name)

    items = [
        pystray.MenuItem("Previous track", cmd("prev")),
        pystray.MenuItem("Play / pause", cmd("play_pause")),
        pystray.MenuItem("Next track", cmd("next")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open start page", open_page, default=True),
        pystray.MenuItem("View raw stats", open_stats),
        pystray.MenuItem("Start with Windows", on_startup, checked=lambda i: startup_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    ]
    icon = pystray.Icon("startpage-stats", load_icon(), "Startpage stats", pystray.Menu(*items))

    def update_tooltip():
        while True:
            cpu, ram = _stats["cpu"], _stats["ram"]
            if cpu is not None and ram is not None:
                icon.title = f"Startpage stats  |  CPU {cpu:.0f}%  RAM {ram:.0f}%"
            time.sleep(3)

    threading.Thread(target=update_tooltip, daemon=True).start()
    icon.run()


def main():
    try:
        srv = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        log_error()
        print(f"could not listen on {HOST}:{PORT} (already running?)", file=sys.stderr, flush=True)
        sys.exit(1)
    srv.daemon_threads = True
    server = threading.Thread(target=srv.serve_forever, daemon=True)
    server.start()
    threading.Thread(target=sampler, daemon=True).start()
    if WIN:
        threading.Thread(target=_media_thread, daemon=True).start()
    print(f"startpage on http://{HOST}:{PORT}", flush=True)

    if pystray:
        try:
            run_tray()  # blocks until Quit
            return
        except Exception:
            log_error()
    # No tray (Docker, Linux, or tray unavailable): run until told to stop.
    stop = lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)  # lets `docker stop` end immediately
    while server.is_alive():
        server.join(1)


if __name__ == "__main__":
    main()
