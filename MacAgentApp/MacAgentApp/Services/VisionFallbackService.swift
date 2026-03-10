import Foundation
import AppKit
import Vision
import CoreGraphics

// MARK: - Vision Fallback Service

/// 视觉辅助模块 — 当 AXUIElement 找不到元素时，使用屏幕截图 + OCR 定位
/// 作为 Accessibility API 的最后一道 fallback
class VisionFallbackService {
    static let shared = VisionFallbackService()
    private init() {}

    // MARK: - Screen Capture

    /// 截取整个主屏幕
    func captureMainScreen() -> CGImage? {
        return CGWindowListCreateImage(
            CGRect.null,
            .optionOnScreenOnly,
            kCGNullWindowID,
            [.boundsIgnoreFraming]
        )
    }

    /// 截取指定应用的窗口
    func captureAppWindow(pid: pid_t) -> CGImage? {
        let windowList = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        for win in windowList {
            if let ownerPID = win[kCGWindowOwnerPID as String] as? Int32, ownerPID == pid,
               let windowID = win[kCGWindowNumber as String] as? CGWindowID {
                return CGWindowListCreateImage(
                    CGRect.null,
                    .optionIncludingWindow,
                    windowID,
                    [.boundsIgnoreFraming]
                )
            }
        }
        return nil
    }

    /// 截取指定区域
    func captureRect(_ rect: CGRect) -> CGImage? {
        return CGWindowListCreateImage(
            rect,
            .optionOnScreenOnly,
            kCGNullWindowID,
            [.boundsIgnoreFraming]
        )
    }

    // MARK: - OCR (Text Recognition)

    /// 对截图执行文字识别，返回识别到的文本及其屏幕坐标
    func recognizeText(in image: CGImage, completion: @escaping ([TextMatch]) -> Void) {
        let request = VNRecognizeTextRequest { request, error in
            guard error == nil,
                  let results = request.results as? [VNRecognizedTextObservation] else {
                completion([])
                return
            }

            let imageWidth = CGFloat(image.width)
            let imageHeight = CGFloat(image.height)

            let matches = results.compactMap { observation -> TextMatch? in
                guard let candidate = observation.topCandidates(1).first else { return nil }
                // Vision 坐标系：左下角为原点，归一化 0-1
                let box = observation.boundingBox
                // 转换为屏幕坐标（左上角原点）
                let screenRect = CGRect(
                    x: box.origin.x * imageWidth,
                    y: (1 - box.origin.y - box.height) * imageHeight,
                    width: box.width * imageWidth,
                    height: box.height * imageHeight
                )
                return TextMatch(
                    text: candidate.string,
                    confidence: candidate.confidence,
                    rect: screenRect,
                    center: CGPoint(x: screenRect.midX, y: screenRect.midY)
                )
            }
            completion(matches)
        }

        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
        request.usesLanguageCorrection = true

        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        DispatchQueue.global(qos: .userInitiated).async {
            try? handler.perform([request])
        }
    }

    /// 同步版本 — 使用 DispatchSemaphore
    func recognizeTextSync(in image: CGImage) -> [TextMatch] {
        let semaphore = DispatchSemaphore(value: 0)
        var result: [TextMatch] = []
        recognizeText(in: image) { matches in
            result = matches
            semaphore.signal()
        }
        semaphore.wait()
        return result
    }

    // MARK: - Find Text on Screen

    /// 在屏幕截图中查找包含指定文本的位置
    func findText(_ searchText: String, in image: CGImage? = nil) -> [TextMatch] {
        guard let img = image ?? captureMainScreen() else { return [] }
        let allText = recognizeTextSync(in: img)
        let lower = searchText.lowercased()
        return allText.filter { $0.text.lowercased().contains(lower) }
    }

    /// 在指定应用窗口中查找文本
    func findTextInApp(pid: pid_t, searchText: String) -> [TextMatch] {
        guard let img = captureAppWindow(pid: pid) else { return [] }
        return findText(searchText, in: img)
    }

    // MARK: - Template Matching (简化版 — 基于颜色直方图)

    /// 在截图中查找与模板颜色分布最匹配的区域
    /// 这是轻量级实现，不依赖 OpenCV
    func findTemplateApproximate(template: CGImage, in screenshot: CGImage, threshold: Float = 0.8) -> CGPoint? {
        // 使用 Vision 的特征匹配
        let request = VNGenerateImageFeaturePrintRequest()
        let templateHandler = VNImageRequestHandler(cgImage: template, options: [:])
        let screenshotHandler = VNImageRequestHandler(cgImage: screenshot, options: [:])

        do {
            try templateHandler.perform([request])
            guard let templatePrint = request.results?.first as? VNFeaturePrintObservation else { return nil }

            let request2 = VNGenerateImageFeaturePrintRequest()
            try screenshotHandler.perform([request2])
            guard let screenshotPrint = request2.results?.first as? VNFeaturePrintObservation else { return nil }

            var distance: Float = 0
            try templatePrint.computeDistance(&distance, to: screenshotPrint)

            if distance < (1.0 - threshold) * 100 {
                // 匹配成功，返回屏幕中心（精确定位需要滑动窗口，这里简化）
                return CGPoint(x: CGFloat(screenshot.width) / 2, y: CGFloat(screenshot.height) / 2)
            }
        } catch {
            print("[Vision] Template matching error: \(error)")
        }
        return nil
    }
}

// MARK: - Models

/// OCR 识别结果
struct TextMatch: Codable {
    let text: String
    let confidence: Float
    let rect: CGRect
    let center: CGPoint
}

// 使 CGRect 和 CGPoint 符合 Codable（系统类型需要扩展）
extension CGRect: @retroactive Codable {
    enum CodingKeys: String, CodingKey { case x, y, width, height }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.init(x: try c.decode(CGFloat.self, forKey: .x),
                  y: try c.decode(CGFloat.self, forKey: .y),
                  width: try c.decode(CGFloat.self, forKey: .width),
                  height: try c.decode(CGFloat.self, forKey: .height))
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(origin.x, forKey: .x)
        try c.encode(origin.y, forKey: .y)
        try c.encode(size.width, forKey: .width)
        try c.encode(size.height, forKey: .height)
    }
}

extension CGPoint: @retroactive Codable {
    enum CodingKeys: String, CodingKey { case x, y }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.init(x: try c.decode(CGFloat.self, forKey: .x),
                  y: try c.decode(CGFloat.self, forKey: .y))
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(x, forKey: .x)
        try c.encode(y, forKey: .y)
    }
}
