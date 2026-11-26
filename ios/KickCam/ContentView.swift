import AVFoundation
import PhotosUI
import SwiftUI

// ChangesCraft tasarım dili (paylaşılan palet)
enum Brand {
    static func hex(_ v: UInt32) -> Color {
        Color(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
    }
    static let night = hex(0x050B0A)
    static let forest = hex(0x06503F)
    static let navy = hex(0x14284A)
    static let blue = hex(0x68ACFF)
    static let ice = hex(0x8AF2FF)
    static let turq = hex(0x2FE0C0)
    static let text = hex(0xD3E6FF)
    static let lav = hex(0xB4BFEE)
    static let kick = hex(0x53FC18)
    static let sub = hex(0xB48CFF)
    static let gold = hex(0xFFCF3F)
    static let accent = LinearGradient(colors: [turq, blue], startPoint: .leading, endPoint: .trailing)

    /// Marka fontu: uygulamaya Coolvetica eklenirse onu, yoksa Inter Tight'ı kullanır.
    static func font(_ size: CGFloat, _ weight: Font.Weight = .medium) -> Font {
        if UIFont(name: "Coolvetica-Regular", size: size) != nil || UIFont(name: "Coolvetica", size: size) != nil {
            return .custom(UIFont(name: "Coolvetica-Regular", size: size) != nil ? "Coolvetica-Regular" : "Coolvetica", size: size)
        }
        let name: String
        switch weight {
        case .heavy, .black: name = "InterTight-ExtraBold"
        case .bold, .semibold: name = "InterTight-Bold"
        default: name = "InterTight-Medium"
        }
        return .custom(name, size: size)
    }
}

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    var onLayer: (AVCaptureVideoPreviewLayer) -> Void = { _ in }
    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    }
    func makeUIView(context: Context) -> PreviewView {
        let v = PreviewView()
        v.previewLayer.session = session
        v.previewLayer.videoGravity = .resizeAspect
        v.backgroundColor = UIColor(red: 0.02, green: 0.04, blue: 0.04, alpha: 1)
        onLayer(v.previewLayer)
        return v
    }
    func updateUIView(_ uiView: PreviewView, context: Context) {}
}

/// Yayın sırasında kameranın altında görünen sohbet.
struct ChatPanel: View {
    let lines: [ChatLine]
    let connected: Bool

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 7) {
                    if lines.isEmpty {
                        Text(connected ? "Sohbet bekleniyor..." : "PC bağlanınca Kick sohbeti burada görünür")
                            .font(Brand.font(13)).foregroundColor(Brand.lav)
                            .frame(maxWidth: .infinity).padding(.top, 30)
                    }
                    ForEach(lines) { line in
                        row(line).id(line.id)
                    }
                }
                .padding(12)
            }
            .onChange(of: lines.count) { _ in
                guard let last = lines.last else { return }
                withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(last.id, anchor: .bottom) }
            }
        }
        .background(RoundedRectangle(cornerRadius: 24, style: .continuous).fill(Brand.night.opacity(0.7)))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Brand.navy, lineWidth: 1))
    }

    @ViewBuilder private func row(_ line: ChatLine) -> some View {
        switch line.kind {
        case .chat:
            (Text(icon(line.badges) + line.user + "  ").bold().foregroundColor(color(line.badges))
             + Text(line.text).foregroundColor(Brand.text))
                .font(Brand.font(16))
                .frame(maxWidth: .infinity, alignment: .leading)
        case .event:
            Text("✦ " + line.text)
                .font(Brand.font(13, .bold)).tracking(1)
                .foregroundColor(Brand.night)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Brand.sub))
        case .system:
            Text("⚙ " + line.text).font(Brand.font(12)).italic().foregroundColor(Brand.lav)
        }
    }

    private func icon(_ b: [String]) -> String {
        if b.contains("broadcaster") { return "★ " }
        if b.contains("moderator") { return "⚔ " }
        if b.contains("vip") { return "◆ " }
        if b.contains("subscriber") || b.contains("founder") { return "♦ " }
        return ""
    }

    private func color(_ b: [String]) -> Color {
        if b.contains("broadcaster") { return Brand.ice }
        if b.contains("moderator") { return Brand.turq }
        if b.contains("vip") { return Brand.gold }
        if b.contains("subscriber") || b.contains("founder") { return Brand.sub }
        return Brand.blue
    }
}

struct ContentView: View {
    @StateObject private var cam = CameraManager()

