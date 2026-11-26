# iPhone uygulamasını sadece Windows ile kurmak

Bu kurulumda Mac'e hiç gerek yok. iOS uygulaması GitHub'ın ücretsiz Mac sunucusunda otomatik olarak derlenir.
Sen de çıkan dosyayı Windows'tan **Sideloadly** ile telefona yüklersin.

## A) Kodu GitHub'a yükle (bir kerelik)
1. https://github.com adresinden ücretsiz bir hesap aç.
2. Sağ üstteki **+** → **New repository**
   - İsim: `KickStudio`
   - **Public** seçersen derleme süresi sınırsız olur.
     Private seçersen ayda yaklaşık 200 dakika Mac derleme hakkın olur (bir derleme 5 dakika sürer).
     Zip'in içinde gizli bilgi yok, Kick anahtarların kendi bilgisayarında kalıyor.
   - **Create repository**
3. Açılan sayfada **"uploading an existing file"** bağlantısına tıkla.
4. Zip'i aç ve `KickStudio` klasörünün **içindekileri** (`.github`, `ios`, `windows`, `README.md` ...) sayfaya sürükleyip bırak.
   **`.github` klasörünün de yüklendiğinden emin ol**, otomatik derleme bu klasöre bağlı.
5. **Commit changes**

## B) Derlenmiş uygulamayı indir
1. Depo sayfasında **Actions** sekmesine git.
   İlk seferde "I understand my workflows, enable them" diye bir uyarı çıkarsa onayla.
2. **Derle (iPhone IPA + Windows EXE)** → derleme kendiliğinden başlar.
   Başlamazsa sağdaki **Run workflow** butonuna bas.
3. Yaklaşık 5–10 dakika sonra yeşil ✓ işareti çıkar. Tıkla, en alttaki **Artifacts** bölümünden indir:
   - **KickCam-iPhone** → içinden `KickCam.ipa` çıkar
   - **KickStudio-Windows** → hazır `KickStudio.exe` (Python kurmana gerek kalmaz)

## C) iPhone'a yükle (Sideloadly)
1. Apple'ın sitesinden **iTunes**'u kur. Microsoft Store sürümü değil, apple.com'daki sürüm olmalı;
   Sideloadly iPhone'u bunun sürücüsüyle tanıyor.
2. https://sideloadly.io adresinden Sideloadly'yi indirip kur.
3. iPhone'u kabloyla bağla, telefonda "Bu bilgisayara güven" uyarısını onayla.
4. Sideloadly'de:
   - `KickCam.ipa` dosyasını pencereye sürükle
   - Apple ID'ni (e-posta) yaz → **Start** → Apple ID şifreni gir
5. iPhone'da:
   - **Ayarlar → Genel → VPN ve Cihaz Yönetimi** → Apple ID'ne dokun → **Güven**
   - **Ayarlar → Gizlilik ve Güvenlik → Geliştirici Modu** → Aç (telefon yeniden başlar)
6. KickCam'i aç, Kamera ve Yerel Ağ izinlerine **İzin Ver** de.

## Bilmen gerekenler
- **7 gün kuralı:** Ücretsiz Apple ID ile yüklenen uygulama 7 gün sonra açılmaz.
  Sideloadly'de aynı `.ipa` dosyasını tekrar Start ile yükle, 1 dakika sürer ve ayarların silinmez.
  Sideloadly'nin "Automatic refresh" seçeneğiyle bunu otomatik de yaptırabilirsin.
  Yıllık 99$'lık Apple Developer hesabın varsa uygulama 1 yıl çalışır.
- **Uygulama sınırı:** Ücretsiz hesapla aynı anda en fazla 3 kendi yüklediğin uygulama olabilir.
- **Derleme hata verirse** (kırmızı ✗): Actions'taki hatalı adıma tıkla, kırmızı satırları kopyala ve bana gönder, düzeltirim.
