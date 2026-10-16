# Apple Silicon performance

The native pipeline uses Apple Vision, Metal/Core Image, hardware VideoToolbox H.264, and arm64/NEON OpenCV. It streams frames, tracks at half resolution, stores samples in SQLite, and performs OCR every eight frames by default. SwiftUI owns no processing loop; AVPlayer supplies native video preview.

Measurements from `demos/native/summary.json`, with 6 px feathering and QC enabled:

| Clip | Transform total | Perspective total | Native analysis | Native rendering |
| --- | ---: | ---: | ---: | ---: |
| 217-frame close-up | 13.03 s | 12.55 s | 19.0–19.6 fps | 1.05–1.15 s |
| 192-frame sideways clip | 11.08 s | 10.94 s | 20.2 fps | 1.05–1.21 s |
| 322-frame wide shot | 16.38 s | 16.95 s | 21.5–22.3 fps | 1.39–1.44 s |

Earlier Python totals were 56.03, 46.16, and 77.57 seconds respectively. The native jobs took roughly one quarter of that time on the same local Apple Silicon environment. This is a complete pipeline comparison, including different OCR/render implementations and encoder settings; it is not an isolated Rust-language microbenchmark.

Vision chooses its compute devices. `usesCPUOnly` is disabled; this does not establish that every OCR operation ran on the Neural Engine. Metal and hardware encoding are explicitly selected. No GPU/CPU encoder fallback is silently used.

## Tune

- Increase `--scan-interval` for fewer OCR passes. Brief URLs become easier to miss, and visibility confirmation waits for the next scan. Masks are never backfilled before detection.
- Use `--no-sideways` when text orientation is known.
- Transform is useful for rigid motion; perspective handles planar viewpoint changes and requires stronger feature geometry.
- Adjust `--threads` for OpenCV tracking. Vision manages its own concurrency.
- Set `--bitrate-mbps` for output quality/file-size needs; the native encoder uses a bitrate target rather than the old libx264 CRF.
- Use a low OCR interval for rapid or very short URL appearances.

Batch jobs run sequentially to avoid oversubscribing OCR, video encoders, and GPU buffers. Forward tracking retains only one previous grayscale frame, independently of clip duration. Higher resolution increases GPU/decoder/readback work and frame memory; many simultaneous URLs increase flow work. Disk usage grows with per-frame samples. The measurements above predate removal of backward tracking and remain historical workload measurements.

`target/release/video-qc doctor` checks Metal availability and reports the native backend. Restricted tool sandboxes can deny Metal even when the machine has a GPU; the hardware validation was run with device access.