    var body: some View {
        TabView {
            StreamTab(cam: cam)
                .tabItem { Label("YAYIN", systemImage: "video.fill") }
            SettingsTab(cam: cam)
                .tabItem { Label("AYARLAR", systemImage: "slider.horizontal.3") }
        }
        .tint(Brand.turq)
        .font(Brand.font(15))
        .preferredColorScheme(.dark)
        .onAppear {
            let tab = UITabBarAppearance()
            tab.configureWithOpaqueBackground()
            tab.backgroundColor = UIColor(red: 0.02, green: 0.04, blue: 0.04, alpha: 0.96)
            if let f = UIFont(name: "InterTight-Bold", size: 11) {
                for item in [tab.stackedLayoutAppearance, tab.inlineLayoutAppearance, tab.compactInlineLayoutAppearance] {
                    item.normal.titleTextAttributes = [.font: f]
                    item.selected.titleTextAttributes = [.font: f]
                }
            }
            UISegmentedControl.appearance().setTitleTextAttributes(
                [.font: UIFont(name: "InterTight-Bold", size: 13) ?? .boldSystemFont(ofSize: 13)], for: .normal)
            UITabBar.appearance().standardAppearance = tab
            UITabBar.appearance().scrollEdgeAppearance = tab
        }
        .alert("Hata", isPresented: Binding(get: { cam.errorMessage != nil },
                                            set: { if !$0 { cam.errorMessage = nil } })) {
            Button("Tamam", role: .cancel) {}
        } message: { Text(cam.errorMessage ?? "") }
    }
}

/// Telefonun pil yüzdesi ve şarj durumu.
struct BatteryPill: View {
    let level: Int
    let charging: Bool

    private var icon: String {
        if charging { return "battery.100percent.bolt" }
        switch level {
        case ..<0: return "battery.0percent"
        case ..<13: return "battery.0percent"
        case ..<38: return "battery.25percent"
        case ..<63: return "battery.50percent"
        case ..<88: return "battery.75percent"
        default: return "battery.100percent"
        }
    }
    private var color: Color {
        if charging { return Brand.kick }
        if level >= 0 && level <= 15 { return .red }
        if level >= 0 && level <= 35 { return Brand.gold }
        return Brand.ice
    }

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: icon).font(.system(size: 13, weight: .semibold))
            Text(level < 0 ? "--" : "%\(level)").font(Brand.font(12, .heavy).monospacedDigit())
        }
        .foregroundColor(color)
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(Capsule().fill(Brand.navy.opacity(0.6)))
        .overlay(Capsule().stroke(color.opacity(0.35), lineWidth: 1))
    }
}

/// Canlı yayın etiketindeki nabız gibi atan nokta.
struct PulseDot: View {
    @State private var on = false
    var body: some View {
        Circle().fill(Color.white).frame(width: 7, height: 7)
            .opacity(on ? 0.35 : 1)
            .scaleEffect(on ? 0.8 : 1.1)
            .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: on)
            .onAppear { on = true }
    }
}

/// Arka plan: gece siyahı + köşede orman ışıması
struct BrandBackground: View {
    var body: some View {
        LinearGradient(colors: [Brand.forest, Brand.night, Brand.night],
                       startPoint: .bottomLeading, endPoint: .topTrailing)
            .ignoresSafeArea()
    }
}

// MARK: - YAYIN sekmesi (yatay): solda kamera, sağda sohbet
struct StreamTab: View {
    @ObservedObject var cam: CameraManager

    var body: some View {
        ZStack {
            BrandBackground()
            GeometryReader { geo in
                HStack(alignment: .top, spacing: 12) {
                    VStack(spacing: 8) {
                        header
                        CameraPreview(session: cam.session, onLayer: cam.attachPreview)
                            .overlay {
                                if let fx = cam.effectPreview {
                                    Image(decorative: fx, scale: 1).resizable().aspectRatio(contentMode: .fit)
                                        .background(Brand.night)
                                }
                            }
                            .aspectRatio(16 / 9, contentMode: .fit)
                            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Brand.accent, lineWidth: 3))
                            .overlay(alignment: .topLeading) { liveTag }
                            .overlay(alignment: .bottom) { warnings }
                            .shadow(color: Brand.turq.opacity(cam.clientCount > 0 ? 0.45 : 0.12), radius: 10)
                            .frame(maxHeight: .infinity)
                        controls
                    }
                    .frame(width: geo.size.width * 0.6)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("SOHBET").font(Brand.font(12, .bold)).tracking(3).foregroundColor(Brand.lav)
                        ChatPanel(lines: cam.chat, connected: cam.clientCount > 0)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Image("Logo").resizable().scaledToFit().frame(height: 28)
            HStack(spacing: 5) {
                Text("Changes")
                    .font(Brand.font(21, .heavy))
                    .foregroundStyle(LinearGradient(colors: [Brand.ice, Brand.text],
                                                    startPoint: .top, endPoint: .bottom))
                Text("LENS")
                    .font(Brand.font(11, .heavy)).tracking(1.5)
                    .foregroundColor(Brand.night)
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(Capsule().fill(Brand.accent))
                    .rotationEffect(.degrees(-4))
            }
            Spacer()
            BatteryPill(level: cam.batteryLevel, charging: cam.isCharging)
            statusChip
        }
    }

