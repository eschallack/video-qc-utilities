import SwiftUI
import AVKit

/// Use AppKit's player directly. The SwiftUI VideoPlayer overlay can abort when
/// resolving its AVPlayerView superclass on macOS 15 with the Swift 5.9 SDK.
@MainActor public struct NativeVideoPreview: NSViewRepresentable {
    public let player: AVPlayer

    public init(player: AVPlayer) { self.player = player }

    public func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .inline
        view.videoGravity = .resizeAspect
        view.player = player
        return view
    }

    public func updateNSView(_ view: AVPlayerView, context: Context) {
        // Changing zoom or progress must not recreate the player or reset playback.
        if view.player !== player { view.player = player }
    }

    public static func dismantleNSView(_ view: AVPlayerView, coordinator: ()) {
        view.player = nil
    }
}
