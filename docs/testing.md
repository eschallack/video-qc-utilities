# Validation

Local validation uses Python 3.12 on macOS.

Final local result: **48 tests passed**, **89% line coverage**. Ruff checks and formatting passed. Source and wheel distributions were built and their contents checked.

Reproduce:

```sh
uv sync --locked --extra gui
uv run ruff check .
uv run ruff format --check .
uv run pytest -q --cov=video_qc --cov-report=term-missing
```

`ocr` tests run the bundled models against every supplied clip and synthetic upright/sideways text. `integration` tests use FFmpeg and PyAV. `gui` tests use Qt offscreen and a real engine child process. Lua tests use the `lua` interpreter if present; the host validation below covers actual Fusion behavior.

## Meaningful checks

- Variable source frame times survive rendering within 0.1 ms in the synthetic VFR test.
- Rendered frame count equals decoded source frame count.
- Compressed audio packet payload hashes are identical before/after.
- Laplacian edge energy drops inside the URL while a distant colored region remains within encoding tolerance.
- Known translation moves the optical-flow box by the expected amount.
- New detections backfill earlier frames through backward flow.
- Empty detection sets yield no tracks and a playable output.
- Cancellation removes staged outputs and terminates child media processes.
- FFmpeg recognizes known black/frozen/silent synthetic intervals.
- URL detection in a sentence excludes surrounding words using OCR character boxes.
- The CLI emits valid newline-delimited JSON, errors correctly, and accepts cancellation markers.
- Desktop jobs complete with a playable render; desktop cancellation publishes no result.
- Fusion coordinates flip Y correctly, padding matches rendering, stepped keys disable gaps, and the blur chain connects to MediaOut.

Each supplied demonstration was also decoded again to compare its frame count and presentation times with the source. Audio payload and timestamp comparisons are recorded in `demos/verification.json`. Comparisons are full renders, not still-image simulations.

## Live Resolve

Resolve **21.0.1.11** was launched and accessed with the installed `fuscript` interpreter. A hidden temporary composition received Background → MediaOut, then the generated importer through `Composition.RunScript`. The check verified actual tool creation, Center `(0.2025, 0.645)`, Level values `1, 1, 0, 1, 0` at frames `0, 1, 3, 5, 6`, and final MediaOut wiring. The composition was closed.

`demos/resolve-host-validation.txt` records this check. The built Python panel also loaded in Resolve; its Scan, Masks, and Status controls were inspected before closing. This is recorded in `demos/resolve-panel-validation.txt`. A Lua contract harness runs in pytest; it does not substitute for the real host check. The panel's complete clip workflow still needs interactive acceptance, particularly timeline transforms/retiming and Windows installation.

CI is configured on Ubuntu, macOS, and Windows. This local run does not establish that remote CI has passed. Linux CI runs engine tests; desktop UI targets macOS/Windows.
