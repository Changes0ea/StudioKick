"""iPhone'daki KickCam uygulamasından görüntü alır ve sanal webcam'e basar.

Protokol: TCP, her kare = 4 bayt big-endian uzunluk + JPEG verisi (iPhone -> PC).
Ters yönde (PC -> iPhone) aynı bağlantıdan 4 bayt uzunluk + JSON gönderilir
(sohbet mesajları: {"type": "chat"|"event"|"sys", ...}).
Sanal kamera: pyvirtualcam (Windows'ta OBS Virtual Camera sürücüsünü kullanır;
OBS Studio'nun kurulu olması yeterli, OBS'in açık olması gerekmez). Kamera sabit
çözünürlükte ve sürekli açıktır; bkz. VirtualCam.
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


class VirtualCam:
    """Sabit çözünürlükte sürekli kare basan sanal kamera.

    NVIDIA Broadcast, Zoom gibi uygulamalar kamerayı seçtikleri an görüntü bekler; kamera
    yoksa ya da çözünürlüğü değişirse seçimi geri alırlar. Bu yüzden kamera uygulama açılır
    açılmaz başlar, iPhone bağlı değilken bekleme ekranı gösterir ve hiç kapanmaz.
    """

    def __init__(self, width, height, fps, placeholder, on_status):
        self.width, self.height, self.fps = width, height, fps
        self.placeholder = cv2.resize(placeholder, (width, height))
        self.on_status = on_status
        self._latest = None
        self._latest_at = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.device = None
        self.running = False

    def start(self):
        if pyvirtualcam is None:
            self.on_status("Sanal kamera modülü (pyvirtualcam) yüklü değil")
            return False
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def stop(self):
        self._stop.set()

    def submit(self, frame):
        """iPhone'dan gelen kareyi sabit boyuta oturt (siyah kenarlı, oran korunur)."""
        h, w = frame.shape[:2]
        if (w, h) != (self.width, self.height):
            scale = min(self.width / w, self.height / h)
            nw, nh = int(w * scale), int(h * scale)
            canvas = np.zeros((self.height, self.width, 3), np.uint8)
            x, y = (self.width - nw) // 2, (self.height - nh) // 2
            canvas[y:y + nh, x:x + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
            frame = canvas
        with self._lock:
            self._latest, self._latest_at = frame, time.time()

    def _run(self):
        try:
            cam = pyvirtualcam.Camera(width=self.width, height=self.height, fps=self.fps,
                                      fmt=pyvirtualcam.PixelFormat.BGR)
        except Exception as e:
            self.on_status(f"Sanal kamera açılamadı: {e} — OBS Studio kurulu mu, OBS'in kendi "
                           "sanal kamerası açık mı?")
            return
        self.device, self.running = cam.device, True
        self.on_status(f"Sanal kamera hazır: {cam.device} ({self.width}x{self.height}, {self.fps} FPS)")
        try:
            while not self._stop.is_set():
                with self._lock:
                    fresh = self._latest is not None and time.time() - self._latest_at < 1.5
                    frame = self._latest if fresh else self.placeholder
                cam.send(frame)
                cam.sleep_until_next_frame()
        finally:
            cam.close()
            self.running = False
            self.on_status("Sanal kamera kapatıldı")


class CameraReceiver:
    def __init__(self, host, port, on_frame, on_status, on_state=None, history=None):
        self.on_state = on_state or (lambda s: None)
        self._sock = None
        self._send_lock = threading.Lock()
        self._history = deque(history or [], maxlen=40)   # bağlanınca telefona gönderilecek son mesajlar
        self.host, self.port = host, port
        self.on_frame = on_frame          # on_frame(bgr ndarray)
        self.on_status = on_status
        self._stop = threading.Event()
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
        self.on_state("stopped")
        self.on_status("Kamera durduruldu")
