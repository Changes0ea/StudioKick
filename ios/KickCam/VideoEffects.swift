import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit
import Vision

/// Sanal arka plan seçenekleri.
enum BackgroundMode: String, CaseIterable, Identifiable {
    case off = "Kapalı"
    case blur = "Bulanık"
    case image = "Görsel"
    case green = "Yeşil Perde"
    var id: String { rawValue }
}

/// Kamera karesine sanal arka plan ve otomatik kadraj uygular.
/// Apple Vision kullanır; işlem telefonun Neural Engine'inde yapılır, PC'ye ek yük bindirmez.
/// Tek bir video kuyruğundan (videoQueue) çağrılmalıdır.
final class VideoEffects {
    // Ayarlar (ana thread'den yazılır, video kuyruğundan okunur)
    var background: BackgroundMode = .off
    var blurRadius: Double = 18
    var backgroundImage: CIImage?
    var autoFrame = false
    /// Otomatik kadrajın ne kadar yakın çekeceği: 2.2 (yakın) ... 4.5 (geniş)
    var frameTightness: Double = 3.2

    var isActive: Bool { background != .off || autoFrame }

    private let segmentation: VNGeneratePersonSegmentationRequest = {
        let r = VNGeneratePersonSegmentationRequest()
        r.qualityLevel = .balanced
        r.outputPixelFormat = kCVPixelFormatType_OneComponent8
        return r
    }()
    private let faces = VNDetectFaceRectanglesRequest()
    private var frameIndex = 0
    private var target: CGRect?
    private var current: CGRect?
    private var lastFaceAt: CFAbsoluteTime = 0

    func process(_ pixelBuffer: CVPixelBuffer) -> CIImage {
        var image = CIImage(cvPixelBuffer: pixelBuffer)
        if background != .off {
            image = replaceBackground(image, pixelBuffer)
        }
        if autoFrame {
            image = reframe(image, pixelBuffer)
        } else {
            target = nil
            current = nil
        }
        return image
    }

    // MARK: - Sanal arka plan

    private func replaceBackground(_ image: CIImage, _ pb: CVPixelBuffer) -> CIImage {
        let handler = VNImageRequestHandler(cvPixelBuffer: pb, orientation: .up, options: [:])
        guard (try? handler.perform([segmentation])) != nil,
              let maskBuffer = segmentation.results?.first?.pixelBuffer else { return image }

        let ext = image.extent
        var mask = CIImage(cvPixelBuffer: maskBuffer)
        mask = mask.transformed(by: CGAffineTransform(scaleX: ext.width / mask.extent.width,
                                                       y: ext.height / mask.extent.height))
        // kenarları biraz yumuşat ki saç/omuz çizgisi tırtıklı görünmesin
        mask = mask.clampedToExtent().applyingGaussianBlur(sigma: 1.5).cropped(to: ext)

        let bg: CIImage
        switch background {
        case .blur:
            bg = blurred(image)
        case .image:
            bg = backgroundImage.map { aspectFill($0, into: ext) } ?? blurred(image)
        case .green:
            bg = CIImage(color: CIColor(red: 0, green: 1, blue: 0)).cropped(to: ext)
        case .off:
            return image
        }
        let blend = CIFilter.blendWithMask()
        blend.inputImage = image
        blend.backgroundImage = bg
        blend.maskImage = mask
        return blend.outputImage?.cropped(to: ext) ?? image
    }

    private func blurred(_ image: CIImage) -> CIImage {
        image.clampedToExtent().applyingGaussianBlur(sigma: blurRadius).cropped(to: image.extent)
    }

    private func aspectFill(_ img: CIImage, into rect: CGRect) -> CIImage {
        let s = max(rect.width / img.extent.width, rect.height / img.extent.height)
        let scaled = img.transformed(by: CGAffineTransform(scaleX: s, y: s))
        let dx = rect.midX - scaled.extent.midX, dy = rect.midY - scaled.extent.midY
        return scaled.transformed(by: CGAffineTransform(translationX: dx, y: dy)).cropped(to: rect)
    }

    // MARK: - Otomatik kadraj (yüz takibi)

    private func reframe(_ image: CIImage, _ pb: CVPixelBuffer) -> CIImage {
        let ext = image.extent
        let now = CFAbsoluteTimeGetCurrent()
        frameIndex += 1

        // Yüz tespiti her 3 karede bir: akıcı ama pil dostu
        if frameIndex % 3 == 0 {
            let handler = VNImageRequestHandler(cvPixelBuffer: pb, orientation: .up, options: [:])
            if (try? handler.perform([faces])) != nil, let found = faces.results, !found.isEmpty {
                var union = found[0].boundingBox
                for f in found.dropFirst() { union = union.union(f.boundingBox) }
                let face = VNImageRectForNormalizedRect(union, Int(ext.width), Int(ext.height))
                propose(for: face, in: ext)
                lastFaceAt = now
            } else if now - lastFaceAt > 2.0 {
                target = ext   // 2 sn yüz yoksa yavaşça tam kareye dön
            }
        }

        let goal = target ?? ext
        let cur = current ?? ext
        let a: CGFloat = 0.07   // yumuşaklık (küçük = daha sinematik)
        let next = CGRect(x: cur.minX + (goal.minX - cur.minX) * a,
                          y: cur.minY + (goal.minY - cur.minY) * a,
                          width: cur.width + (goal.width - cur.width) * a,
                          height: cur.height + (goal.height - cur.height) * a)
        current = next

        // Kırp ve tekrar tam boyuta büyüt (PC'ye giden çözünürlük değişmez)
        let s = ext.width / next.width
        return image.cropped(to: next)
            .transformed(by: CGAffineTransform(translationX: -next.minX, y: -next.minY))
            .transformed(by: CGAffineTransform(scaleX: s, y: s))
            .cropped(to: CGRect(origin: .zero, size: ext.size))
    }

    private func propose(for face: CGRect, in ext: CGRect) {
        let aspect = ext.width / ext.height
        let h = min(ext.height, max(face.height * frameTightness, ext.height * 0.42))
        let w = h * aspect
        // Yüzü kadrajın üst üçte birine yakın tut (CIImage'de y aşağıdan yukarı artar)
        let cx = face.midX
        let cy = face.midY - h * 0.12
        var r = CGRect(x: cx - w / 2, y: cy - h / 2, width: w, height: h)
        r.origin.x = min(max(r.minX, ext.minX), ext.maxX - w)
        r.origin.y = min(max(r.minY, ext.minY), ext.maxY - h)

        // Ölü bölge: küçük kıpırdanmalarda kadraj oynamasın
        if let t = target {
            let moved = abs(t.midX - r.midX) / ext.width + abs(t.midY - r.midY) / ext.height
            let resized = abs(t.height - r.height) / ext.height
            if moved < 0.04 && resized < 0.06 { return }
        }
        target = r
    }
}
