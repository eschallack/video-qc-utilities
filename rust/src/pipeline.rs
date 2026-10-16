use crate::{
    config::Config,
    fusion, media,
    native::{self, Reader, Writer},
    ocr, qc,
    store::Store,
    tracking::Tracker,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{fs, path::Path, time::Instant};

#[derive(Serialize, Deserialize, Debug)]
pub struct Report {
    pub schema_version: usize,
    pub source: String,
    pub output: String,
    pub frames: usize,
    pub tracks: usize,
    pub ocr_scans: usize,
    pub tracking_losses: usize,
    pub config: Config,
    pub timings: Value,
    pub elapsed_seconds: f64,
    pub review_required: bool,
    pub acceleration: Value,
}

pub fn process(
    source: &Path,
    output: &Path,
    config: &Config,
    mut progress: impl FnMut(Value),
) -> Result<Report> {
    config.validate()?;
    config.check_cancelled()?;
    if !source.is_file() {
        bail!("Source video does not exist: {}", source.display());
    }
    if output.exists() {
        bail!("Output already exists: {}", output.display());
    }
    let source = source.canonicalize()?;
    let mut meta = media::probe(&source)?;
    media::validate_sdr(&meta)?;
    if meta.width % 2 != 0 || meta.height % 2 != 0 {
        bail!("Rendering requires even video dimensions");
    }
    if !native::metal_available() {
        bail!("Metal unavailable. Run on a Mac with an accessible Metal device.");
    }
    native::set_threads(config.threads);
    let parent = output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let temp = tempfile::Builder::new()
        .prefix(".video-qc-")
        .tempdir_in(parent)?;
    let folder = temp.path();
    let started = Instant::now();
    let analysis_started = Instant::now();
    let store = Store::new(&folder.join("tracking.sqlite"))?;
    let mut reader = Reader::open(&source)?;
    let tw = meta.width / 2;
    let th = meta.height / 2;
    let mut tracker = Tracker::default();
    let mut previous_gray: Option<Vec<u8>> = None;
    let mut origin = None;
    let mut index = 0;
    let mut scans = 0;
    let mut losses = 0;
    while let Some(frame) = reader.next(tw, th)? {
        config.check_cancelled()?;
        let time = frame.pts as f64 / frame.timescale as f64;
        let origin = *origin.get_or_insert(time);
        let seconds = time - origin;
        let cut = previous_gray.as_ref().is_some_and(|previous| {
            previous
                .iter()
                .step_by(31)
                .zip(frame.gray.iter().step_by(31))
                .map(|(a, b)| a.abs_diff(*b) as f64)
                .sum::<f64>()
                / previous.iter().step_by(31).count() as f64
                > 55.
        });
        if cut {
            tracker.active.clear();
            previous_gray = None;
        }
        if let Some(previous) = &previous_gray {
            losses += tracker.advance(previous, &frame.gray, tw, th, seconds, config)?;
        }
        if index % config.scan_interval == 0 || cut {
            let mut detections =
                ocr::detect(&mut reader, meta.width, config.confidence, config.sideways)?;
            for d in &mut detections {
                d.quad = d.quad.scale(0.5);
            }
            // A detection authorizes this frame and subsequent forward tracking.
            // Never project a newly detected mask into unconfirmed earlier frames.
            tracker.update(detections, seconds);
            scans += 1;
        }
        for track in &tracker.active {
            store.save(track, index, seconds, track.quad.scale(2.), track.method)?;
        }
        previous_gray = Some(frame.gray);
        if index % 30 == 0 {
            store.commit()?;
            progress(
                json!({"stage":"analyze","frame":index,"seconds":seconds,"duration":meta.duration}),
            );
        }
        index += 1;
    }
    if index == 0 {
        bail!("No decodable video frames");
    }
    drop(reader);
    drop(previous_gray);
    let analysis_seconds = analysis_started.elapsed().as_secs_f64();
    meta.frames = index;
    store.commit()?;
    store.export(&folder.join("tracking.json"), &meta, config)?;
    fusion::export(&store, &folder.join("masks.fusion.lua"), &meta, config)?;
    let render_started = Instant::now();
    let mut reader = Reader::open(&source)?;
    let silent = folder.join(".video-only.mp4");
    let mut writer = Writer::open(
        &silent,
        meta.width,
        meta.height,
        meta.rate(),
        config.bitrate_mbps,
    )?;
    let mut origin = None;
    let mut rendered = 0;
    while let Some(frame) = reader.next(0, 0)? {
        config.check_cancelled()?;
        let raw = frame.pts as f64 / frame.timescale as f64;
        let origin = *origin.get_or_insert(frame.pts);
        let pts = frame.pts - origin;
        let seconds = pts as f64 / frame.timescale as f64;
        let quads: Vec<_> = store
            .at(rendered)?
            .iter()
            .map(|q| q.padded(config.padding))
            .collect();
        writer.append(
            &reader,
            &quads,
            config.blur_sigma,
            config.feather,
            pts,
            frame.timescale,
        )?;
        if rendered % 30 == 0 {
            progress(
                json!({"stage":"render","frame":rendered,"seconds":seconds,"duration":meta.duration}),
            );
        }
        let _ = raw;
        rendered += 1;
    }
    writer.finish(
        meta.video["duration"]
            .as_str()
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(meta.duration),
    )?;
    drop(writer);
    drop(reader);
    if rendered != index {
        bail!("Frame count changed between analysis and rendering");
    }
    media::mux(&source, &silent, &folder.join("blurred.mp4"), &meta, config)?;
    let render_seconds = render_started.elapsed().as_secs_f64();
    progress(json!({"stage":"qc","frame":0,"seconds":0,"duration":meta.duration}));
    let checks = if config.run_qc {
        qc::inspect(&source, &meta, config)?
    } else {
        json!({"notice":"QC skipped"})
    };
    fs::write(folder.join("qc.json"), serde_json::to_vec_pretty(&checks)?)?;
    let tracks = store
        .db
        .query_row("SELECT COUNT(*) FROM tracks", [], |r| r.get(0))?;
    let report = Report {
        schema_version: 2,
        source: meta.source.clone(),
        output: output.to_string_lossy().into(),
        frames: index,
        tracks,
        ocr_scans: scans,
        tracking_losses: losses,
        config: config.clone(),
        timings: json!({"analysis_seconds":analysis_seconds,"render_seconds":render_seconds,"analysis_fps":index as f64/analysis_seconds}),
        elapsed_seconds: started.elapsed().as_secs_f64(),
        review_required: true,
        acceleration: json!({"ocr":"Apple Vision (system-selected GPU/Neural Engine)","blur":"Core Image / Metal","encoder":"VideoToolbox hardware H.264","tracking":"OpenCV arm64 / NEON"}),
    };
    fs::write(
        folder.join("report.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    drop(store);
    config.check_cancelled()?;
    if output.exists() {
        bail!("Output was created by another job");
    }
    fs::rename(folder, output).context("Cannot publish completed result")?;
    progress(
        json!({"stage":"complete","frame":index,"seconds":meta.duration,"duration":meta.duration}),
    );
    Ok(report)
}
