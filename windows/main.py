"""ChangesStudio — Kick yayıncı paneli + iPhone sanal webcam (Windows)."""
import collections

import numpy as np
import html
import json
import os
import sys
import threading
import time

import cv2
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSpinBox, QStatusBar, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from camera_receiver import DEFAULT_PORT, CameraReceiver, Discovery, VirtualCam
from kick_api import KickAPI
from kick_chat import DEFAULT_CLUSTER, DEFAULT_KEY, LOG_PATH, KickChat, find_chatroom_id

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "KickStudio")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
TOKEN_PATH = os.path.join(APP_DIR, "tokens.json")

DEFAULT_CONFIG = {
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "http://localhost:8765/callback",
    "chatroom_id": "",
    "pusher_key": DEFAULT_KEY,
    "pusher_cluster": DEFAULT_CLUSTER,
    "camera_host": "",
    "camera_port": DEFAULT_PORT,
    "camera_fps": 30,
    "vcam_enabled": True,
    "vcam_size": "1280x720",
}

# ChangesCraft tasarım dili (paylaşılan palet)
PALETTE = {
    "night": "#050B0A", "forest": "#06503F", "navy": "#14284A", "line": "#0E5A4A",
    "blue": "#68ACFF", "sky": "#70C0FF", "ice": "#8AF2FF", "water": "#7CDEFF", "turq": "#2FE0C0",
    "text": "#D3E6FF", "lav": "#B4BFEE",
    "sub": "#B48CFF", "gold": "#FFCF3F", "kick": "#53FC18",
}
P = PALETTE
BRAND_FONT = "Segoe UI"   # main() içinde belirlenir
STYLE = f"""
QMainWindow, QWidget {{ background:{P['night']}; color:{P['text']};
  font-family:'__FONT__','Segoe UI'; font-size:13px; font-weight:500; }}
QMainWindow {{ background: qlineargradient(x1:0,y1:1,x2:1,y2:0, stop:0 {P['forest']}, stop:0.45 {P['night']}, stop:1 {P['night']}); }}
QGroupBox {{ background: rgba(20,40,74,0.38); border:1px solid rgba(104,172,255,0.18);
  border-radius:18px; margin-top:20px; padding:16px 12px 12px 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; left:16px; padding:2px 10px; color:{P['night']};
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {P['turq']}, stop:1 {P['blue']});
  border-radius:9px; font-weight:800; }}
QLabel {{ background:transparent; }}
QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {P['turq']}, stop:1 {P['blue']});
  color:{P['night']}; border:none; border-radius:17px; padding:9px 20px; font-weight:800; }}
QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {P['ice']}, stop:1 {P['sky']}); }}
QPushButton:pressed {{ padding-top:10px; padding-bottom:8px; }}
QPushButton:disabled {{ background:{P['navy']}; color:#5a6b85; }}
QPushButton#secondary {{ background:rgba(20,40,74,0.7); color:{P['text']}; border:1px solid rgba(104,172,255,0.25); }}
QPushButton#secondary:hover {{ border-color:{P['turq']}; color:{P['ice']}; }}
QLineEdit, QComboBox, QSpinBox, QListWidget, QTextBrowser {{
  background: rgba(5,11,10,0.8); border:1px solid rgba(104,172,255,0.2); border-radius:14px; padding:7px 12px;
  selection-background-color:{P['line']}; }}
QListWidget {{ padding:8px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border:1px solid {P['turq']}; }}
QComboBox::drop-down {{ border:none; width:26px; }}
QComboBox QAbstractItemView {{ background:{P['night']}; border:1px solid {P['navy']}; border-radius:10px; }}
QListWidget::item {{ padding:6px 8px; margin:2px 0; border-radius:10px; }}
QListWidget::item:hover {{ background:rgba(20,40,74,0.55); }}
QListWidget::item:selected {{ background:rgba(47,224,192,0.15); color:{P['ice']}; }}
QCheckBox {{ background:transparent; spacing:8px; }}
QCheckBox::indicator {{ width:18px; height:18px; border-radius:9px; }}
QCheckBox::indicator:checked {{ background:{P['turq']}; border:1px solid {P['turq']}; }}
QCheckBox::indicator:unchecked {{ background:{P['night']}; border:1px solid {P['navy']}; }}
QTabWidget::pane {{ border:none; background:transparent; }}
QTabBar::tab {{ background:rgba(20,40,74,0.35); color:{P['lav']}; padding:9px 22px; margin:0 6px 8px 0;
  border-radius:17px; font-weight:800; }}
QTabBar::tab:selected {{ color:{P['night']};
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {P['turq']}, stop:1 {P['blue']}); }}
QTabBar::tab:hover:!selected {{ color:{P['ice']}; background:rgba(20,40,74,0.7); }}
QStatusBar {{ background:rgba(5,11,10,0.9); color:{P['lav']}; border-top:1px solid {P['navy']}; }}
QMenu {{ background:{P['night']}; border:1px solid {P['navy']}; border-radius:12px; padding:6px; }}
QMenu::item {{ padding:6px 16px; border-radius:8px; }}
QMenu::item:selected {{ background:{P['line']}; }}
QScrollBar:vertical {{ background:transparent; width:8px; margin:4px; }}
QScrollBar::handle:vertical {{ background:{P['navy']}; border-radius:4px; min-height:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
"""


