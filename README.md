# KickStudio

İki parçadan oluşur:

| Parça | Platform | Görevi |
|---|---|---|
| `windows/` | Windows 10/11 (Python + Qt) | Kick yayıncı paneli + iPhone görüntüsünü **sanal webcam** olarak sisteme verir |
| `ios/` | iPhone (iOS 16+, Swift) | **KickCam**: kamerayı Wi‑Fi üzerinden bilgisayara gönderir |

## Özellikler
**Yayıncı paneli:** Kick ile OAuth girişi · canlı/çevrimdışı durumu, izleyici sayısı (30 sn'de bir yenilenir) · yayın başlığı ve kategori değiştirme · canlı sohbeti okuma ve sohbete mesaj yazma · sağ tıkla timeout (1 dk / 10 dk / 1 saat), kalıcı ban, ban kaldırma.

**iPhone webcam:** ön/arka kamera, 720p/1080p, 10–60 FPS, JPEG kalitesi, zoom ve fener ayarı · Bonjour ile otomatik bulma (IP elle de girilebilir) · görüntü "OBS Virtual Camera" olarak OBS, Discord, Zoom, Teams ve tarayıcılarda görünür.

---

## 1) Windows kurulumu
1. [Python 3.11+](https://www.python.org/downloads/) kur (kurulumda "Add to PATH" kutusunu işaretle).
2. [OBS Studio 28+](https://obsproject.com) kur. Sanal kamera sürücüsü OBS ile gelir; OBS'in açık olması gerekmez.
3. `windows\run.bat` dosyasını çalıştır. İlk açılışta bağımlılıklar kendiliğinden kurulur.
   Tek dosyalık `.exe` istersen `windows\build.bat` → `dist\KickStudio\KickStudio.exe`.

### Kick API anahtarı
1. https://kick.com/settings/developer → **Create App**
2. Redirect URL: `http://localhost:8765/callback`
3. Şu izinleri seç: `user:read`, `channel:read`, `channel:write`, `chat:write`, `moderation:ban`, `events:subscribe`
4. Client ID ve Client Secret'ı uygulamadaki **Ayarlar** sekmesine yapıştır → Kaydet → **Panel** → *Kick ile Giriş Yap*

> Sohbet, Kick'in kendi sitesinde kullandığı websocket üzerinden okunur. Chatroom ID kendiliğinden bulunamazsa
> (Cloudflare engeli), tarayıcıda `https://kick.com/api/v2/channels/KANAL_ADIN` adresini aç,
> `"chatroom":{"id": ...}` değerini kopyalayıp Ayarlar'a gir.

## 2) iPhone uygulaması (bir Mac ve Xcode gerekir)
```bash
brew install xcodegen
cd ios && xcodegen
open KickCam.xcodeproj
```
Xcode'da *Signing & Capabilities* → Team olarak Apple ID'ni seç → iPhone'u kabloyla bağla → ▶ Run.
Ücretsiz Apple ID ile imzalanan uygulama 7 gün çalışır; sonra tekrar Run yapman gerekir. Ücretli geliştirici hesabıyla (99$/yıl) 1 yıl çalışır ve TestFlight kullanılabilir.
İlk açılışta **Kamera** ve **Yerel Ağ** izinlerine "İzin Ver" de.

## 3) Kullanım
1. iPhone ve PC aynı Wi‑Fi ağında olsun (5 GHz önerilir).
2. iPhone'da KickCam → **Yayını Başlat**
3. PC'de KickStudio → **iPhone Kamera** sekmesi → listeden telefonunu seç (veya ekrandaki IP'yi gir) → **Bağlan**
4. OBS'te: Kaynak ekle → *Video Yakalama Cihazı* → **OBS Virtual Camera**
   (Dikkat: OBS'in kendi "Sanal Kamerayı Başlat" butonuna basma; çünkü cihazı KickStudio kullanıyor.
   OBS içinde doğrudan kullanmak istersen, sanal kamera kutusunu kapatıp KickStudio önizleme penceresini *Pencere Yakalama* ile alabilirsin.)

## Protokol
TCP 5050 portu. Her kare `[4 bayt big-endian uzunluk][JPEG]` biçiminde gönderilir. Bonjour servisi: `_kickcam._tcp`.
