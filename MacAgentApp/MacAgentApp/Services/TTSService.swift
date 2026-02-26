import Foundation
import AVFoundation

/// macOS TTS：使用 AVSpeechSynthesizer 朗读文本，支持流式按句朗读与停止。
@MainActor
final class TTSService: NSObject, ObservableObject {
    static let shared = TTSService()
    
    private let synthesizer = AVSpeechSynthesizer()
    private var pendingSentenceBuffer: String = ""
    private var spokenSentenceCount: Int = 0
    private static let sentenceEndChars: Set<Character> = ["。", "！", "？", ".", "!", "?", "\n"]
    
    @Published private(set) var isSpeaking: Bool = false
    
    override init() {
        super.init()
        synthesizer.delegate = self
    }
    
    /// 朗读完整一段文字（会先停止当前朗读再播）
    func speak(_ text: String) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        stop()
        let utterance = AVSpeechUtterance(string: t)
        utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN") ?? AVSpeechSynthesisVoice(language: "en-US")
        synthesizer.speak(utterance)
        isSpeaking = true
    }
    
    /// 流式追加内容：只朗读新完整的句子（句号、问号、感叹号、换行结尾），避免重复播
    func appendAndSpeakStreamedContent(_ fullText: String) {
        let t = fullText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        
        let (sentences, remainder) = Self.splitIntoSentences(t)
        pendingSentenceBuffer = remainder
        
        for i in spokenSentenceCount..<sentences.count {
            let trimmed = sentences[i].trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                if !isSpeaking {
                    speakUtterance(trimmed)
                    isSpeaking = true
                } else {
                    queueSentence(trimmed)
                }
            }
        }
        spokenSentenceCount = sentences.count
    }
    
    private var sentenceQueue: [String] = []
    
    private func queueSentence(_ s: String) {
        sentenceQueue.append(s)
    }
    
    private func speakUtterance(_ text: String) {
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN") ?? AVSpeechSynthesisVoice(language: "en-US")
        synthesizer.speak(utterance)
    }
    
    private func speakNextInQueue() {
        guard !sentenceQueue.isEmpty, !isSpeaking else { return }
        let next = sentenceQueue.removeFirst()
        speakUtterance(next)
        isSpeaking = true
    }
    
    /// 会话结束：朗读剩余缓冲中的内容
    func speakRemainingBuffer() {
        let t = pendingSentenceBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
        pendingSentenceBuffer = ""
        spokenSentenceCount = 0
        if !t.isEmpty {
            if !isSpeaking {
                speakUtterance(t)
                isSpeaking = true
            } else {
                queueSentence(t)
            }
        }
    }
    
    /// 重置流式状态（新一条助手消息开始时调用，避免和上一条句子计数混在一起）
    func resetStreamState() {
        spokenSentenceCount = 0
    }
    
    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
        sentenceQueue.removeAll()
        pendingSentenceBuffer = ""
        spokenSentenceCount = 0
        isSpeaking = false
    }
    
    /// 按句号、问号、感叹号、换行分割，返回 (完整句子数组, 最后未完成片段)
    static func splitIntoSentences(_ text: String) -> (sentences: [String], remainder: String) {
        var sentences: [String] = []
        var current = ""
        for char in text {
            let s = String(char)
            if Self.sentenceEndChars.contains(char) {
                current += s
                let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { sentences.append(trimmed) }
                current = ""
            } else {
                current += s
            }
        }
        let remainder = current.trimmingCharacters(in: .whitespacesAndNewlines)
        return (sentences, remainder)
    }
}

extension TTSService: @preconcurrency AVSpeechSynthesizerDelegate {
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.isSpeaking = false
            if !self.sentenceQueue.isEmpty {
                self.speakNextInQueue()
            }
        }
    }
    
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.isSpeaking = false
            if !self.sentenceQueue.isEmpty {
                self.speakNextInQueue()
            }
        }
    }
}
