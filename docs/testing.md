# Native validation

The current suite covers three layers: Rust core/native media, Swift app state/process integration, and the preserved Python compatibility engine. Hardware tests ran with actual Metal/VideoToolbox access.

Final local results: **22 Rust tests**, **13 Swift tests** including the real hardware integration and native preview regression tests, and **50 Python compatibility tests** passed. Cargo fmt, Clippy with warnings denied, Ruff checks/formatting, and the app's code-signature verification passed.

```sh
cargo test --locked -- --test-threads=1
cargo clippy --all-targets --locked -- -D warnings
cargo fmt --check
URL_GUARD_ENGINE="$PWD/target/release/video-qc" swift test --package-path macos
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

## What is checked

Rust tests validate known rotation/scale/translation and known projective warps. Perspective corners are compared with the ground-truth homography and must change independently. Blank tracking frames fail without drifting. Geometry tests cover padding, overlap, convexity, and invalid coordinates. Contract tests preserve polygon coordinates, gaps, settings, and identity association.

Real media tests decode/render a provided fixture through Apple frameworks. They check orientation, frame counts, variable presentation times, copied audio hashes/timestamps, reduced edge energy inside a URL, and unchanged distant pixels within encoding tolerance. A separate Metal test renders hard and feathered masks and compares edge/distant pixels. Cancellation tests verify no incomplete results or staging folders survive.

An appearing/disappearing URL regression uses a persistent textured background so optical flow remains possible without the text. In both transform and perspective modes, samples begin on the first positive OCR scan, negative scans stop masking, and reappearance starts a new segment. A scan interval of one confirms that every masked frame has an OCR detection and no mask survives the exact disappearance frame. Rendered background detail before detection and blur after detection are checked; Fusion exports use the same samples and stepped visibility keys.

Swift tests check mask settings reaching Rust, invalid settings, progress/report decoding, file acceptance, batch deduplication, output collisions, settings snapshots, subprocess framing/errors, and missing-engine handling. With `URL_GUARD_ENGINE`, a real Swift AppModel → process runner → Rust → Metal render is produced and its settings/output verified.

Native preview regression tests mount a real SwiftUI hosting window, import a supplied video after the empty drop state, await decoder readiness, play it, and switch sources. They also verify player replacement reuses the AppKit view and teardown detaches it. Earlier model-only import tests did not instantiate the video view and missed a macOS 15.3.1 / Swift 5.9.2 runtime abort: `failed to demangle superclass of VideoPlayerView`. The preview now embeds AppKit `AVPlayerView` directly, preserving native playback controls without the failing SwiftUI `VideoPlayer` overlay.

Python tests retain prior OCR/media/CLI regression coverage. The primary Python launcher is separately tested to forward paths and perspective/feather settings to the Rust executable. Qt is no longer used.

## Fixture verification

All three supplied clips were rendered in transform and perspective modes. `demos/native/verification.json` independently compares decoded video presentation times and compressed audio packet payloads/timestamps against each source. All six have matching frame counts, zero reported video timestamp error, and identical audio data/timing.

Comparisons are actual rendered movies. The source is left, native result right. The full-resolution `blurred.mp4` preserves the source timing; resized comparison movies are review artifacts.

## Live Resolve and UI

The new importer ran through `Composition.RunScript` in a hidden temporary Fusion composition on Resolve **21.0.1.11**. CornerPositioner, BitmapMask, and Blur nodes were created. All four animated corner inputs, Alpha channel, 6/1280 normalized feather, enabled mask level, and MediaOut connections were checked. The temporary composition was closed; no existing timeline was edited. Evidence: `demos/native/resolve-validation.txt`.

The release Swift `.app` was launched and its own native view was captured without screen-recording APIs. The sidebar, drag/drop target, tracking selector, feather controls, and output/render steps are visible in `demos/native/swift-ui.png`. Preview mounting and actual playback are now automated. OS file dialogs, physical drag gestures, and transport-button interactions still merit interactive acceptance.

CI runs native tests/builds on macOS and compatibility checks separately. These local results do not claim that a remote CI run has completed. This native media adapter is macOS-only.