    @ViewBuilder private var statusChip: some View {
        if cam.isRunning {
            let connected = cam.clientCount > 0
            Text(connected ? "● PC BAĞLI" : "● PC BEKLENİYOR")
                .font(Brand.font(11, .bold)).tracking(1)
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(Capsule().fill(connected ? Brand.kick : Brand.navy))
                .foregroundColor(connected ? Brand.night : Brand.lav)
        }
    }

    @ViewBuilder private var warnings: some View {
        VStack(spacing: 6) {
            if cam.batteryLevel >= 0 && cam.batteryLevel <= 15 && !cam.isCharging {
                warning("battery.25percent", "Şarj %\(cam.batteryLevel) — yayın kesilmeden şarja tak", Color.red)
            }
            if cam.isHot {
                warning("thermometer.sun.fill", "Telefon ısındı — FPS'i ya da efektleri azalt", Brand.gold)
            }
        }
        .padding(10)
    }

    private func warning(_ icon: String, _ text: String, _ color: Color) -> some View {
        Label(text, systemImage: icon)
            .font(Brand.font(12, .bold))
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Capsule().fill(color.opacity(0.92)))
            .foregroundColor(color == Brand.gold ? Brand.night : .white)
    }

    private func fxButton(_ icon: String, on: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 15, weight: .semibold))
                .frame(width: 40, height: 40)
                .background(Circle().fill(on ? AnyShapeStyle(Brand.accent) : AnyShapeStyle(Brand.navy.opacity(0.75))))
                .foregroundColor(on ? Brand.night : Brand.ice)
        }
    }

    @ViewBuilder private var liveTag: some View {
        if cam.isRunning && cam.clientCount > 0 {
            HStack(spacing: 5) {
                PulseDot()
                Text("YAYINDA").font(Brand.font(11, .heavy)).tracking(1)
                if cam.autoFrame { Image(systemName: "person.crop.rectangle").font(.system(size: 10, weight: .bold)) }
                if cam.background != .off { Image(systemName: "person.and.background.dotted").font(.system(size: 10, weight: .bold)) }
            }
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(Capsule().fill(Color.red.opacity(0.9)))
            .foregroundColor(.white)
            .padding(12)
        }
    }

    private var controls: some View {
        HStack(spacing: 10) {
            if !cam.isRunning {
                Text("Telefon ve PC aynı Wi‑Fi'da olmalı")
                    .font(Brand.font(12)).foregroundColor(Brand.lav)
                    .lineLimit(1).minimumScaleFactor(0.7)
            }
            Spacer(minLength: 4)
            fxButton("person.crop.rectangle", on: cam.autoFrame) { cam.autoFrame.toggle() }
            fxButton("person.and.background.dotted", on: cam.background != .off) {
                // Kapalı -> Bulanık -> Görsel (seçildiyse) -> Yeşil Perde -> Kapalı
                switch cam.background {
                case .off: cam.background = .blur
                case .blur: cam.background = cam.backgroundThumb != nil ? .image : .green
                case .image: cam.background = .green
                case .green: cam.background = .off
                }
            }
            Button(action: { cam.useFront.toggle() }) {
                Image(systemName: "arrow.triangle.2.circlepath.camera")
                    .font(.system(size: 16, weight: .semibold))
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(Brand.navy.opacity(0.75)))
                    .foregroundColor(Brand.ice)
            }
            Button(action: { cam.isRunning ? cam.stop() : cam.start() }) {
                Text(cam.isRunning ? "DURDUR" : "YAYINI BAŞLAT")
                    .font(Brand.font(15, .heavy)).tracking(2)
                    .padding(.horizontal, 22)
                    .frame(height: 40)
                    .background {
                        if cam.isRunning {
                            Capsule().fill(Color.red.opacity(0.85))
                        } else {
                            Capsule().fill(Brand.accent)
                        }
                    }
                    .shadow(color: (cam.isRunning ? Color.red : Brand.turq).opacity(0.35), radius: 8, y: 2)
                    .foregroundColor(cam.isRunning ? .white : Brand.night)
            }
        }
    }
}

// MARK: - AYARLAR sekmesi
struct SettingsTab: View {
    @ObservedObject var cam: CameraManager
    @State private var pickedPhoto: PhotosPickerItem?

