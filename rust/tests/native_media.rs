#![cfg(target_os = "macos")]
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use video_qc::{
    geometry::Quad,
    media,
    native::{self, Reader, Writer},
    process, Config, TrackingType,
};

fn hardware() -> bool {
    let available = native::metal_available();
    if !available {
        eprintln!("Metal unavailable: run hardware tests outside the restricted sandbox");
    }
    available
}
fn fixture() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/video/VID_20261012_115842.mp4")
}
fn probe_frames(p: &Path) -> Vec<f64> {
    let out = Command::new(media::tool("ffprobe"))
        .args([
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "json",
        ])
        .arg(p)
        .output()
        .unwrap();
    let d: Value = serde_json::from_slice(&out.stdout).unwrap();
    d["frames"]
        .as_array()
        .unwrap()
        .iter()
        .map(|f| {
            f["best_effort_timestamp_time"]
                .as_str()
                .unwrap()
                .parse()
                .unwrap()
        })
        .collect()
}
fn audio(p: &Path) -> Value {
    let out = Command::new(media::tool("ffprobe"))
        .args([
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_packets",
            "-show_data_hash",
            "sha256",
            "-show_entries",
            "packet=data_hash,pts_time",
            "-of",
            "json",
        ])
        .arg(p)
        .output()
        .unwrap();
    serde_json::from_slice(&out.stdout).unwrap()
}
fn rgb(p: &Path, time: &str) -> Vec<u8> {
    let out = Command::new(media::tool("ffmpeg"))
        .args(["-v", "error", "-ss", time, "-i"])
        .arg(p)
        .args(["-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        .output()
        .unwrap();
    assert!(out.status.success());
    out.stdout
}
fn energy(image: &[u8], width: usize, b: [usize; 4]) -> f64 {
    let [x, y, w, h] = b;
    let mut sum = 0.;
    let mut count = 0;
    for yy in y + 1..y + h - 1 {
        for xx in x + 1..x + w - 1 {
            let i = (yy * width + xx) * 3;
            let v = 4. * image[i] as f64
                - image[i - 3] as f64
                - image[i + 3] as f64
                - image[i - width * 3] as f64
                - image[i + width * 3] as f64;
            sum += v * v;
            count += 1;
        }
    }
    sum / count as f64
}

#[test]
fn hardware_pipeline_preserves_vfr_audio_orientation_and_blurs() {
    if !hardware() {
        return;
    }
    let temp = tempfile::tempdir().unwrap();
    let out = temp.path().join("result");
    let source = fixture();
    let config = Config {
        tracking_type: TrackingType::Perspective,
        feather: 6.,
        run_qc: false,
        ..Config::default()
    };
    let mut stages = Vec::new();
    let report = process(&source, &out, &config, |e| {
        stages.push(e["stage"].as_str().unwrap().to_owned())
    })
    .unwrap();
    assert_eq!(report.frames, 217);
    assert!(report.tracks >= 2);
    assert_eq!(report.config.tracking_type, TrackingType::Perspective);
    assert_eq!(stages.last().unwrap(), "complete");
    let rendered = out.join("blurred.mp4");
    let meta = media::probe(&rendered).unwrap();
    assert_eq!((meta.width, meta.height, meta.rotation), (1280, 720, 0));
    let a = probe_frames(&source);
    let b = probe_frames(&rendered);
    assert_eq!(a.len(), b.len());
    for (x, y) in a.iter().zip(&b) {
        assert!(
            (x - y).abs() < 0.00001,
            "Presentation timestamp changed: {x} vs {y}"
        );
    }
    assert_eq!(audio(&source), audio(&rendered));
    let original = rgb(&source, "2");
    let blurred = rgb(&rendered, "2");
    let original_energy = energy(&original, 1280, [540, 50, 390, 50]);
    assert!(energy(&blurred, 1280, [540, 50, 390, 50]) < original_energy * 0.2);
    let error: f64 = (300..400)
        .flat_map(|y| (0..100).map(move |x| (y * 1280 + x) * 3))
        .map(|i| (original[i] as f64 - blurred[i] as f64).abs())
        .sum::<f64>()
        / 10000.;
    assert!(
        error < 10.,
        "Orientation/color/locality changed outside the mask: {error}"
    );
    let tracking: Value =
        serde_json::from_slice(&fs::read(out.join("tracking.json")).unwrap()).unwrap();
    assert_eq!(tracking["schema_version"], 2);
    assert!(tracking["tracks"][0]["samples"][0]["quad"].is_array());
    assert!(fs::read_to_string(out.join("masks.fusion.lua"))
        .unwrap()
        .contains("CornerPositioner"));
}

fn synthetic(path: &Path) {
    let status=Command::new(media::tool("ffmpeg")).args(["-v","error","-f","lavfi","-i","color=c=white:s=640x320:r=12:d=1",
        "-vf","drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text=www.example.com:fontsize=32:fontcolor=black:x=60:y=100",
        "-c:v","libx264","-threads","1","-y"]).arg(path).status().unwrap();
    assert!(status.success());
}

#[test]
fn masks_start_at_detection_and_stay_off_across_negative_scans() {
    if !hardware() {
        return;
    }
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("appearing-url.mp4");
    // Persistent background corners deliberately remain trackable without text.
    // The URL appears between scans, disappears, and then returns.
    let status = Command::new(media::tool("ffmpeg"))
        .args([
            "-v", "error", "-f", "lavfi", "-i",
            "color=c=white:s=640x320:r=12:d=4",
            "-vf",
            "drawgrid=w=10:h=10:t=1:c=gray@0.3,drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text=www.example.com:fontsize=40:fontcolor=black:x=100:y=120:enable='between(n,5,19)+between(n,29,39)'",
            "-c:v", "libx264", "-threads", "1", "-y",
        ])
        .arg(&input)
        .status()
        .unwrap();
    assert!(status.success());
    for (mode, scan_interval) in [
        (TrackingType::Transform, 8),
        (TrackingType::Perspective, 8),
        (TrackingType::Transform, 1),
    ] {
        let out = temp.path().join(format!("{mode:?}-{scan_interval}"));
        let config = Config {
            scan_interval,
            tracking_type: mode,
            sideways: false,
            run_qc: false,
            ..Config::default()
        };
        process(&input, &out, &config, |_| {}).unwrap();
        let tracking: Value =
            serde_json::from_slice(&fs::read(out.join("tracking.json")).unwrap()).unwrap();
        let tracks = tracking["tracks"].as_array().unwrap();
        assert!(
            tracks.len() >= 2,
            "Both appearances must be detected: {tracking}"
        );
        let mut frames = Vec::new();
        for track in tracks {
            let samples = track["samples"].as_array().unwrap();
            assert_eq!(
                samples[0]["method"], "ocr",
                "A mask must begin at a detection"
            );
            for sample in samples {
                assert_ne!(sample["method"], "backfill");
                if scan_interval == 1 {
                    assert_eq!(
                        sample["method"], "ocr",
                        "Every mask frame must have a detection"
                    );
                }
                frames.push(sample["frame"].as_u64().unwrap());
            }
        }
        assert_eq!(
            frames.iter().min(),
            Some(&(if scan_interval == 1 { 5 } else { 8 })),
            "No masking before the first positive scan"
        );
        assert!(frames.contains(&16));
        assert!(frames.contains(&32));
        assert!(
            frames.iter().all(|f| {
                let gap = if scan_interval == 1 { 20..29 } else { 24..32 };
                !gap.contains(f) && *f < 40
            }),
            "Negative OCR scans must stop masking: {frames:?}"
        );
        // Persistent grid texture makes an early mask measurable in the render.
        let rendered = out.join("blurred.mp4");
        let original = rgb(&input, "0.25");
        let before = rgb(&rendered, "0.25");
        let region = [100, 120, 350, 45];
        assert!(
            energy(&before, 640, region) > energy(&original, 640, region) * 0.75,
            "The render must preserve background detail before detection"
        );
        let original = rgb(&input, "1");
        let after = rgb(&rendered, "1");
        assert!(
            energy(&after, 640, region) < energy(&original, 640, region) * 0.4,
            "A detected URL must actually be blurred"
        );
        let lua = fs::read_to_string(out.join("masks.fusion.lua")).unwrap();
        assert!(lua.contains("levels[t-1]={0,Flags={StepIn=true}}"));
        assert!(lua.contains("levels[t+1]={0,Flags={StepIn=true}}"));
    }
}
fn render_mask(source: &Path, out: &Path, feather: f64) {
    let mut r = Reader::open(source).unwrap();
    let mut w = Writer::open(out, 640, 320, 12., 12.).unwrap();
    while let Some(frame) = r.next(0, 0).unwrap() {
        w.append(
            &r,
            &[Quad::from_box([65., 90., 240., 45.])],
            18.,
            feather,
            frame.pts,
            frame.timescale,
        )
        .unwrap();
    }
    w.finish(1.).unwrap();
}
#[test]
fn actual_metal_feather_changes_edges_and_preserves_distant_pixels() {
    if !hardware() {
        return;
    }
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("input.mp4");
    synthetic(&input);
    let hard = temp.path().join("hard.mp4");
    let soft = temp.path().join("soft.mp4");
    render_mask(&input, &hard, 0.);
    render_mask(&input, &soft, 10.);
    let a = rgb(&hard, "0.2");
    let b = rgb(&soft, "0.2");
    let edge = (95..135)
        .flat_map(|y| (55..80).map(move |x| (y * 640 + x) * 3))
        .map(|i| (a[i] as f64 - b[i] as f64).abs())
        .sum::<f64>()
        / 1000.;
    assert!(edge > 1., "Feather must alter edge alpha: {edge}");
    let far = (20..50)
        .flat_map(|y| (20..50).map(move |x| (y * 640 + x) * 3))
        .map(|i| (a[i] as f64 - b[i] as f64).abs())
        .sum::<f64>()
        / 900.;
    assert!(far < 2.);
}
#[test]
fn cancelled_and_existing_jobs_do_not_publish() {
    let temp = tempfile::tempdir().unwrap();
    let source = fixture();
    let output = temp.path().join("cancelled");
    let marker = temp.path().join("marker");
    fs::write(&marker, "").unwrap();
    let config = Config {
        cancel_file: Some(marker),
        ..Config::default()
    };
    assert!(process(&source, &output, &config, |_| {})
        .unwrap_err()
        .to_string()
        .contains("cancelled"));
    assert!(!output.exists());
    fs::create_dir(&output).unwrap();
    assert!(process(&source, &output, &Config::default(), |_| {})
        .unwrap_err()
        .to_string()
        .contains("already exists"));
}
#[test]
fn cancellation_after_analysis_cleans_staging() {
    if !hardware() {
        return;
    }
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("input.mp4");
    synthetic(&input);
    let output = temp.path().join("cancelled");
    let marker = temp.path().join("marker");
    let config = Config {
        cancel_file: Some(marker.clone()),
        ..Config::default()
    };
    let result = process(&input, &output, &config, |event| {
        if event["stage"] == "analyze" {
            fs::write(&marker, "").unwrap();
        }
    });
    assert!(result.unwrap_err().to_string().contains("cancelled"));
    assert!(!output.exists());
    assert!(!fs::read_dir(temp.path()).unwrap().any(|e| e
        .unwrap()
        .file_name()
        .to_string_lossy()
        .starts_with(".video-qc-")));
}
