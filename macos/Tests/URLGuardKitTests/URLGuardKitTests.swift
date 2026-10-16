import XCTest
@testable import URLGuardKit

final class SettingsTests: XCTestCase {
    func testAllMaskSettingsReachRust() throws {
        var settings = EngineSettings(); settings.trackingType = .perspective; settings.feather = 12
        settings.blur = 25; settings.sideways = false; settings.runQC = false
        let args = try settings.arguments(source: URL(fileURLWithPath: "/tmp/My Video.mp4"),
                                          output: URL(fileURLWithPath: "/tmp/Output Folder"),
                                          cancelFile: URL(fileURLWithPath: "/tmp/cancel"))
        XCTAssertEqual(args[1], "/tmp/My Video.mp4")
        XCTAssertEqual(args[args.firstIndex(of: "--tracking-type")! + 1], "perspective")
        XCTAssertEqual(args[args.firstIndex(of: "--feather")! + 1], "12.0")
        XCTAssertTrue(args.contains("--no-sideways")); XCTAssertTrue(args.contains("--no-qc"))
        XCTAssertTrue(args.contains("--json-progress"))
    }
    func testInvalidSettings() {
        var settings = EngineSettings(); settings.feather = -1
        XCTAssertThrowsError(try settings.validate())
        settings = EngineSettings(); settings.blur = .nan
        XCTAssertThrowsError(try settings.validate())
        settings = EngineSettings(); settings.scanInterval = 0
        XCTAssertThrowsError(try settings.validate())
    }
    func testEventProgressAndReport() throws {
        let data = Data(#"{"stage":"result","report":{"output":"/tmp/job","frames":12,"tracks":2,"elapsed_seconds":1.5}}"#.utf8)
        let event = try JSONDecoder().decode(BackendEvent.self, from: data)
        XCTAssertEqual(event.fraction, 1); XCTAssertEqual(event.report?.tracks, 2)
        XCTAssertEqual(BackendEvent(stage: "analyze", seconds: 5, duration: 10).fraction, 0.25)
        XCTAssertEqual(BackendEvent(stage: "render", seconds: 5, duration: 10).fraction, 0.725)
    }
    func testPerspectiveDescription() { XCTAssertTrue(TrackingType.perspective.detail.contains("Four corners")) }
}

private final class FakeBackend: BackendRunning {
    var sources: [URL] = []
    var received: [EngineSettings] = []
    func events(source: URL, output: URL, settings: EngineSettings, cancelFile: URL) -> AsyncThrowingStream<BackendEvent, Error> {
        sources.append(source); received.append(settings)
        return AsyncThrowingStream { continuation in
            continuation.yield(BackendEvent(stage: "analyze", frame: 1, seconds: 1, duration: 2))
            continuation.yield(BackendEvent(stage: "result", report: JobReport(output: output.path, tracks: 2, frames: 12, elapsedSeconds: 0.5)))
            continuation.finish()
        }
    }
}

@MainActor final class ModelTests: XCTestCase {
    var directory: URL!
    override func setUp() async throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }
    override func tearDown() async throws { try FileManager.default.removeItem(at: directory) }
    private func video(_ name: String) throws -> URL {
        let url = directory.appendingPathComponent(name)
        try Data().write(to: url); return url
    }
    func testDropAndBatchDeduplication() throws {
        let backend = FakeBackend(); let model = AppModel(backend: backend)
        let a = try video("one.mp4"), b = try video("two.mov")
        model.batch = true; model.addFiles([a, b, a])
        XCTAssertEqual(model.files, [a, b]); XCTAssertEqual(model.selected, a)
        model.batch = false; model.addFiles([b, a]); XCTAssertEqual(model.files, [b])
    }
    func testRejectInvalidDrop() throws {
        let model = AppModel(backend: FakeBackend())
        model.addFiles([try video("notes.txt"), URL(string: "https://example.com/video.mp4")!, directory])
        XCTAssertTrue(model.files.isEmpty)
        XCTAssertEqual(model.status, BackendError.invalidVideo.localizedDescription)
    }
    func testOutputCollision() throws {
        let source = try video("sample.mp4")
        try FileManager.default.createDirectory(at: directory.appendingPathComponent("sample_qc"), withIntermediateDirectories: true)
        XCTAssertEqual(AppModel.resultFolder(source: source, parent: nil).lastPathComponent, "sample_qc_2")
    }
    func testBatchExecutionAndCapturedSettings() async throws {
        let backend = FakeBackend(); let model = AppModel(backend: backend)
        let a = try video("one.mp4"), b = try video("two.mov")
        model.batch = true; model.addFiles([a, b]); model.settings.trackingType = .perspective; model.settings.feather = 7
        model.start(); model.settings.feather = 13
        for _ in 0..<100 where model.busy { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertFalse(model.busy); XCTAssertEqual(backend.sources, [a, b])
        XCTAssertEqual(backend.received.map(\.feather), [7, 7])
        XCTAssertEqual(model.reports.count, 2); XCTAssertEqual(model.progress, 1); XCTAssertTrue(model.showRender)
    }
    func testMissingEngineError() async throws {
        let model = AppModel(backend: BackendRunner(executable: nil)); model.addFiles([try video("one.mp4")]); model.start()
        for _ in 0..<100 where model.busy { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertFalse(model.busy); XCTAssertTrue(model.status.contains("Rust engine missing"))
    }
    func testSwiftToRustEndToEnd() async throws {
        guard let path = ProcessInfo.processInfo.environment["URL_GUARD_ENGINE"] else {
            throw XCTSkip("Set URL_GUARD_ENGINE to run the real hardware integration")
        }
        let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("tests/fixtures/video/VID_20261012_115842.mp4")
        let model = AppModel(backend: BackendRunner(executable: URL(fileURLWithPath: path)))
        model.outputFolder = directory; model.settings.trackingType = .perspective
        model.settings.feather = 8; model.settings.scanInterval = 16; model.settings.runQC = false
        model.addFiles([source]); model.start()
        for _ in 0..<400 where model.busy { try await Task.sleep(nanoseconds: 100_000_000) }
        XCTAssertFalse(model.busy, "Native job timed out")
        XCTAssertEqual(model.reports.count, 1, model.status)
        XCTAssertEqual(model.reports.first?.frames, 217)
        XCTAssertTrue(model.showRender)
        let output = try XCTUnwrap(model.lastOutput)
        XCTAssertTrue(FileManager.default.fileExists(atPath: output.appendingPathComponent("blurred.mp4").path))
        let data = try Data(contentsOf: output.appendingPathComponent("report.json"))
        let report = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let config = try XCTUnwrap(report["config"] as? [String: Any])
        XCTAssertEqual(config["tracking_type"] as? String, "perspective")
        XCTAssertEqual(config["feather"] as? Double, 8)
    }
}

final class ProcessTests: XCTestCase {
    func testRealProcessFramingAndFailure() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let executable = directory.appendingPathComponent("fake-engine")
        try "#!/bin/sh\nprintf '%s\\n' '{\"stage\":\"analyze\",\"frame\":3,\"seconds\":1,\"duration\":2}' '{\"stage\":\"complete\"}'\n".write(to: executable, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)
        let runner = BackendRunner(executable: executable)
        var events: [BackendEvent] = []
        for try await event in runner.events(source: directory, output: directory, settings: EngineSettings(), cancelFile: directory.appendingPathComponent("cancel")) { events.append(event) }
        XCTAssertEqual(events.map(\.stage), ["analyze", "complete"])
        try "#!/bin/sh\necho 'encoder unavailable' >&2\nexit 1\n".write(to: executable, atomically: true, encoding: .utf8)
        do {
            for try await _ in runner.events(source: directory, output: directory, settings: EngineSettings(), cancelFile: directory.appendingPathComponent("cancel")) {}
            XCTFail("Failure should propagate")
        } catch { XCTAssertTrue(error.localizedDescription.contains("encoder unavailable")) }
    }
}
