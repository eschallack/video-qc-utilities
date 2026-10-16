#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPS="$ROOT/.native/opencv"
if [ -f "$DEPS/install/lib/libopencv_video.a" ]; then exit 0; fi
mkdir -p "$DEPS"
curl --fail --location --retry 3 https://github.com/opencv/opencv/archive/refs/tags/4.12.0.tar.gz -o "$DEPS/source.tar.gz"
tar -xzf "$DEPS/source.tar.gz" -C "$DEPS"
cmake -S "$DEPS/opencv-4.12.0" -B "$DEPS/build" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$DEPS/install" -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_LIST=core,imgproc,video,calib3d -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF \
  -DBUILD_EXAMPLES=OFF -DBUILD_opencv_apps=OFF -DBUILD_opencv_python2=OFF -DBUILD_opencv_python3=OFF \
  -DWITH_IPP=OFF -DWITH_ITT=OFF -DWITH_OPENCL=OFF -DWITH_LAPACK=OFF \
  -DWITH_TBB=OFF -DWITH_FFMPEG=OFF -DWITH_AVFOUNDATION=OFF -DWITH_PROTOBUF=OFF \
  -DBUILD_JAVA=OFF -DBUILD_opencv_dnn=OFF -DOPENCV_GENERATE_PKGCONFIG=ON
cmake --build "$DEPS/build" --parallel 4
cmake --install "$DEPS/build"
