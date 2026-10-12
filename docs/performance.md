# Performance

The default favors finding tilted camera text. It performs two OCR orientations every eight frames, then tracks between scans. It is an offline CPU pipeline, not a real-time filter.

Actual fixture timings are saved in `demos/summary.json` and each bundle's `report.json`. Results include decode, OCR, tracking, rendering, and QC. The first default benchmark overlapped with a fast-profile job, so these are workload measurements rather than isolated hardware comparisons.

The earlier upright-only benchmark on `VID_20261012_115842.mp4` processed 217 frames with 14 OCR scans. Analysis took 15.89 seconds; the complete job took 29.33 seconds. The corresponding default used 28 scans with two orientations each, taking roughly 43 seconds for analysis. This measurement preceded character-level mask refinement; `demos/fast-benchmark.json` records its exact settings.

## Tune

| Setting | Effect and tradeoff |
| --- | --- |
| `--scan-interval 16` | Half as many OCR scans; brief appearances are easier to miss |
| `--no-sideways` | One orientation; intended for known upright titles |
| `--ocr-max-side 960` | Smaller OCR images; reduced recall for small text |
| `--threads 4` | More ONNX/encoder CPU threads; benchmark on your hardware |
| `--preset veryfast` | Faster H.264 encoding, typically larger files at the same CRF |
| `--scan-interval 1` | Dense OCR for critical brief text; highest CPU cost |

When integrating with a native application, keep a detector session alive and inject it into successive `process` calls to reuse model initialization. Each job still receives fresh tracking state. Limit the number of concurrent jobs; ONNX, codecs, and the OS already use workers.

## Bounded work

- Decode and render sequentially; the complete clip is never loaded into RAM.
- Track at half resolution with at most 60 corner features per region.
- Retain a configurable grayscale lookback window, one second by default.
- Keep samples in indexed SQLite and stream exports.
- Blur only URL regions; mask overlaps read from the original frame.
- Reuse ONNX models and set explicit ONNX/encoder thread counts.
- Copy audio without re-encoding.

Four-K footage increases decode/render cost and grayscale history memory. Large numbers of text regions increase OCR and tracking work. Long files increase disk usage, not the number of buffered frames. SQLite still stores one sample per active track per frame; plan output storage accordingly.

GPU OCR/encoding are not enabled in this build. The detector protocol permits an optimized backend without replacing the pipeline. Preserve the coordinate and timestamp contract when adding one. A hardware encoder should have its own quality/timing tests before replacing libx264.
