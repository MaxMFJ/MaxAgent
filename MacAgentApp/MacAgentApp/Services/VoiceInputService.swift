import Foundation
import Speech
import AVFoundation

/// 语音输入服务：实时识别、静音超时自动提交、无说话超时强制提交。
/// 识别结果通过 onInterim / onFinal 回写输入框；onShouldSubmit 时由调用方发送消息（空消息需过滤）。
final class VoiceInputService: NSObject, ObservableObject {
    
    enum AuthorizationStatus {
        case notDetermined
        case denied
        case authorized
    }
    
    /// 静音多久后自动提交（秒）
    var silenceDuration: TimeInterval = 2.0
    /// 一直未说话多久后强制提交（秒）
    var noSpeechTimeout: TimeInterval = 12.0
    
    /// 实时中间结果（显示在输入框）
    @Published var interimText: String = ""
    /// 当前会话已确认的最终文本（用于提交）
    @Published var finalText: String = ""
    
    /// 静音检测到后触发提交：参数为当前最终文本，调用方需过滤空字符串
    var onShouldSubmit: ((String) -> Void)?
    /// 授权状态变化
    @Published var authorizationStatus: AuthorizationStatus = .notDetermined
    
    private var speechRecognizer: SFSpeechRecognizer?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()
    
    private var silenceWorkItem: DispatchWorkItem?
    private var noSpeechWorkItem: DispatchWorkItem?
    private let queue = DispatchQueue(label: "com.macagent.voiceinput")
    
    private var isRunning = false
    
    override init() {
        super.init()
        speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))
        if speechRecognizer == nil {
            speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
        }
    }
    
    func requestAuthorization(completion: @escaping (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            DispatchQueue.main.async {
                switch status {
                case .authorized:
                    self?.authorizationStatus = .authorized
                    completion(true)
                case .denied:
                    self?.authorizationStatus = .denied
                    completion(false)
                case .restricted:
                    self?.authorizationStatus = .denied
                    completion(false)
                case .notDetermined:
                    self?.authorizationStatus = .notDetermined
                    completion(false)
                @unknown default:
                    self?.authorizationStatus = .notDetermined
                    completion(false)
                }
            }
        }
    }
    
    func startRecording() {
        guard authorizationStatus == .authorized else {
            requestAuthorization { [weak self] ok in
                if ok { self?.startRecording() }
            }
            return
        }
        
        guard !isRunning else { return }
        guard let recognizer = speechRecognizer, recognizer.isAvailable else { return }
        
        stopRecording()
        
        interimText = ""
        finalText = ""
        isRunning = true
        
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        req.requiresOnDeviceRecognition = false
        recognitionRequest = req
        
        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.recognitionRequest?.append(buffer)
        }
        
        audioEngine.prepare()
        do {
            try audioEngine.start()
        } catch {
            isRunning = false
            return
        }
        
        recognitionTask = recognizer.recognitionTask(with: req) { [weak self] result, error in
            guard let self = self else { return }
            if let error = error {
                let ns = error as NSError
                if ns.code != 216 && ns.code != 203 { }
                return
            }
            guard let result = result else { return }
            
            let best = result.bestTranscription.formattedString
            let isFinal = result.isFinal
            
            DispatchQueue.main.async {
                if isFinal {
                    self.finalText = best
                    self.interimText = ""
                    self.cancelNoSpeechTimeout()
                    self.scheduleSilenceSubmit()
                } else {
                    self.interimText = best
                }
            }
        }
        
        scheduleNoSpeechTimeout()
    }
    
    private func cancelNoSpeechTimeout() {
        queue.async { [weak self] in
            self?.noSpeechWorkItem?.cancel()
            self?.noSpeechWorkItem = nil
        }
    }
    
    func stopRecording() {
        queue.async { [weak self] in
            self?.silenceWorkItem?.cancel()
            self?.silenceWorkItem = nil
            self?.noSpeechWorkItem?.cancel()
            self?.noSpeechWorkItem = nil
        }
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        isRunning = false
    }
    
    /// 静音 N 秒后自动提交（只提交一次，然后停止录音）
    private func scheduleSilenceSubmit() {
        let textToSubmit = finalText
        queue.async { [weak self] in
            guard let self = self else { return }
            self.silenceWorkItem?.cancel()
            let item = DispatchWorkItem { [weak self] in
                DispatchQueue.main.async {
                    guard let self = self, self.isRunning else { return }
                    self.stopRecording()
                    self.onShouldSubmit?(textToSubmit)
                }
            }
            self.silenceWorkItem = item
            self.queue.asyncAfter(deadline: .now() + self.silenceDuration, execute: item)
        }
    }
    
    /// 超时未说话则强制提交（可能为空），只提交一次后停止
    private func scheduleNoSpeechTimeout() {
        queue.async { [weak self] in
            guard let self = self else { return }
            self.noSpeechWorkItem?.cancel()
            let item = DispatchWorkItem { [weak self] in
                DispatchQueue.main.async {
                    guard let self = self, self.isRunning else { return }
                    let text = self.finalText.isEmpty ? self.interimText : self.finalText
                    self.stopRecording()
                    self.onShouldSubmit?(text)
                }
            }
            self.noSpeechWorkItem = item
            self.queue.asyncAfter(deadline: .now() + self.noSpeechTimeout, execute: item)
        }
    }
    
    /// 手动触发提交（例如用户点击「发送」）：取当前 finalText 或 interimText
    func commitCurrentText() -> String {
        let text = finalText.isEmpty ? interimText : finalText
        stopRecording()
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
