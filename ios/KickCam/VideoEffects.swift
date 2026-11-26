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
    var frameTightness: Double = 3.8

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
            smoothFace = nil
            outsideSince = nil
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

    // MARK: - Otomatik kadraj (yüz takibi) — sabit, sinematik

    /// Yüzün yumuşatılmış konumu/boyutu (görüntü koordinatında)
    private var smoothFace: CGRect?
    /// Yüz rahat bölgeden ne zamandan beri dışarıda
    private var outsideSince: CFAbsoluteTime?

    private func reframe(_ image: CIImage, _ pb: CVPixelBuffer) -> CIImage {
        let ext = image.extent
        let now = CFAbsoluteTimeGetCurrent()
        frameIndex += 1

        // 1) Yüz tespiti her 3 karede bir; ölçümler yumuşatılır (titreşimi süzer)
        if frameIndex % 3 == 0 {
            let handler = VNImageRequestHandler(cvPixelBuffer: pb, orientation: .up, options: [:])
            if (try? handler.perform([faces])) != nil, let found = faces.results, !found.isEmpty {
                var union = found[0].boundingBox
                for f in found.dropFirst() { union = union.union(f.boundingBox) }
                let face = VNImageRectForNormalizedRect(union, Int(ext.width), Int(ext.height))
                smoothFace = smoothFace.map { lerp($0, face, 0.18) } ?? face
                lastFaceAt = now
            }
        }

        // 2) Hedef kadraj sadece gerçekten gerektiğinde değişir
        let cur = current ?? ext
        if let face = smoothFace, now - lastFaceAt < 3.0 {
            let ideal = idealCrop(for: face, in: ext)
            if target == nil {
                target = ideal
            } else if needsReframe(face: face, crop: target!, ideal: ideal) {
                if outsideSince == nil { outsideSince = now }
                // 0,7 sn dışarıda kaldıysa kadrajı taşı (anlık hareketlere tepki verme)
                if now - outsideSince! > 0.7 { target = ideal; outsideSince = nil }
            } else {
                outsideSince = nil
            }
        } else if now - lastFaceAt > 3.0 {
            target = ext            // 3 sn yüz yoksa yavaşça tam kareye dön
            smoothFace = nil
        }

        // 3) Yavaş, yumuşak geçiş (~1,5 sn); hedefe çok yaklaşınca tam dur
        let goal = target ?? ext
        var next = lerp(cur, goal, 0.035)
        if abs(next.minX - goal.minX) < 0.5 && abs(next.width - goal.width) < 0.5 { next = goal }
        current = next

        // 4) Kırpılan bölgeyi tam kare boyutuna getir
        let s = ext.width / next.width
        return image.cropped(to: next)
            .transformed(by: CGAffineTransform(translationX: -next.minX, y: -next.minY))
            .transformed(by: CGAffineTransform(scaleX: s, y: s))
            .cropped(to: CGRect(origin: .zero, size: ext.size))
    }

    /// Yüz için ideal kadraj: yüz üst üçte birde, en fazla 1,8x yakınlaşma.
    private func idealCrop(for face: CGRect, in ext: CGRect) -> CGRect {
        let aspect = ext.width / ext.height
        let h = min(ext.height, max(face.height * frameTightness, ext.height / 1.8))
        let w = h * aspect
        var r = CGRect(x: face.midX - w / 2, y: face.midY - h * 0.62, width: w, height: h)
        r.origin.x = min(max(r.minX, ext.minX), ext.maxX - w)
        r.origin.y = min(max(r.minY, ext.minY), ext.maxY - h)
        return r
    }

    /// Yüz, mevcut kadrajın ortasındaki rahat bölgeden çıktı mı ya da boyut çok mu değişti?
    private func needsReframe(face: CGRect, crop: CGRect, ideal: CGRect) -> Bool {
        // Kadraj zaten gidebileceği yerdeyse (ör. görüntünün kenarı) yeniden hedefleme
        let same = abs(ideal.midX - crop.midX) < crop.width * 0.02 &&
                   abs(ideal.midY - crop.midY) < crop.height * 0.02 &&
                   abs(ideal.height - crop.height) < crop.height * 0.03
        if same { return false }
        let comfort = crop.insetBy(dx: crop.width * 0.30, dy: crop.height * 0.25)
        let outside = !comfort.contains(CGPoint(x: face.midX, y: face.midY))
        let sizeChange = abs(ideal.height - crop.height) / crop.height
        return outside || sizeChange > 0.22
    }

    private func lerp(_ a: CGRect, _ b: CGRect, _ t: CGFloat) -> CGRect {
        CGRect(x: a.minX + (b.minX - a.minX) * t, y: a.minY + (b.minY - a.minY) * t,
               width: a.width + (b.width - a.width) * t, height: a.height + (b.height - a.height) * t)
    }
}