def load_brand_font():
    """Coolvetica bilgisayarda kuruluysa onu, değilse uygulamayla gelen Inter Tight'ı kullanır."""
    if "Coolvetica" in QFontDatabase.families():
        return "Coolvetica"
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for name in ("InterTight-Medium.ttf", "InterTight-Bold.ttf", "InterTight-ExtraBold.ttf"):
        QFontDatabase.addApplicationFont(os.path.join(base, "assets", "fonts", name))
    return "Inter Tight" if "Inter Tight" in QFontDatabase.families() else "Segoe UI"


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


class Bus(QObject):
    """Arka plan thread'lerinden arayüze güvenli sinyal köprüsü."""
    status = Signal(str)
    chat = Signal(dict)
    frame = Signal(object)
    channel = Signal(dict)
    error = Signal(str)
    logged_in = Signal()
    categories = Signal(list)
    camera_found = Signal(str, str, int)
    chat_sys = Signal(str)
    chat_state = Signal(str)
    cam_state = Signal(str)


def run_bg(fn, bus, on_ok=None):
    def worker():
        try:
            res = fn()
            if on_ok:
                on_ok(res)
        except Exception as e:
            bus.error.emit(str(e))
    threading.Thread(target=worker, daemon=True).start()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChangesStudio — Kick Yayıncı Paneli")
        self.resize(1180, 760)
        self.cfg = load_config()
        self.bus = Bus()
        self.api = None
        self.channel_data = {}
        self.chat_client = None
        self.receiver = None
        self.discovery = None
        self._last_frame = None
        self.me = {}
        self._recent = collections.deque(maxlen=40)   # telefona gönderilecek son sohbet
        self._seen_ids = set()

        tabs = QTabWidget()
        tabs.addTab(self._build_dashboard(), "PANEL")
        tabs.addTab(self._build_camera(), "IPHONE KAMERA")
        tabs.addTab(self._build_settings(), "AYARLAR")
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(14, 10, 14, 4)
        cl.addWidget(self._build_header())
        cl.addWidget(tabs)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.ind_chat = QLabel()
        self.ind_cam = QLabel()
        for lbl in (self.ind_chat, self.ind_cam):
            lbl.setStyleSheet("padding:0 10px;")
            self.statusBar().addPermanentWidget(lbl)
        self._set_ind(self.ind_chat, "Sohbet", "stopped")
        self._set_ind(self.ind_cam, "Kamera", "stopped")

        b = self.bus
        b.status.connect(lambda s: self.statusBar().showMessage(s, 8000))
        b.error.connect(lambda s: QMessageBox.warning(self, "Hata", s))
        b.chat.connect(self._add_chat)
        b.frame.connect(self._store_frame)
        b.channel.connect(self._show_channel)
        b.logged_in.connect(self._after_login)
        b.categories.connect(self._show_categories)
        b.camera_found.connect(self._camera_found)
        b.chat_sys.connect(self._add_sys)
        b.chat_state.connect(lambda st: self._set_ind(self.ind_chat, "Sohbet", st))
        b.cam_state.connect(lambda st: self._set_ind(self.ind_cam, "Kamera", st))

        self.poll = QTimer(self, interval=30_000, timeout=self.refresh_channel)
        self.preview_timer = QTimer(self, interval=40, timeout=self._paint_preview)
        self.preview_timer.start()

        self._init_api()
        self._start_discovery()
        self.vcam = None
        QTimer.singleShot(300, self._start_vcam)   # NVIDIA Broadcast / Zoom kamerayı hemen bulsun

    def _build_header(self):
        bar = QWidget(objectName="header")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setStyleSheet(f"QWidget#header {{ background:rgba(20,40,74,0.30); border:1px solid rgba(104,172,255,0.15);"
                          f" border-radius:22px; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 8, 16, 8)
        h.setSpacing(10)
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base, "assets", "logo.png")
        if os.path.exists(logo_path):
            logo = QLabel()
            logo.setPixmap(QPixmap(logo_path).scaledToHeight(54, Qt.SmoothTransformation))
            h.addWidget(logo)
        mark = QLabel(f"<span style='color:{P['ice']}'>Changes</span>"
                      f"<span style='color:{P['blue']}'>Studio</span>")
        f = QFont(BRAND_FONT, 24)
        f.setWeight(QFont.ExtraBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, -0.5)
        mark.setFont(f)
        # genel stil kuralı (13px/500) fontu ezmesin diye boyut ve kalınlık burada da veriliyor
        mark.setStyleSheet(f"font-family:'{BRAND_FONT}'; font-size:30px; font-weight:800; letter-spacing:-0.5px;")
        sub = QLabel("KICK YAYINCI PANELİ")
        sf = QFont(BRAND_FONT, 10)
        sf.setWeight(QFont.Bold)
        sf.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        sub.setFont(sf)
        sub.setStyleSheet(f"color:{P['night']}; background:{P['lav']}; border-radius:11px; padding:4px 12px;"
                          f" font-family:'{BRAND_FONT}'; font-size:11px; font-weight:800; letter-spacing:1.5px;")
        h.addWidget(mark)
        h.addWidget(sub, 0, Qt.AlignVCenter)
        h.addStretch()
        self.lbl_live_badge = QLabel("")
        h.addWidget(self.lbl_live_badge, 0, Qt.AlignVCenter)
        return bar

    # ===================== PANEL =====================
    def _build_dashboard(self):
        w = QWidget()
        root = QHBoxLayout(w)

        left = QVBoxLayout()
        acc = QGroupBox("Hesap")
        al = QVBoxLayout(acc)
        self.lbl_user = QLabel("Giriş yapılmadı")
        self.btn_login = QPushButton("Kick ile Giriş Yap", clicked=self.login)
        self.btn_logout = QPushButton("Çıkış", objectName="secondary", clicked=self.logout)
        al.addWidget(self.lbl_user)
        row = QHBoxLayout()
        row.addWidget(self.btn_login)
        row.addWidget(self.btn_logout)
        al.addLayout(row)
        left.addWidget(acc)

        live = QGroupBox("Yayın Durumu")
        ll = QFormLayout(live)
        self.lbl_live = QLabel("—")
        self.lbl_viewers = QLabel("—")
        self.lbl_started = QLabel("—")
        self.lbl_cat = QLabel("—")
        self.lbl_title = QLabel("—")
        self.lbl_title.setWordWrap(True)
        ll.addRow("Durum:", self.lbl_live)
        ll.addRow("Başlık:", self.lbl_title)
        ll.addRow("İzleyici:", self.lbl_viewers)
        ll.addRow("Başlangıç:", self.lbl_started)
        ll.addRow("Kategori:", self.lbl_cat)
        ll.addRow(QPushButton("Yenile", objectName="secondary", clicked=self.refresh_channel))
        left.addWidget(live)

        info = QGroupBox("Yayın Bilgisi Düzenle")
        il = QVBoxLayout(info)
        self.ed_title = QLineEdit(placeholderText="Yayın başlığı")
        il.addWidget(QLabel("Başlık"))
        il.addWidget(self.ed_title)
        il.addWidget(QLabel("Kategori ara"))
        crow = QHBoxLayout()
        self.ed_cat = QLineEdit(placeholderText="örn. Just Chatting")
        self.ed_cat.returnPressed.connect(self.search_categories)
        crow.addWidget(self.ed_cat)
        crow.addWidget(QPushButton("Ara", objectName="secondary", clicked=self.search_categories))
        il.addLayout(crow)
        self.cmb_cat = QComboBox()
        il.addWidget(self.cmb_cat)
        il.addWidget(QPushButton("Güncelle", clicked=self.update_channel))
        left.addWidget(info)
        left.addStretch()

        right = QVBoxLayout()
        chat = QGroupBox("Canlı Sohbet  (kullanıcıya sağ tık: timeout / ban)")
        cl = QVBoxLayout(chat)
        self.chat_list = QListWidget()
        self.chat_list.setWordWrap(True)
        self.chat_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._chat_menu)
        cl.addWidget(self.chat_list)
        srow = QHBoxLayout()
        self.ed_msg = QLineEdit(placeholderText="Mesaj yaz ve Enter'a bas...")
        self.ed_msg.returnPressed.connect(self.send_chat)
        srow.addWidget(self.ed_msg)
        srow.addWidget(QPushButton("Gönder", clicked=self.send_chat))
        cl.addLayout(srow)
        right.addWidget(chat)

        root.addLayout(left, 4)
        root.addLayout(right, 6)
        return w

    # ===================== KAMERA =====================
    def _build_camera(self):
        w = QWidget()
        root = QHBoxLayout(w)
        side = QVBoxLayout()

        g = QGroupBox("iPhone Bağlantısı")
        f = QFormLayout(g)
        self.cmb_dev = QComboBox()
        self.cmb_dev.addItem("— Ağda bulunan iPhone'lar —", None)
        self.cmb_dev.currentIndexChanged.connect(self._device_selected)
        self.ed_host = QLineEdit(self.cfg["camera_host"], placeholderText="iPhone IP (örn. 192.168.1.34)")
        self.sp_port = QSpinBox(maximum=65535, value=int(self.cfg["camera_port"]))
        self.sp_fps = QSpinBox(minimum=5, maximum=60, value=int(self.cfg["camera_fps"]))
        self.chk_vcam = QCheckBox("Sanal webcam her zaman açık (OBS Virtual Camera)",
                                  checked=bool(self.cfg.get("vcam_enabled", True)))
        self.chk_vcam.toggled.connect(self._vcam_toggled)
        self.cmb_vsize = QComboBox()
        for size in ("1280x720", "1920x1080"):
            self.cmb_vsize.addItem(size)
        self.cmb_vsize.setCurrentText(self.cfg.get("vcam_size", "1280x720"))
        self.cmb_vsize.currentTextChanged.connect(lambda _: self._restart_vcam())
        self.sp_fps.valueChanged.connect(lambda _: self._restart_vcam())
        f.addRow("Bulunanlar:", self.cmb_dev)
        f.addRow("IP:", self.ed_host)
        f.addRow("Port:", self.sp_port)
        f.addRow("FPS:", self.sp_fps)
        f.addRow("Sanal kamera:", self.cmb_vsize)
        f.addRow(self.chk_vcam)
        self.btn_cam = QPushButton("Bağlan", clicked=self.toggle_camera)
        f.addRow(self.btn_cam)
        side.addWidget(g)

        help_ = QLabel(
            "<b>Nasıl kullanılır?</b><br>"
            "1. iPhone'da <b>ChangesLens</b> uygulamasını aç, YAYINI BAŞLAT'a bas.<br>"
            "2. Telefon ve bilgisayar aynı Wi‑Fi'da olmalı.<br>"
            "3. Listeden iPhone'u seç ya da ekranda yazan IP'yi gir, Bağlan.<br>"
            "4. OBS / Discord / Zoom'da kamera olarak <b>OBS Virtual Camera</b> seç.<br>"
            "5. <b>NVIDIA Broadcast</b>: Kamera kaynağı olarak <b>OBS Virtual Camera</b> seç, sonra "
            "OBS'te kamera olarak <b>Camera (NVIDIA Broadcast)</b> kullan.<br><br>"
            "<i>OBS'in kendi \"Sanal Kamerayı Başlat\" butonuna basma — sanal kamerayı ChangesStudio kullanıyor.</i><br>"
            "<i>Sanal kamera için OBS Studio (28+) kurulu olmalıdır.</i>")
        help_.setWordWrap(True)
        side.addWidget(help_)
        self.lbl_fps = QLabel("FPS: —")
        side.addWidget(self.lbl_fps)
        side.addStretch()

        self.preview = QLabel("Önizleme", alignment=Qt.AlignCenter)
        self.preview.setMinimumSize(640, 360)
        self.preview.setStyleSheet(f"background:{P['night']}; color:{P['lav']}; border:3px solid {P['turq']}; border-radius:22px;")
        root.addLayout(side, 3)
        root.addWidget(self.preview, 7)
        return w

    # ===================== AYARLAR =====================
    def _build_settings(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Kick Geliştirici Uygulaması  (kick.com/settings/developer)")
        f = QFormLayout(g)
        self.ed_cid = QLineEdit(self.cfg["client_id"])
        self.ed_secret = QLineEdit(self.cfg["client_secret"], echoMode=QLineEdit.Password)
        self.ed_redirect = QLineEdit(self.cfg["redirect_uri"])
        f.addRow("Client ID:", self.ed_cid)
        f.addRow("Client Secret:", self.ed_secret)
        f.addRow("Redirect URI:", self.ed_redirect)
        lay.addWidget(g)

        g2 = QGroupBox("Sohbet")
        f2 = QFormLayout(g2)
        self.ed_room = QLineEdit(str(self.cfg["chatroom_id"]),
                                 placeholderText="Boş bırakılırsa otomatik bulunur")
        self.ed_pkey = QLineEdit(self.cfg["pusher_key"])
        self.ed_pcl = QLineEdit(self.cfg["pusher_cluster"])
        f2.addRow("Chatroom ID:", self.ed_room)
        f2.addRow("Pusher key:", self.ed_pkey)
        f2.addRow("Pusher cluster:", self.ed_pcl)
        lay.addWidget(g2)

        lay.addWidget(QPushButton("Kaydet", clicked=self.save_settings))
        lay.addWidget(QLabel(f"Ayar klasörü: {APP_DIR}\nSohbet günlüğü: {LOG_PATH}"))
        lay.addStretch()
        return w

    def save_settings(self):
        self.cfg.update({
            "client_id": self.ed_cid.text().strip(),
            "client_secret": self.ed_secret.text().strip(),
            "redirect_uri": self.ed_redirect.text().strip(),
            "chatroom_id": self.ed_room.text().strip(),
            "pusher_key": self.ed_pkey.text().strip() or DEFAULT_KEY,
            "pusher_cluster": self.ed_pcl.text().strip() or DEFAULT_CLUSTER,
        })
        save_config(self.cfg)
        self._init_api()
        self.bus.status.emit("Ayarlar kaydedildi")

    # ===================== KICK =====================
    def _init_api(self):
        if not self.cfg["client_id"]:
            self.lbl_user.setText("Önce Ayarlar sekmesinden Client ID / Secret girin")
            return
        self.api = KickAPI(self.cfg["client_id"], self.cfg["client_secret"],
                           self.cfg["redirect_uri"], TOKEN_PATH)
        if self.api.logged_in:
            self._after_login()

    def login(self):
        if not self.api:
            return self.bus.error.emit("Önce Ayarlar sekmesinden Client ID / Secret girin")
        self.bus.status.emit("Tarayıcıda Kick girişi bekleniyor...")
        run_bg(self.api.login, self.bus, lambda _: self.bus.logged_in.emit())

    def logout(self):
        if self.api:
            self.api.logout()
        if self.chat_client:
            self.chat_client.stop()
            self.chat_client = None
        self.channel_data = {}
        self.poll.stop()
        self.lbl_user.setText("Giriş yapılmadı")

    def _after_login(self):
        def fetch():
            me = self.api.me()
            ch = self.api.channel() or {}
            ch["_me"] = me
            return ch
        run_bg(fetch, self.bus, lambda ch: self.bus.channel.emit(ch))
        self.poll.start()

    def refresh_channel(self):
        if self.api and self.api.logged_in:
            run_bg(self.api.channel, self.bus, lambda ch: self.bus.channel.emit(ch or {}))

    def _show_channel(self, ch):
        first = not self.channel_data
        me = ch.pop("_me", None)
        self.channel_data.update(ch)
        if me:
            self.me = me
            self.lbl_user.setText(f"<b>{html.escape(me.get('name', ''))}</b>  (kick.com/{ch.get('slug', '')})")
        stream = ch.get("stream") or {}
        if stream.get("is_live"):
            self.lbl_live.setText(f"<span style='color:{P['kick']}'>● CANLI</span>")
            self.lbl_live_badge.setText(f"● CANLI · {stream.get('viewer_count', 0)} izleyici")
            self.lbl_live_badge.setStyleSheet(f"background:{P['kick']}; color:{P['night']}; font-weight:800;"
                                              " border-radius:14px; padding:6px 14px;")
        else:
            self.lbl_live.setText(f"<span style='color:{P['lav']}'>● Çevrimdışı</span>")
            self.lbl_live_badge.setText("● ÇEVRİMDIŞI")
            self.lbl_live_badge.setStyleSheet(f"background:rgba(20,40,74,0.7); color:{P['lav']}; font-weight:800;"
                                              " border-radius:14px; padding:6px 14px;")
        self.lbl_viewers.setText(str(stream.get("viewer_count", 0)))
        self.lbl_started.setText(stream.get("start_time") or "—")
        self.lbl_cat.setText((ch.get("category") or {}).get("name", "—"))
        self.lbl_title.setText(html.escape(ch.get("stream_title") or "—"))
        if first:
            self.ed_title.setText(ch.get("stream_title", ""))
            self._start_chat()

    def search_categories(self):
        q = self.ed_cat.text().strip()
        if q and self.api:
            run_bg(lambda: self.api.search_categories(q), self.bus,
                   lambda r: self.bus.categories.emit(r))

    def _show_categories(self, cats):
        self.cmb_cat.clear()
        for c in cats:
            self.cmb_cat.addItem(c.get("name", "?"), c.get("id"))
        if not cats:
            self.bus.status.emit("Kategori bulunamadı")

    def update_channel(self):
        title = self.ed_title.text().strip() or None
        cat = self.cmb_cat.currentData()
        cat_name = self.cmb_cat.currentText() if cat else None

        def do():
            self.api.update_channel(title, cat)
            ch = {}
            for _ in range(4):            # Kick bazen birkaç saniye eski veriyi döndürür
                time.sleep(1.5)
                ch = self.api.channel() or {}
                ok_t = title is None or ch.get("stream_title") == title
                ok_c = cat is None or (ch.get("category") or {}).get("id") == cat
                if ok_t and ok_c:
                    break
            if title is not None and ch.get("stream_title") != title:
                ch["stream_title"] = title     # API henüz eski değeri dönüyorsa yine de göster
            if cat is not None and (ch.get("category") or {}).get("id") != cat:
                ch["category"] = {"id": cat, "name": cat_name}
            return ch
        self.bus.status.emit("Yayın bilgisi gönderiliyor...")
        run_bg(do, self.bus, lambda ch: (self.bus.channel.emit(ch),
                                         self.bus.status.emit("Yayın bilgisi güncellendi ✓")))

    # ===================== SOHBET =====================
    def _start_chat(self):
        room = self.cfg.get("chatroom_id")

        def go(room_id):
            if not room_id:
                self.bus.chat_sys.emit("Chatroom ID otomatik bulunamadı — Ayarlar'dan elle girin (README'ye bakın)")
                return
            if self.chat_client:
                self.chat_client.stop()
            self.chat_client = KickChat(room_id, self.bus.chat.emit, self.bus.chat_sys.emit,
                                        self.cfg["pusher_key"], self.cfg["pusher_cluster"],
                                        on_state=self.bus.chat_state.emit)
            self.chat_client.start()

        if room:
            go(room)
        else:
            slug = self.channel_data.get("slug")
            run_bg(lambda: find_chatroom_id(slug), self.bus, go)

    def _add_chat(self, m):
        if m.get("id"):
            if m["id"] in self._seen_ids:
                return                     # kendi mesajımızın websocket yankısı
            self._seen_ids.add(m["id"])
        badges = [b for b in m["badges"] if b]
        icons = {"broadcaster": "★ ", "moderator": "⚔ ", "vip": "◆ ", "subscriber": "♦ ",
                 "og": "● ", "founder": "✦ "}
        prefix = "".join(icons.get(b, "") for b in badges)
        self._to_phone({"type": "chat", "user": m["username"], "content": m["content"], "badges": badges})
        item = QListWidgetItem(f"{prefix}{m['username']}:  {m['content']}")
        item.setData(Qt.UserRole, m)
        if "broadcaster" in badges:
            item.setForeground(QColor(P["ice"]))
        elif "moderator" in badges:
            item.setForeground(QColor(P["turq"]))
        elif "vip" in badges:
            item.setForeground(QColor(P["gold"]))
        elif "subscriber" in badges or "founder" in badges:
            item.setForeground(QColor(P["sub"]))
        else:
            item.setForeground(QColor(P["text"]))
        self.chat_list.addItem(item)
        if self.chat_list.count() > 500:
            self.chat_list.takeItem(0)
        self.chat_list.scrollToBottom()

    STATES = {"connected": ("#53fc18", "Bağlı"), "connecting": ("#f5a623", "Bağlanıyor..."),
              "retrying": ("#f5a623", "Yeniden deneniyor..."), "stopped": ("#ff4d4d", "Kapalı")}

    def _set_ind(self, lbl, name, state):
        color, text = self.STATES.get(state, ("#888", state))
        lbl.setText(f"{name}: <span style='color:{color}'>●</span> {text}")

    def _add_sys(self, text):
        event_colors = {"Subscription": P["sub"], "GiftedSubscriptions": P["sub"],
                        "Kicks": P["kick"], "Donation": P["gold"], "Tip": P["gold"],
                        "StreamHost": P["blue"], "Follow": P["turq"]}
        color = next((c for k, c in event_colors.items() if k in text), None)
        if color:
            self._to_phone({"type": "event", "text": text.replace("Olay: ", "").replace("Event", "")})
        item = QListWidgetItem(("✦ " if color else "⚙ ") + text)
        item.setForeground(QColor(color or P["lav"]))
        self.chat_list.addItem(item)
        self.chat_list.scrollToBottom()
        self.statusBar().showMessage(text, 8000)

    def _to_phone(self, obj):
        self._recent.append(obj)
        if self.receiver:
            self.receiver.send_json(obj)

    def send_chat(self):
        text = self.ed_msg.text().strip()
        bid = self.channel_data.get("broadcaster_user_id")
        if not text or not bid:
            return
        self.ed_msg.clear()
        me = self.me

        def shown(res):
            data = (res or {}).get("data") or {}
            if data.get("is_sent") is False:
                self.bus.chat_sys.emit("Mesaj Kick tarafından reddedildi (yavaş mod / yasaklı kelime olabilir)")
                return
            self.bus.chat.emit({"id": data.get("message_id"), "user_id": me.get("user_id"),
                                "username": me.get("name", "Ben"), "color": "#53fc18",
                                "badges": ["broadcaster"], "content": text})
        run_bg(lambda: self.api.send_chat(bid, text), self.bus, shown)

    def _chat_menu(self, pos):
        item = self.chat_list.itemAt(pos)
        if not item:
            return
        m = item.data(Qt.UserRole)
        if not m:
            return
        bid = self.channel_data.get("broadcaster_user_id")
        menu = QMenu(self)
        for label, dur in (("Timeout 1 dk", 1), ("Timeout 10 dk", 10), ("Timeout 1 saat", 60)):
            menu.addAction(QAction(label, self, triggered=lambda _=False, d=dur:
                                   run_bg(lambda: self.api.ban(bid, m["user_id"], d), self.bus,
                                          lambda _: self.bus.status.emit(f"{m['username']} susturuldu"))))
        menu.addSeparator()

        def do_ban():
            reason, ok = QInputDialog.getText(self, "Ban", f"{m['username']} için sebep:")
            if ok:
                run_bg(lambda: self.api.ban(bid, m["user_id"], None, reason), self.bus,
                       lambda _: self.bus.status.emit(f"{m['username']} banlandı"))
        menu.addAction(QAction("Kalıcı Ban", self, triggered=do_ban))
        menu.addAction(QAction("Banı Kaldır", self, triggered=lambda: run_bg(
            lambda: self.api.unban(bid, m["user_id"]), self.bus)))
        menu.exec(self.chat_list.mapToGlobal(pos))

    # ===================== KAMERA MANTIĞI =====================
    def _start_discovery(self):
        self.discovery = Discovery(self.bus.camera_found.emit)
        if not self.discovery.start():
            self.cmb_dev.setItemText(0, "(zeroconf yüklü değil — IP girin)")

    def _camera_found(self, name, host, port):
        if self.cmb_dev.findText(name) == -1:
            self.cmb_dev.addItem(name, (host, port))
            self.bus.status.emit(f"iPhone bulundu: {name} ({host})")

    def _device_selected(self, i):
        d = self.cmb_dev.itemData(i)
        if d:
            self.ed_host.setText(d[0])
            self.sp_port.setValue(d[1])

    def toggle_camera(self):
        if self.receiver:
            self.receiver.stop()
            self.receiver = None
            self.btn_cam.setText("Bağlan")
            return
        host = self.ed_host.text().strip()
        if not host:
            return self.bus.error.emit("iPhone IP adresini girin")
        self.cfg.update(camera_host=host, camera_port=self.sp_port.value(), camera_fps=self.sp_fps.value())
        save_config(self.cfg)
        self.receiver = CameraReceiver(host, self.sp_port.value(), self._on_cam_frame,
                                       self.bus.status.emit, on_state=self.bus.cam_state.emit,
                                       history=list(self._recent))
        self.receiver.start()
        self.btn_cam.setText("Bağlantıyı Kes")

    # ---- sürekli açık sanal kamera ----
    def _on_cam_frame(self, frame):
        """Alıcı thread'inden: kareyi sanal kameraya ve önizlemeye ver."""
        if self.vcam:
            self.vcam.submit(frame)
        self.bus.frame.emit(frame)

    def _placeholder(self, w=1920, h=1080):
        """iPhone bağlı değilken sanal kamerada görünen logolu bekleme ekranı."""
        img = QImage(w, h, QImage.Format_RGB888)
        img.fill(QColor(P["night"]))
        from PySide6.QtGui import QLinearGradient, QPainter
        pt = QPainter(img)
        pt.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, h, w, 0)
        g.setColorAt(0, QColor(P["forest"]))
        g.setColorAt(0.5, QColor(P["night"]))
        pt.fillRect(0, 0, w, h, g)
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        logo = QPixmap(os.path.join(base, "assets", "logo.png"))
        if not logo.isNull():
            logo = logo.scaledToHeight(int(h * 0.28), Qt.SmoothTransformation)
            pt.drawPixmap((w - logo.width()) // 2, int(h * 0.26), logo)
        f = QFont(BRAND_FONT, int(h * 0.035))
        f.setWeight(QFont.ExtraBold)
        pt.setFont(f)
        pt.setPen(QColor(P["ice"]))
        pt.drawText(0, int(h * 0.60), w, int(h * 0.08), Qt.AlignCenter, "iPhone kamerası bekleniyor")
        f.setPointSize(int(h * 0.018))
        f.setWeight(QFont.Medium)
        pt.setFont(f)
        pt.setPen(QColor(P["lav"]))
        pt.drawText(0, int(h * 0.68), w, int(h * 0.06), Qt.AlignCenter,
                    "ChangesLens'te YAYINI BAŞLAT'a bas, ChangesStudio'da Bağlan'a tıkla")
        pt.end()
        arr = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[:, :w * 3]
        return cv2.cvtColor(arr.reshape(h, w, 3), cv2.COLOR_RGB2BGR)

    def _start_vcam(self):
        if self.vcam or not self.chk_vcam.isChecked():
            return
        w, h = map(int, self.cmb_vsize.currentText().split("x"))
        self.vcam = VirtualCam(w, h, self.sp_fps.value(), self._placeholder(), self.bus.status.emit)
        if not self.vcam.start():
            self.vcam = None

    def _stop_vcam(self):
        if self.vcam:
            self.vcam.stop()
            self.vcam = None

    def _restart_vcam(self):
        self.cfg.update(vcam_size=self.cmb_vsize.currentText(), camera_fps=self.sp_fps.value())
        save_config(self.cfg)
        if self.vcam:
            self._stop_vcam()
            QTimer.singleShot(500, self._start_vcam)   # eski cihaz kapanana kadar bekle

    def _vcam_toggled(self, on):
        self.cfg["vcam_enabled"] = on
        save_config(self.cfg)
        self._start_vcam() if on else self._stop_vcam()

    def _store_frame(self, frame):
        self._last_frame = frame

    def _paint_preview(self):
        if self._last_frame is None:
            return
        f, self._last_frame = self._last_frame, None
        rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.receiver:
            self.lbl_fps.setText(f"FPS: {self.receiver.stats_fps:.1f}   Çözünürlük: {w}x{h}")

    def closeEvent(self, e):
        self._stop_vcam()
        if self.receiver:
            self.receiver.stop()
        if self.chat_client:
            self.chat_client.stop()
        if self.discovery:
            self.discovery.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    global BRAND_FONT
    BRAND_FONT = load_brand_font()
    app.setFont(QFont(BRAND_FONT, 10))
    app.setStyleSheet(STYLE.replace("__FONT__", BRAND_FONT))
    ico = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets", "icon.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
