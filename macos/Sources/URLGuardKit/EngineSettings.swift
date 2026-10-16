import Foundation

public enum TrackingType: String, CaseIterable, Codable, Identifiable {
    case transform, perspective
    public var id: String { rawValue }
    public var title: String { rawValue.capitalized }
    public var detail: String {
        self == .transform ? "Translation, rotation and scale" : "Four corners follow a changing plane"
    }
}

public struct EngineSettings: Equatable, Codable {
    public var trackingType: TrackingType = .transform
    public var feather: Double = 4
    public var blur: Double = 18
    public var padding: Double = 10
    public var scanInterval: Int = 8
    public var confidence: Double = 0.45
    public var threads: Int = 2
    public var bitrate: Double = 12
    public var sideways = true
    public var runQC = true
    public init() {}

    public func validate() throws {
        guard (1...120).contains(scanInterval), (1...64).contains(threads),
              [feather, blur, padding, confidence, bitrate].allSatisfy(\.isFinite),
              (0...100).contains(feather), (0.1...100).contains(blur),
              (0...100).contains(padding), (0...1).contains(confidence),
              (1...100).contains(bitrate) else { throw BackendError.invalidSettings }
    }

    public func arguments(source: URL, output: URL, cancelFile: URL) throws -> [String] {
        try validate()
        var args = ["blur", source.path, "--output", output.path,
                    "--tracking-type", trackingType.rawValue, "--feather", String(feather),
                    "--sigma", String(blur), "--padding", String(padding),
                    "--scan-interval", String(scanInterval), "--confidence", String(confidence),
                    "--threads", String(threads), "--bitrate-mbps", String(bitrate),
                    "--cancel-file", cancelFile.path, "--json-progress"]
        if !sideways { args.append("--no-sideways") }
        if !runQC { args.append("--no-qc") }
        return args
    }
}

public enum BackendError: LocalizedError, Equatable {
    case missingEngine, invalidSettings, invalidVideo, cancelled, process(String), malformedEvent
    public var errorDescription: String? {
        switch self {
        case .missingEngine: return "Rust engine missing. Build the native app with scripts/build_macos.sh."
        case .invalidSettings: return "A mask or processing setting is outside its supported range."
        case .invalidVideo: return "Choose a local video file."
        case .cancelled: return "Cancelled."
        case .process(let detail): return detail
        case .malformedEvent: return "The engine returned an invalid progress event."
        }
    }
}
