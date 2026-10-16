import XCTest
import SwiftUI
import AVKit
@testable import URLGuardKit

private struct ImportPreview: View {
    @ObservedObject var model: AppModel
    var body: some View {
        if model.selected != nil { NativeVideoPreview(player: model.player) }
        else { Text("Drop a video") }
    }
}

@MainActor final class NativeVideoPreviewTests: XCTestCase {
    private func playerView(in view: NSView) -> AVPlayerView? {
        if let player = view as? AVPlayerView { return player }
        return view.subviews.compactMap { playerView(in: $0) }.first
    }

    private func fixture(_ name: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("tests/fixtures/video/\(name)")
    }

    private func window<Content: View>(hosting content: Content) -> (NSWindow, NSHostingView<Content>) {
        _ = NSApplication.shared
        let host = NSHostingView(rootView: content)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 400),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.orderFront(nil)
        host.layoutSubtreeIfNeeded()
        return (window, host)
    }

    func testImportMountsPreviewAndPlaysThenSwitchesSource() async throws {
        let model = AppModel()
        let (window, host) = window(hosting: ImportPreview(model: model))
        defer { model.stopPlayback(); window.close() }
        XCTAssertNil(playerView(in: host))

        let first = fixture("VID_20261012_115842.mp4")
        model.addFiles([first])
        // Await SwiftUI's real update cycle. Model-only tests missed the original abort.
        for _ in 0..<100 where playerView(in: host) == nil {
            try await Task.sleep(nanoseconds: 20_000_000)
            host.layoutSubtreeIfNeeded()
        }
        let view = try XCTUnwrap(playerView(in: host))
        XCTAssertTrue(view.player === model.player)
        XCTAssertEqual(view.controlsStyle, .inline)
        XCTAssertEqual(view.videoGravity, .resizeAspect)
        let item = try XCTUnwrap(model.player.currentItem)
        for _ in 0..<200 where item.status == .unknown {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertEqual(item.status, .readyToPlay, item.error?.localizedDescription ?? "Preview did not become ready")
        model.player.play()
        for _ in 0..<100 where model.player.currentTime().seconds < 0.1 {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertGreaterThan(model.player.currentTime().seconds, 0)

        let second = fixture("VID_20261012_115856.mp4")
        model.addFiles([second])
        try await Task.sleep(nanoseconds: 50_000_000)
        XCTAssertTrue(playerView(in: host) === view)
        XCTAssertEqual((model.player.currentItem?.asset as? AVURLAsset)?.url, second)
        XCTAssertEqual(model.player.rate, 0)
    }

    func testPreviewUpdatesPlayerWithoutRecreatingNativeView() async throws {
        let first = AVPlayer(), second = AVPlayer()
        let (window, host) = window(hosting: NativeVideoPreview(player: first))
        defer { window.close() }
        let view = try XCTUnwrap(playerView(in: host))
        XCTAssertTrue(view.player === first)
        host.rootView = NativeVideoPreview(player: second)
        for _ in 0..<100 where view.player !== second {
            try await Task.sleep(nanoseconds: 20_000_000)
            host.layoutSubtreeIfNeeded()
        }
        XCTAssertTrue(playerView(in: host) === view)
        XCTAssertTrue(view.player === second)
        NativeVideoPreview.dismantleNSView(view, coordinator: ())
        XCTAssertNil(view.player)
    }
}
