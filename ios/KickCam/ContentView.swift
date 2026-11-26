import AVFoundation
import SwiftUI

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
        v.backgroundColor = .black
        return v
    }
    func updateUIView(_ uiView: PreviewView, context: Context) {}
}

struct ContentView: View {
    @StateObject private var cam = CameraManager()
    private let kickGreen = Color(red: 0.33, green: 0.99, blue: 0.09)

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 12) {
                HStack {
                    Text("KickCam").font(.title2.bold()).foregroundColor(kickGreen)
                    Spacer()
                    if cam.isRunning {
                        Label(cam.clientCount > 0 ? "PC bağlı (\(cam.clientCount))" : "PC bekleniyor",
                              systemImage: cam.clientCount > 0 ? "checkmark.circle.fill" : "wifi")
                            .font(.footnote)
                            .foregroundColor(cam.clientCount > 0 ? kickGreen : .orange)
                    }
                }

                CameraPreview(session: cam.session)
                    .aspectRatio(16 / 9, contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.1)))

                if cam.isRunning {
                    Text("IP: \(NetworkInfo.wifiIPAddress() ?? "bulunamadı")  •  Port: 5050")
                        .font(.system(.body, design: .monospaced))
                        .foregroundColor(.white)
                }

                Form {
                    Section("Kamera") {
                        Picker("Kamera", selection: $cam.useFront) {
                            Text("Arka").tag(false)
                            Text("Ön").tag(true)
                        }.pickerStyle(.segmented)
                        Picker("Çözünürlük", selection: $cam.resolution) {
                            ForEach(Resolution.allCases) { Text($0.rawValue).tag($0) }
                        }.pickerStyle(.segmented)
                        HStack { Text("FPS \(Int(cam.fps))"); Slider(value: $cam.fps, in: 10...60, step: 5) }
                        HStack { Text("Kalite \(Int(cam.quality * 100))"); Slider(value: $cam.quality, in: 0.3...0.95) }
                        HStack { Text("Zoom \(String(format: "%.1fx", cam.zoom))"); Slider(value: $cam.zoom, in: 1...5) }
                        Toggle("Fener", isOn: $cam.torch).disabled(cam.useFront)
                    }
                }
                .scrollContentBackground(.hidden)

                Button(action: { cam.isRunning ? cam.stop() : cam.start() }) {
                    Text(cam.isRunning ? "Yayını Durdur" : "Yayını Başlat")
                        .font(.headline)
                        .frame(maxWidth: .infinity, minHeight: 50)
                        .background(cam.isRunning ? Color.red : kickGreen)
                        .foregroundColor(cam.isRunning ? .white : .black)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
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
}
