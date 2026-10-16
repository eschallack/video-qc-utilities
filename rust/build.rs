use std::{env, path::PathBuf};

fn main() {
    println!("cargo:rerun-if-changed=rust/native/apple.mm");
    println!("cargo:rerun-if-changed=rust/native/tracking.cpp");
    println!("cargo:rerun-if-env-changed=VIDEO_QC_OPENCV_DIR");
    if env::var("CARGO_CFG_TARGET_OS").unwrap() != "macos" {
        return;
    }
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let cv = env::var_os("VIDEO_QC_OPENCV_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join(".native/opencv/install"));
    assert!(
        cv.join("include/opencv4").exists(),
        "Run bash scripts/build_native_deps.sh first"
    );
    cc::Build::new()
        .cpp(true)
        .flag("-std=c++17")
        .flag("-fobjc-arc")
        .flag("-mmacosx-version-min=13.0")
        .file("rust/native/apple.mm")
        .compile("qc_apple");
    cc::Build::new()
        .cpp(true)
        .flag("-std=c++17")
        .include(cv.join("include/opencv4"))
        .file("rust/native/tracking.cpp")
        .compile("qc_tracking");
    println!(
        "cargo:rustc-link-search=native={}",
        cv.join("lib").display()
    );
    println!(
        "cargo:rustc-link-search=native={}",
        cv.join("lib/opencv4/3rdparty").display()
    );
    for lib in [
        "opencv_video",
        "opencv_calib3d",
        "opencv_features2d",
        "opencv_flann",
        "opencv_imgproc",
        "opencv_core",
    ] {
        println!("cargo:rustc-link-lib=static={lib}");
    }
    if cv.join("lib/opencv4/3rdparty/libtegra_hal.a").exists() {
        println!("cargo:rustc-link-lib=static=tegra_hal");
    }
    println!("cargo:rustc-link-lib=z");
    for framework in [
        "Foundation",
        "AVFoundation",
        "CoreMedia",
        "CoreVideo",
        "CoreImage",
        "Vision",
        "Metal",
        "VideoToolbox",
        "Accelerate",
        "CoreGraphics",
        "ImageIO",
    ] {
        println!("cargo:rustc-link-lib=framework={framework}");
    }
    println!("cargo:rustc-link-lib=c++");
}