    var body: some View {
        ZStack {
            BrandBackground()
            Form {
                Section {
                    Picker("Kamera", selection: $cam.useFront) {
                        Text("Arka").tag(false)
                        Text("Ön").tag(true)
                    }.pickerStyle(.segmented)
                    Picker("Çözünürlük", selection: $cam.resolution) {
                        ForEach(Resolution.allCases) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.segmented)
                    Toggle("Fener", isOn: $cam.torch).disabled(cam.useFront)
                } header: { sectionTitle("KAMERA") }
                .listRowBackground(Brand.navy.opacity(0.35))

                Section {
                    Toggle("Otomatik Kadraj (yüz takibi)", isOn: $cam.autoFrame)
                    if cam.autoFrame {
                        sliderRow("YAKINLIK", cam.frameTightness < 3.0 ? "Yakın" : cam.frameTightness > 4.0 ? "Geniş" : "Orta") {
                            Slider(value: $cam.frameTightness, in: 2.2...4.5)
                        }
                    }
                    Picker("Arka plan", selection: $cam.background) {
                        ForEach(BackgroundMode.allCases) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.segmented)
                    if cam.background == .blur {
                        sliderRow("BULANIK", "\(Int(cam.blurRadius))") { Slider(value: $cam.blurRadius, in: 6...40) }
                    }
                    PhotosPicker(selection: $pickedPhoto, matching: .images) {
                        HStack(spacing: 12) {
                            if let thumb = cam.backgroundThumb {
                                Image(uiImage: thumb).resizable().scaledToFill()
                                    .frame(width: 64, height: 36)
                                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                            } else {
                                Image(systemName: "photo.on.rectangle.angled").foregroundColor(Brand.turq)
                            }
                            Text(cam.backgroundThumb == nil ? "Arka plan görseli seç" : "Arka plan görselini değiştir")
                                .foregroundColor(Brand.ice)
                        }
                    }
                    .onChange(of: pickedPhoto) { item in
                        Task {
                            if let data = try? await item?.loadTransferable(type: Data.self),
                               let img = UIImage(data: data) {
                                await MainActor.run { cam.setBackgroundImage(img) }
                            }
                        }
                    }
                } header: { sectionTitle("EFEKTLER") } footer: {
                    Text("Efektler telefonda işlenir; NVIDIA Broadcast gerekmez. Otomatik kadraj açıkken kamera 1080p çeker, yakınlaşınca görüntü net kalır; küçük kıpırdanmalarda kadraj oynamaz. Yeşil Perde, OBS'te Chroma Key ile arka planı tamamen silmek içindir. Eski iPhone'larda takılma olursa FPS'i 24'e indir.")
                        .foregroundColor(Brand.lav)
                }
                .listRowBackground(Brand.navy.opacity(0.35))

                Section {
                    sliderRow("FPS", "\(Int(cam.fps))") { Slider(value: $cam.fps, in: 10...60, step: 5) }
                    sliderRow("KALİTE", "\(Int(cam.quality * 100))") { Slider(value: $cam.quality, in: 0.3...0.95) }
                    sliderRow("ZOOM", String(format: "%.1fx", cam.zoom)) { Slider(value: $cam.zoom, in: 1...5) }
                } header: { sectionTitle("GÖRÜNTÜ") } footer: {
                    Text("Görüntü takılıyorsa önce KALİTE'yi, sonra FPS'i düşür.").foregroundColor(Brand.lav)
                }
                .listRowBackground(Brand.navy.opacity(0.35))

                Section {
                    infoRow("Durum", cam.isRunning ? (cam.clientCount > 0 ? "PC bağlı" : "PC bekleniyor") : "Kapalı")
                    infoRow("IP adresi", NetworkInfo.wifiIPAddress() ?? "Wi‑Fi bağlı değil")
                    infoRow("Pil", cam.batteryLevel < 0 ? "--" : "%\(cam.batteryLevel)" + (cam.isCharging ? " · şarjda" : ""))
                    infoRow("Port", "5050")
                } header: { sectionTitle("BAĞLANTI") } footer: {
                    Text("PC'deki ChangesStudio > IPHONE KAMERA sekmesinden bu telefonu seç.")
                        .foregroundColor(Brand.lav)
                }
                .listRowBackground(Brand.navy.opacity(0.35))
            }
            .scrollContentBackground(.hidden)
            .foregroundColor(Brand.text)
        }
    }

    private func sectionTitle(_ t: String) -> some View {
        Text(t).tracking(3).foregroundColor(Brand.lav)
    }

    private func infoRow(_ k: String, _ v: String) -> some View {
        HStack {
            Text(k).foregroundColor(Brand.lav)
            Spacer()
            Text(v).font(Brand.font(15, .bold).monospacedDigit()).foregroundColor(Brand.ice)
        }
    }

    private func sliderRow<S: View>(_ title: String, _ value: String, @ViewBuilder slider: () -> S) -> some View {
        HStack {
            Text(title).font(Brand.font(12, .semibold)).tracking(2).foregroundColor(Brand.lav)
                .frame(width: 70, alignment: .leading)
            slider()
            Text(value).font(Brand.font(12, .bold).monospacedDigit()).foregroundColor(Brand.ice).frame(width: 44)
        }
    }
}
