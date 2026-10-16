use serde_json::json;
use video_qc::{
    geometry::Quad,
    media::Metadata,
    ocr::Detection,
    store::Store,
    tracking::{Track, Tracker},
    Config, TrackingType,
};

fn metadata(format: &str, transfer: &str) -> Metadata {
    Metadata {
        source: "input.mp4".into(),
        width: 640,
        height: 320,
        rotation: 0,
        fps: "25/1".into(),
        time_base: "1/1000".into(),
        duration: 1.,
        video: json!({"pix_fmt":format,"color_transfer":transfer}),
        audio: vec![],
        frames: 25,
    }
}
#[test]
fn ten_bit_is_rejected_without_explicit_bit_depth() {
    assert!(video_qc::media::validate_sdr(&metadata("yuv420p10le", "bt709")).is_err());
    assert!(video_qc::media::validate_sdr(&metadata("yuv420p", "smpte2084")).is_err());
}
#[test]
fn nv12_and_normal_sdr_are_supported() {
    assert!(video_qc::media::validate_sdr(&metadata("nv12", "bt709")).is_ok());
    assert!(video_qc::media::validate_sdr(&metadata("yuvj420p", "bt709")).is_ok());
}

#[test]
fn config_validation_and_serialized_settings() {
    assert!(Config::default().validate().is_ok());
    for config in [
        Config {
            feather: -1.,
            ..Config::default()
        },
        Config {
            feather: f64::NAN,
            ..Config::default()
        },
        Config {
            scan_interval: 0,
            ..Config::default()
        },
        Config {
            bitrate_mbps: 0.,
            ..Config::default()
        },
    ] {
        assert!(config.validate().is_err());
    }
    let config = Config {
        tracking_type: TrackingType::Perspective,
        feather: 12.,
        ..Config::default()
    };
    let value = serde_json::to_value(config).unwrap();
    assert_eq!(value["tracking_type"], "perspective");
    assert_eq!(value["feather"], 12.);
}
#[test]
fn store_keeps_four_corners_and_gap_frames() {
    let temp = tempfile::tempdir().unwrap();
    let store = Store::new(&temp.path().join("tracks.sqlite")).unwrap();
    let quad = Quad([[20., 30.], [80., 35.], [75., 65.], [25., 60.]]);
    let track = Track {
        id: 1,
        text: "www.example.com".into(),
        confidence: 1.,
        quad,
        last_seen: 0.,
        method: "ocr",
    };
    store.save(&track, 0, 0., quad, "ocr").unwrap();
    store.save(&track, 5, 0.2, quad, "flow").unwrap();
    store.commit().unwrap();
    assert_eq!(store.at(0).unwrap(), vec![quad]);
    assert!(store.at(3).unwrap().is_empty());
    let meta = Metadata {
        source: "input.mp4".into(),
        width: 200,
        height: 100,
        rotation: 0,
        fps: "25/1".into(),
        time_base: "1/1000".into(),
        duration: 1.,
        video: json!({}),
        audio: vec![],
        frames: 25,
    };
    let path = temp.path().join("tracking.json");
    store.export(&path, &meta, &Config::default()).unwrap();
    let value: serde_json::Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
    assert_eq!(value["tracks"][0]["samples"].as_array().unwrap().len(), 2);
    assert_eq!(
        value["tracks"][0]["samples"][0]["quad"],
        serde_json::to_value(quad).unwrap()
    );
    let lua = temp.path().join("masks.lua");
    video_qc::fusion::export(
        &store,
        &lua,
        &meta,
        &Config {
            feather: 8.,
            ..Config::default()
        },
    )
    .unwrap();
    let text = std::fs::read_to_string(lua).unwrap();
    assert!(text.contains("CornerPositioner"));
    assert!(text.contains("SoftEdge',0.04"));
    assert!(text.contains("StepIn=true"));
    assert!(text.contains("BitmapMask"));
}
#[test]
fn tracker_reuses_identity_and_does_not_merge_distinct_urls() {
    let mut tracker = Tracker::default();
    let d = |x| Detection {
        text: "www.example.com".into(),
        confidence: 1.,
        quad: Quad::from_box([x, 20., 80., 30.]),
    };
    assert_eq!(tracker.update(vec![d(20.)], 0.).len(), 1);
    assert!(tracker.update(vec![d(25.)], 0.1).is_empty());
    assert_eq!(tracker.active[0].id, 1);
    assert_eq!(tracker.update(vec![d(25.), d(200.)], 0.2).len(), 1);
    assert_eq!(tracker.active.len(), 2);
}

#[test]
fn negative_ocr_scan_ends_mask_and_reappearance_starts_new_segment() {
    let mut tracker = Tracker::default();
    let detection = || Detection {
        text: "www.example.com".into(),
        confidence: 1.,
        quad: Quad::from_box([20., 20., 80., 30.]),
    };
    assert!(tracker.update(vec![], 0.).is_empty());
    assert!(tracker.active.is_empty());
    let first = tracker.update(vec![detection()], 0.3);
    assert_eq!(first.len(), 1);
    assert_eq!(tracker.active[0].method, "ocr");
    assert!(tracker.update(vec![], 0.6).is_empty());
    assert!(
        tracker.active.is_empty(),
        "Background flow must not survive a negative OCR scan"
    );
    let next = tracker.update(vec![detection()], 0.9);
    assert_eq!(next.len(), 1);
    assert_ne!(first[0].id, next[0].id);
}

#[test]
fn negative_scan_removes_only_the_unconfirmed_url() {
    let mut tracker = Tracker::default();
    let detection = |x| Detection {
        text: "www.example.com".into(),
        confidence: 1.,
        quad: Quad::from_box([x, 20., 80., 30.]),
    };
    tracker.update(vec![detection(20.), detection(200.)], 0.);
    let retained_id = tracker.active[1].id;
    tracker.update(vec![detection(200.)], 0.3);
    assert_eq!(tracker.active.len(), 1);
    assert_eq!(tracker.active[0].id, retained_id);
}
