import AVFoundation
import CoreImage
import ImageIO
import UIKit

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

    let session = AVCaptureSession()
    private let server = FrameServer()
    private let sessionQueue = DispatchQueue(label: "kickcam.session")
    private let videoQueue = DispatchQueue(label: "kickcam.video")
    private let ciContext = CIContext(options: [.useSoftwareRenderer: false])
    private var device: AVCaptureDevice?
    private var lastSent = CFAbsoluteTimeGetCurrent()
    private let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!

    override init() {
        super.init()
        server.onClientsChanged = { [weak self] n in self?.clientCount = n }
    }

    func start() {
        AVCaptureDevice.requestAccess(for: .video) { granted in
            guard granted else {
                DispatchQueue.main.async { self.errorMessage = "Kamera izni verilmedi (Ayarlar > KickCam)." }
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
            if let conn = out.connection(with: .video) {
                if #available(iOS 17.0, *) {
                    if conn.isVideoRotationAngleSupported(0) { conn.videoRotationAngle = 0 } // yatay
                } else {
                    conn.videoOrientation = .landscapeRight
                }
                if front && conn.isVideoMirroringSupported {
                    conn.automaticallyAdjustsVideoMirroring = false
                    conn.isVideoMirrored = true
                }
            }
            self.session.commitConfiguration()
            if !self.session.isRunning { self.session.startRunning() }
            DispatchQueue.main.async { self.applyZoom(); self.applyTorch() }
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

    // Kamera karesi geldi -> JPEG'e çevir -> gönder
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard server.hasClients else { return }
        let now = CFAbsoluteTimeGetCurrent()
        guard now - lastSent >= (1.0 / fps) * 0.95 else { return }
        lastSent = now
        guard let pb = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let image = CIImage(cvPixelBuffer: pb)
        let opts: [CIImageRepresentationOption: Any] = [CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String): quality]
        if let jpeg = ciContext.jpegRepresentation(of: image, colorSpace: colorSpace, options: opts) {
            server.send(jpeg: jpeg)
        }
    }
}
