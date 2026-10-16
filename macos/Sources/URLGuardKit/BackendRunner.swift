import Foundation

public struct BackendEvent: Decodable, Equatable {
    public var stage: String
    public var frame: Int?
    public var seconds: Double?
    public var duration: Double?
    public var report: JobReport?
    public init(stage: String, frame: Int? = nil, seconds: Double? = nil, duration: Double? = nil, report: JobReport? = nil) {
        self.stage = stage; self.frame = frame; self.seconds = seconds; self.duration = duration; self.report = report
    }
    public var fraction: Double {
        let fraction = min(1, max(0, (seconds ?? 0) / max(0.01, duration ?? 1)))
        switch stage {
        case "analyze": return fraction * 0.5
        case "render": return 0.5 + fraction * 0.45
        case "qc": return 0.96
        case "complete", "result": return 1
        default: return 0
        }
    }
}
public struct JobReport: Decodable, Equatable {
    public var output: String
    public var tracks: Int
    public var frames: Int
    public var elapsedSeconds: Double
    enum CodingKeys: String, CodingKey { case output, tracks, frames; case elapsedSeconds = "elapsed_seconds" }
    public init(output: String, tracks: Int, frames: Int, elapsedSeconds: Double) {
        self.output = output; self.tracks = tracks; self.frames = frames; self.elapsedSeconds = elapsedSeconds
    }
}
public protocol BackendRunning {
    func events(source: URL, output: URL, settings: EngineSettings, cancelFile: URL) -> AsyncThrowingStream<BackendEvent, Error>
}

public final class BackendRunner: BackendRunning {
    public let executable: URL?
    public init(executable: URL? = BackendRunner.locateEngine()) { self.executable = executable }
    public static func locateEngine() -> URL? {
        let fm = FileManager.default
        let candidates = [ProcessInfo.processInfo.environment["URL_GUARD_ENGINE"].map { URL(fileURLWithPath: $0) },
                          Bundle.main.resourceURL?.appendingPathComponent("video-qc"),
                          URL(fileURLWithPath: fm.currentDirectoryPath).appendingPathComponent("target/release/video-qc")]
        return candidates.compactMap { $0 }.first { fm.isExecutableFile(atPath: $0.path) }
    }
    public func events(source: URL, output: URL, settings: EngineSettings, cancelFile: URL) -> AsyncThrowingStream<BackendEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.onTermination = { reason in
                if case .cancelled = reason { try? Data().write(to: cancelFile) }
            }
            DispatchQueue.global(qos: .userInitiated).async { [executable] in
                let log = FileManager.default.temporaryDirectory.appendingPathComponent("url-guard-\(UUID().uuidString).log")
                defer { try? FileManager.default.removeItem(at: log) }
                do {
                    guard let executable else { throw BackendError.missingEngine }
                    let process = Process()
                    process.executableURL = executable
                    process.arguments = try settings.arguments(source: source, output: output, cancelFile: cancelFile)
                    let pipe = Pipe()
                    FileManager.default.createFile(atPath: log.path, contents: nil)
                    let errors = try FileHandle(forWritingTo: log)
                    defer { try? errors.close() }
                    process.standardOutput = pipe
                    process.standardError = errors
                    try process.run()
                    var buffer = Data()
                    var parseError: Error?
                    while let data = try pipe.fileHandleForReading.read(upToCount: 65536), !data.isEmpty {
                        buffer.append(data)
                        while let end = buffer.firstIndex(of: 0x0a) {
                            let line = Data(buffer[..<end]); buffer.removeSubrange(...end)
                            if line.isEmpty { continue }
                            do { continuation.yield(try JSONDecoder().decode(BackendEvent.self, from: line)) }
                            catch { parseError = BackendError.malformedEvent; try? Data().write(to: cancelFile) }
                        }
                    }
                    process.waitUntilExit()
                    if process.terminationStatus == 130 { throw BackendError.cancelled }
                    if process.terminationStatus != 0 {
                        let bytes = (try? Data(contentsOf: log)) ?? Data()
                        throw BackendError.process(String(decoding: bytes.suffix(64000), as: UTF8.self))
                    }
                    if let parseError { throw parseError }
                    if !buffer.isEmpty {
                        continuation.yield(try JSONDecoder().decode(BackendEvent.self, from: buffer))
                    }
                    continuation.finish()
                } catch { continuation.finish(throwing: error) }
            }
        }
    }
}
