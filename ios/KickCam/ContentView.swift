import AVFoundation
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
    static let accent = LinearGradient(colors: [turq, blue], startPoint: .leading, endPoint: .trailing)
}

/// Logodaki gibi kesik köşeli şekil.
struct ChamferShape: Shape {
    var cut: CGFloat = 14
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX + cut, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - cut))
        p.addLine(to: CGPoint(x: r.maxX - cut, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX, y: r.minY + cut))
        p.closeSubpath()
        return p
    }
}

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    }
    func makeUIView(context: Context) -> PreviewView {
        let v = PreviewView()
        v.previewLayer.session = session
        v.previewLayer.videoGravity = .resizeAspect
        v.backgroundColor = UIColor(red: 0.02, green: 0.04, blue: 0.04, alpha: 1)
        return v
    }
    func updateUIView(_ uiView: PreviewView, context: Context) {}
}

struct ContentView: View {
    @StateObject private var cam = CameraManager()

    var body: some View {
        ZStack {
            LinearGradient(colors: [Brand.forest, Brand.night, Brand.night],
                           startPoint: .bottomLeading, endPoint: .topTrailing)
                .ignoresSafeArea()
            VStack(spacing: 14) {
                header

                CameraPreview(session: cam.session)
                    .aspectRatio(16 / 9, contentMode: .fit)
                    .clipShape(ChamferShape())
                    .overlay(ChamferShape().stroke(Brand.accent, lineWidth: 3))
                    .shadow(color: Brand.turq.opacity(cam.clientCount > 0 ? 0.45 : 0.15), radius: 12)

                if cam.isRunning {
                    Text("IP  \(NetworkInfo.wifiIPAddress() ?? "bulunamadı")   ·   PORT  5050")
                        .font(.system(.footnote, design: .monospaced).weight(.semibold))
                        .tracking(1)
                        .foregroundColor(Brand.ice)
                }

                Form {
                    Section {
                        Picker("Kamera", selection: $cam.useFront) {
                            Text("Arka").tag(false)
                            Text("Ön").tag(true)
                        }.pickerStyle(.segmented)
                        Picker("Çözünürlük", selection: $cam.resolution) {
                            ForEach(Resolution.allCases) { Text($0.rawValue).tag($0) }
                        }.pickerStyle(.segmented)
                        sliderRow("FPS", "\(Int(cam.fps))") { Slider(value: $cam.fps, in: 10...60, step: 5) }
                        sliderRow("KALİTE", "\(Int(cam.quality * 100))") { Slider(value: $cam.quality, in: 0.3...0.95) }
                        sliderRow("ZOOM", String(format: "%.1fx", cam.zoom)) { Slider(value: $cam.zoom, in: 1...5) }
                        Toggle("Fener", isOn: $cam.torch).disabled(cam.useFront)
                    } header: {
                        Text("KAMERA").tracking(3).foregroundColor(Brand.lav)
                    }
                    .listRowBackground(Brand.navy.opacity(0.35))
                }
                .scrollContentBackground(.hidden)
                .tint(Brand.turq)
                .foregroundColor(Brand.text)

                Button(action: { cam.isRunning ? cam.stop() : cam.start() }) {
                    Text(cam.isRunning ? "YAYINI DURDUR" : "YAYINI BAŞLAT")
                        .font(.headline.weight(.heavy))
                        .tracking(2)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background {
                            if cam.isRunning {
                                ChamferShape(cut: 10).fill(Color.red.opacity(0.85))
                            } else {
                                ChamferShape(cut: 10).fill(Brand.accent)
                            }
                        }
                        .foregroundColor(cam.isRunning ? .white : Brand.night)
                }
            }
            .padding()
        }
        .preferredColorScheme(.dark)
        .alert("Hata", isPresented: Binding(get: { cam.errorMessage != nil },
                                            set: { if !$0 { cam.errorMessage = nil } })) {
            Button("Tamam", role: .cancel) {}
        } message: { Text(cam.errorMessage ?? "") }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 8) {
            Image("Logo").resizable().scaledToFit().frame(height: 34)
            (Text("CHANGES").foregroundColor(Brand.ice) + Text("CRAFT").foregroundColor(Brand.blue))
                .font(.system(size: 22, weight: .light))
                .tracking(4)
            Text("CAM").font(.caption.weight(.semibold)).tracking(3).foregroundColor(Brand.lav)
            Spacer()
            if cam.isRunning {
                let connected = cam.clientCount > 0
                Text(connected ? "● PC BAĞLI" : "● PC BEKLENİYOR")
                    .font(.caption2.weight(.bold))
                    .tracking(1)
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(ChamferShape(cut: 5).fill(connected ? Brand.kick : Brand.navy))
                    .foregroundColor(connected ? Brand.night : Brand.lav)
            }
        }
    }

    private func sliderRow<S: View>(_ title: String, _ value: String, @ViewBuilder slider: () -> S) -> some View {
        HStack {
            Text(title).font(.caption.weight(.semibold)).tracking(2).foregroundColor(Brand.lav)
                .frame(width: 64, alignment: .leading)
            slider()
            Text(value).font(.caption.monospacedDigit()).foregroundColor(Brand.ice).frame(width: 40)
        }
    }
}
