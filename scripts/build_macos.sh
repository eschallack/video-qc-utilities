#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
bash scripts/build_native_deps.sh
cargo build --release --locked
swift build --package-path macos --configuration release --disable-sandbox
BIN="$(swift build --package-path macos --configuration release --show-bin-path)"
APP="$ROOT/dist/URL Guard.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN/URLGuard" "$APP/Contents/MacOS/URLGuard"
cp target/release/video-qc "$APP/Contents/Resources/video-qc"
cp macos/Info.plist "$APP/Contents/Info.plist"
cp LICENSE "$APP/Contents/Resources/LICENSE"
codesign --force --deep --sign - "$APP"
echo "$APP"
