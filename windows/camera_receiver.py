"""iPhone'daki KickCam uygulamasından görüntü alır ve sanal webcam'e basar.

Protokol: TCP, her kare = 4 bayt big-endian uzunluk + JPEG verisi (iPhone -> PC).
Ters yönde (PC -> iPhone) aynı bağlantıdan 4 bayt uzunluk + JSON gönderilir
(sohbet mesajları: {"type": "chat"|"event"|"sys", ...}).
Sanal kamera: pyvirtualcam (Windows'ta OBS Virtual Camera sürücüsünü kullanır;
OBS Studio'nun kurulu olması yeterli, OBS'in açık olması gerekmez).
"""
import json
import socket
import struct
import threading
import time
from collections import deque

import cv2
import numpy as np

try:
    import pyvirtualcam
except ImportError:  # sanal kamera opsiyonel
    pyvirtualcam = None

try:
    from zeroconf import ServiceBrowser, Zeroconf
except ImportError:
    Zeroconf = None

SERVICE_TYPE = "_kickcam._tcp.local."
DEFAULT_PORT = 5050


class Discovery:
    """Yerel ağdaki iPhone'ları Bonjour ile bulur."""

    def __init__(self, on_found):
        self.on_found = on_found
        self.zc = None

    def start(self):
        if Zeroconf is None:
            return False
        self.zc = Zeroconf()
        ServiceBrowser(self.zc, SERVICE_TYPE, self)
        return True

    def stop(self):
        if self.zc:
            self.zc.close()

    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        if info and info.parsed_addresses():
            self.on_found(name.replace("." + SERVICE_TYPE, ""),
                          info.parsed_addresses()[0], info.port)

    def update_service(self, *a):
        pass

    def remove_service(self, *a):
        pass


class CameraReceiver:
    def __init__(self, host, port, on_frame, on_status, virtual_cam=True, fps=30, on_state=None,
                 history=None):
        self.on_state = on_state or (lambda s: None)
        self._sock = None
        self._send_lock = threading.Lock()
        self._history = deque(history or [], maxlen=40)   # bağlanınca telefona gönderilecek son mesajlar
        self.host, self.port = host, port
        self.on_frame = on_frame          # on_frame(bgr ndarray)
        self.on_status = on_status
        self.virtual_cam = virtual_cam and pyvirtualcam is not None
        self.fps = fps
        self._stop = threading.Event()
        self._cam = None
        self.stats_fps = 0.0

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()

    def send_json(self, obj):
        """Telefona mesaj gönder (her thread'den çağrılabilir). Bağlı değilse geçmişe ekler."""
        self._history.append(obj)
        self._write(obj)

    def _write(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        packet = struct.pack(">I", len(data)) + data
        with self._send_lock:
            sock = self._sock
            if not sock:
                return
            try:
                sock.sendall(packet)
            except OSError:
                pass   # okuma döngüsü kopmayı fark edip yeniden bağlanır

    def _recv_exact(self, sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Bağlantı kapandı")
            buf.extend(chunk)
        return bytes(buf)

    def _ensure_cam(self, w, h):
        if not self.virtual_cam:
            return
        if self._cam and (self._cam.width, self._cam.height) == (w, h):
            return
        if self._cam:
            self._cam.close()
        try:
            self._cam = pyvirtualcam.Camera(width=w, height=h, fps=self.fps,
                                            fmt=pyvirtualcam.PixelFormat.BGR)
            self.on_status(f"Sanal kamera aktif: {self._cam.device} ({w}x{h})")
        except Exception as e:
            self._cam = None
            self.virtual_cam = False
            self.on_status(f"Sanal kamera açılamadı (OBS Studio kurulu mu?): {e}")

    def _run(self):
        while not self._stop.is_set():
            try:
                self.on_state("connecting")
                self.on_status(f"{self.host}:{self.port} adresine bağlanılıyor...")
                sock = socket.create_connection((self.host, self.port), timeout=5)
                sock.settimeout(5)
                with self._send_lock:
                    self._sock = sock
                for old in list(self._history):   # telefon son mesajları da görsün
                    self._write(old)
                self.on_state("connected")
                self.on_status("iPhone kamerasına bağlanıldı")
                count, t0 = 0, time.time()
                while not self._stop.is_set():
                    (length,) = struct.unpack(">I", self._recv_exact(sock, 4))
                    if length <= 0 or length > 20_000_000:
                        raise ConnectionError("Geçersiz kare")
                    jpg = self._recv_exact(sock, length)
                    frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        continue
                    h, w = frame.shape[:2]
                    self._ensure_cam(w, h)
                    if self._cam:
                        self._cam.send(frame)
                    self.on_frame(frame)
                    count += 1
                    if time.time() - t0 >= 1:
                        self.stats_fps = count / (time.time() - t0)
                        count, t0 = 0, time.time()
                sock.close()
            except Exception as e:
                with self._send_lock:
                    self._sock = None
                self.on_state("retrying")
                self.on_status(f"Kamera bağlantı hatası: {e} — 2 sn sonra tekrar denenecek")
                time.sleep(2)
        if self._cam:
            self._cam.close()
            self._cam = None
        self.on_state("stopped")
        self.on_status("Kamera durduruldu")
