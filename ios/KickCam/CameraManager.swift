import AVFoundation
import CoreImage
import ImageIO
import UIKit

struct ChatLine: Identifiable {
    enum Kind { case chat, event, system }
    let id = UUID()
    let kind: Kind
    let user: String
    let text: String
    let badges: [String]
}

enum Resolution: String, CaseIterable, Identifiable {
    case hd720 = "720p", hd1080 = "1080p"
    var id: String { rawValue }
    var preset: AVCaptureSession.Preset { self == .hd720 ? .hd1280x720 : .hd1920x1080 }
}

final class CameraManager: NSObject, ObservableObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    @Published var isRunning = false
    @Published var clientCount = 0
    @Published var useFront = false { didSet { if isRunning { reconfigure() } } }
    @Published var resolution: Resolution = .hd720 { didSet { if isRunning { reconfigure() } } }
    @Published var fps: Double = 30
    @Published var quality: Double = 0.6
    @Published var torch = false { didSet { applyTorch() } }
    @Published var zoom: CGFloat = 1.0 { didSet { applyZoom() } }
    @Published var errorMessage: String?
    @Published var chat: [ChatLine] = []

    // Efektler (NVIDIA Broadcast'teki otomatik kadraj ve sanal arka planın karşılığı)
    @Published var autoFrame = UserDefaults.standard.bool(forKey: "autoFrame") {
        didSet { effects.autoFrame = autoFrame; UserDefaults.standard.set(autoFrame, forKey: "autoFrame") }
    }
    @Published var frameTightness: Double = 3.2 { didSet { effects.frameTightness = frameTightness } }
    @Published var background: BackgroundMode =
        BackgroundMode(rawValue: UserDefaults.standard.string(forKey: "background") ?? "") ?? .off {
        didSet { effects.background = background; UserDefaults.standard.set(background.rawValue, forKey: "background") }
    }
    @Published var blurRadius: Double = 18 { didSet { effects.blurRadius = blurRadius } }
    @Published var backgroundThumb: UIImage?
    /// Efekt açıkken telefonda gösterilen işlenmiş önizleme
    @Published var effectPreview: CGImage?

    let session = AVCaptureSession()
    private let server = FrameServer()
    private let sessionQueue = DispatchQueue(label: "kickcam.session")
    private let videoQueue = DispatchQueue(label: "kickcam.video")
    private let ciContext = CIContext(options: [.useSoftwareRenderer: false])
    private var device: AVCaptureDevice?
    private var videoOutput: AVCaptureVideoDataOutput?
    private weak var previewLayer: AVCaptureVideoPreviewLayer?
    private var videoOrientation: AVCaptureVideoOrientation = .landscapeRight
    private var lastSent = CFAbsoluteTimeGetCurrent()
    private let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
    private let effects = VideoEffects()
    private var lastPreview: CFAbsoluteTime = 0
    private var previewShown = false
    private static var backgroundURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("background.jpg")
    }

    override init() {
        super.init()
        server.onClientsChanged = { [weak self] n in
            guard let self else { return }
            if n > 0 && self.clientCount == 0 { self.chat.removeAll() }   // PC son mesajları tekrar gönderir
            self.clientCount = n
        }
        server.onMessage = { [weak self] obj in self?.handle(obj) }
        effects.autoFrame = autoFrame
        effects.background = background
        if let data = try? Data(contentsOf: Self.backgroundURL), let img = UIImage(data: data) {
            setBackgroundImage(img, save: false)
        }
        UIDevice.current.beginGeneratingDeviceOrientationNotifications()
        NotificationCenter.default.addObserver(forName: UIDevice.orientationDidChangeNotification,
                                               object: nil, queue: .main) { [weak self] _ in
            // ekran dönme animasyonu bitince arayüz yönünü oku
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { self?.updateOrientation() }
        }
    }

    func start() {
        AVCaptureDevice.requestAccess(for: .video) { granted in
            guard granted else {
                DispatchQueue.main.async { self.errorMessage = "Kamera izni verilmedi (Ayarlar > ChangesLens)." }
                return
            }
            do {
                try self.server.start(name: UIDevice.current.name)
            } catch {
                DispatchQueue.main.async { self.errorMessage = "Sunucu başlatılamadı: \(error.localizedDescription)" }
                return
            }
            self.reconfigure()
            DispatchQueue.main.async {
                self.isRunning = true
                UIApplication.shared.isIdleTimerDisabled = true
            }
        }
    }

    func stop() {
        sessionQueue.async { self.session.stopRunning() }
        server.stop()
        isRunning = false
        UIApplication.shared.isIdleTimerDisabled = false
    }

    /// Önizleme katmanı oluşunca çağrılır.
    func attachPreview(_ layer: AVCaptureVideoPreviewLayer) {
        previewLayer = layer
        updateOrientation()
    }

    /// Ekran yatayda sağa/sola çevrildiğinde önizlemeyi ve PC'ye giden görüntüyü düz tutar.
    func updateOrientation() {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let o: AVCaptureVideoOrientation
        switch scene?.interfaceOrientation ?? .landscapeRight {
        case .landscapeLeft: o = .landscapeLeft
        case .portrait: o = .portrait
        case .portraitUpsideDown: o = .portraitUpsideDown
        default: o = .landscapeRight
        }
        videoOrientation = o
        if let c = previewLayer?.connection, c.isVideoOrientationSupported { c.videoOrientation = o }
        sessionQueue.async {
            if let c = self.videoOutput?.connection(with: .video), c.isVideoOrientationSupported {
                c.videoOrientation = o
            }
        }
    }

    /// Galeriden seçilen arka plan görselini hazırla (yönünü düzelt, küçült, kaydet).
    func setBackgroundImage(_ img: UIImage, save: Bool = true) {
        let maxSide: CGFloat = 1920
        let scale = min(1, maxSide / max(img.size.width, img.size.height))
        let size = CGSize(width: img.size.width * scale, height: img.size.height * scale)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let normalized = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            img.draw(in: CGRect(origin: .zero, size: size))
        }
        if let cg = normalized.cgImage { effects.backgroundImage = CIImage(cgImage: cg) }
        backgroundThumb = normalized
        if save, let data = normalized.jpegData(compressionQuality: 0.9) {
            try? data.write(to: Self.backgroundURL)
        }
        if background == .off || background == .blur { background = .image }
    }

    private func handle(_ obj: [String: Any]) {
        let line: ChatLine
        switch obj["type"] as? String {
        case "chat":
            line = ChatLine(kind: .chat, user: obj["user"] as? String ?? "?",
                            text: obj["content"] as? String ?? "", badges: obj["badges"] as? [String] ?? [])
        case "event":
            line = ChatLine(kind: .event, user: "", text: obj["text"] as? String ?? "", badges: [])
        default:
            line = ChatLine(kind: .system, user: "", text: obj["text"] as? String ?? "", badges: [])
        }
        chat.append(line)
        if chat.count > 150 { chat.removeFirst(chat.count - 150) }
    }

    private func reconfigure() {
        let front = useFront, res = resolution
        sessionQueue.async {
            self.session.beginConfiguration()
            self.session.inputs.forEach { self.session.removeInput($0) }
            self.session.outputs.forEach { self.session.removeOutput($0) }
            self.session.sessionPreset = res.preset

            let pos: AVCaptureDevice.Position = front ? .front : .back
            guard let dev = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: pos),
                  let input = try? AVCaptureDeviceInput(device: dev),
                  self.session.canAddInput(input) else {
                self.session.commitConfiguration()
                DispatchQueue.main.async { self.errorMessage = "Kamera açılamadı" }
                return
            }
            self.session.addInput(input)
            self.device = dev

            let out = AVCaptureVideoDataOutput()
            out.alwaysDiscardsLateVideoFrames = true
            out.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
            out.setSampleBufferDelegate(self, queue: self.videoQueue)
            if self.session.canAddOutput(out) { self.session.addOutput(out) }
            self.videoOutput = out
            if let conn = out.connection(with: .video) {
                if conn.isVideoOrientationSupported { conn.videoOrientation = self.videoOrientation }
                if front && conn.isVideoMirroringSupported {
                    conn.automaticallyAdjustsVideoMirroring = false
                    conn.isVideoMirrored = true
                }
            }
            self.session.commitConfiguration()
            if !self.session.isRunning { self.session.startRunning() }
            DispatchQueue.main.async { self.applyZoom(); self.applyTorch(); self.updateOrientation() }
        }
    }

    private func applyZoom() {
        guard let d = device, (try? d.lockForConfiguration()) != nil else { return }
        d.videoZoomFactor = max(1, min(zoom, min(d.activeFormat.videoMaxZoomFactor, 10)))
        d.unlockForConfiguration()
    }

    private func applyTorch() {
        guard let d = device, d.hasTorch, (try? d.lockForConfiguration()) != nil else { return }
        d.torchMode = torch ? .on : .off
        d.unlockForConfiguration()
    }

    // Kamera karesi geldi -> efektleri uygula -> JPEG'e çevir -> gönder
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        let hasClients = server.hasClients
        let fxOn = effects.isActive
        if !fxOn && previewShown {
            previewShown = false
            DispatchQueue.main.async { self.effectPreview = nil }
        }
        guard hasClients || fxOn else { return }
        let now = CFAbsoluteTimeGetCurrent()
        guard now - lastSent >= (1.0 / fps) * 0.95 else { return }
        lastSent = now
        guard let pb = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        let image = fxOn ? effects.process(pb) : CIImage(cvPixelBuffer: pb)

        // Telefondaki önizleme: efekt açıkken işlenmiş görüntüyü ~15 FPS göster
        if fxOn && now - lastPreview > 1.0 / 15 {
            lastPreview = now
            let s = 640 / image.extent.width
            let small = image.transformed(by: CGAffineTransform(scaleX: s, y: s))
            if let cg = ciContext.createCGImage(small, from: small.extent) {
                previewShown = true
                DispatchQueue.main.async { self.effectPreview = cg }
            }
        }

        guard hasClients else { return }
        let opts: [CIImageRepresentationOption: Any] = [CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String): quality]
        if let jpeg = ciContext.jpegRepresentation(of: image, colorSpace: colorSpace, options: opts) {
            server.send(jpeg: jpeg)
        }
    }
}
