import Foundation
import Combine
import AVFoundation

@MainActor public final class AppModel: ObservableObject {
    @Published public var files: [URL] = []
    @Published public var selected: URL?
    @Published public var outputFolder: URL?
    @Published public var settings = EngineSettings()
    @Published public var batch = false
    @Published public var busy = false
    @Published public var progress: Double = 0
    @Published public var status = "Ready"
    @Published public var detail = "Local processing · Apple Silicon acceleration"
    @Published public var lastOutput: URL?
    @Published public var showRender = false
    @Published public var reports: [JobReport] = []
    public let player = AVPlayer()
    private let backend: BackendRunning
    private var cancelFile: URL?
    private var task: Task<Void, Never>?
    public init(backend: BackendRunning = BackendRunner()) { self.backend = backend }
    public static let extensions: Set<String> = ["mp4", "mov", "m4v", "mxf", "avi", "mkv"]

    public func addFiles(_ urls: [URL]) {
        guard !busy else { return }
        let accepted = urls.filter { url in
            var directory: ObjCBool = false
            return url.isFileURL && Self.extensions.contains(url.pathExtension.lowercased())
                && FileManager.default.fileExists(atPath: url.path, isDirectory: &directory) && !directory.boolValue
        }.map { $0.standardizedFileURL }
        guard !accepted.isEmpty else { status = BackendError.invalidVideo.localizedDescription; return }
        if batch {
            for url in accepted where !files.contains(url) { files.append(url) }
        } else { files = [accepted[0]] }
        select(accepted[0]); status = "Ready"; progress = 0
    }
    public func select(_ url: URL) {
        selected = url; lastOutput = nil; showRender = false
        loadPreview()
    }
    public func loadPreview() {
        player.pause()
        let url = showRender ? lastOutput?.appendingPathComponent("blurred.mp4") : selected
        player.replaceCurrentItem(with: url.map { AVPlayerItem(url: $0) })
    }
    public static func resultFolder(source: URL, parent: URL?, fileManager: FileManager = .default) -> URL {
        let root = parent ?? source.deletingLastPathComponent()
        let stem = source.deletingPathExtension().lastPathComponent + "_qc"
        var output = root.appendingPathComponent(stem, isDirectory: true)
        var index = 2
        while fileManager.fileExists(atPath: output.path) {
            output = root.appendingPathComponent("\(stem)_\(index)", isDirectory: true); index += 1
        }
        return output
    }
    public func start() {
        guard !busy, let selected else { return }
        do { try settings.validate() } catch { status = error.localizedDescription; return }
        let jobs = batch ? files : [selected]
        let snapshot = settings; let parent = outputFolder
        let marker = FileManager.default.temporaryDirectory.appendingPathComponent("url-guard-cancel-\(UUID().uuidString)")
        cancelFile = marker; busy = true; progress = 0; reports = []; showRender = false; loadPreview()
        task = Task { [weak self] in
            guard let self else { return }
            defer { self.busy = false; self.cancelFile = nil; try? FileManager.default.removeItem(at: marker) }
            do {
                for (index, source) in jobs.enumerated() {
                    if FileManager.default.fileExists(atPath: marker.path) { throw BackendError.cancelled }
                    let output = Self.resultFolder(source: source, parent: parent)
                    self.selected = source
                    self.lastOutput = nil; self.showRender = false; self.loadPreview()
                    self.status = "Preparing \(index + 1) of \(jobs.count)"
                    var receivedResult = false
                    for try await event in backend.events(source: source, output: output, settings: snapshot, cancelFile: marker) {
                        self.progress = (Double(index) + event.fraction) / Double(jobs.count)
                        self.status = "\(event.stage.capitalized) · \(index + 1)/\(jobs.count)"
                        if let report = event.report {
                            receivedResult = true; self.reports.append(report); self.lastOutput = URL(fileURLWithPath: report.output)
                            self.detail = "\(report.tracks) URL tracks · \(report.frames) frames · \(String(format: "%.1f", report.elapsedSeconds))s"
                        }
                    }
                    guard receivedResult else { throw BackendError.process("Engine exited without a completed result.") }
                }
                self.progress = 1; self.status = "Render ready · review before delivery"
                self.showRender = true; self.loadPreview()
            } catch { self.status = error.localizedDescription; self.detail = "No incomplete result is published." }
        }
    }
    public func cancel() {
        guard busy, let marker = cancelFile else { return }
        try? Data().write(to: marker); status = "Cancelling…"
    }
    public func stopPlayback() { player.pause() }
}
