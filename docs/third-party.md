# Third-party components

The project is MIT licensed. Native processing uses Apple's installed AVFoundation, Vision, Core Image, Metal, VideoToolbox, and Accelerate frameworks. SwiftUI/AVPlayer supply the app interface and preview. No proprietary Resolve executable or SDK bridge binary is redistributed.

OpenCV 4.12 is built from its official source with a minimal module set and linked statically, including its arm64 Carotene/NEON implementation. Rust dependencies are pinned in `Cargo.lock`; they include clap, serde, regex, psl/public suffix data, rusqlite/SQLite, and tempfile. Dependencies retain their own licenses and notices.

FFmpeg is installed separately and used for stream-copy audio, QC, and demonstration comparisons. FFmpeg licensing depends on the installed build. The legacy Python implementation retains its original library requirements; Qt is no longer a dependency of the native app.

The local `.app` is ad-hoc signed for use on the build machine. External distribution needs the appropriate signing, third-party notices, and packaging choices. Test videos are user-provided fixtures; confirm their rights before redistribution.
