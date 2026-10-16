use crate::config::Config;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::Duration,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Metadata {
    pub source: String,
    pub width: usize,
    pub height: usize,
    pub rotation: i32,
    pub fps: String,
    pub time_base: String,
    pub duration: f64,
    pub video: Value,
    pub audio: Vec<Value>,
    pub frames: usize,
}
impl Metadata {
    pub fn rate(&self) -> f64 {
        let p: Vec<_> = self.fps.split('/').collect();
        p[0].parse::<f64>().unwrap_or(30.)
            / p.get(1).and_then(|x| x.parse::<f64>().ok()).unwrap_or(1.)
    }
}
pub fn tool(name: &str) -> PathBuf {
    // Finder-launched apps do not inherit the user's shell PATH.
    for root in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"] {
        let p = Path::new(root).join(name);
        if p.is_file() {
            return p;
        }
    }
    PathBuf::from(name)
}
pub fn probe(source: &Path) -> Result<Metadata> {
    let result = Command::new(tool("ffprobe"))
        .args([
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
        ])
        .arg(source)
        .output()
        .context("Install FFmpeg (ffmpeg and ffprobe)")?;
    if !result.status.success() {
        bail!("ffprobe: {}", String::from_utf8_lossy(&result.stderr));
    }
    let value: Value = serde_json::from_slice(&result.stdout)?;
    let streams = value["streams"].as_array().context("No streams")?;
    let video = streams
        .iter()
        .find(|s| s["codec_type"] == "video" && s["disposition"]["attached_pic"] != 1)
        .context("No video stream")?
        .clone();
    let rotation = video["side_data_list"]
        .as_array()
        .and_then(|a| a.iter().find_map(|s| s["rotation"].as_i64()))
        .unwrap_or(0) as i32;
    if rotation % 90 != 0 {
        bail!("Only right-angle display rotation is supported");
    }
    let mut width = video["width"].as_u64().context("Missing width")? as usize;
    let mut height = video["height"].as_u64().context("Missing height")? as usize;
    if rotation % 180 != 0 {
        std::mem::swap(&mut width, &mut height);
    }
    let duration = value["format"]["duration"]
        .as_str()
        .context("Missing duration")?
        .parse::<f64>()?;
    let meta = Metadata {
        source: source.canonicalize()?.to_string_lossy().to_string(),
        width,
        height,
        rotation,
        fps: video["avg_frame_rate"].as_str().unwrap_or("30/1").into(),
        time_base: video["time_base"].as_str().unwrap_or("1/90000").into(),
        duration,
        audio: streams
            .iter()
            .filter(|s| s["codec_type"] == "audio")
            .cloned()
            .collect(),
        video,
        frames: 0,
    };
    if !meta.rate().is_finite() || meta.rate() <= 0. {
        bail!("Invalid source frame rate");
    }
    Ok(meta)
}

pub fn validate_sdr(meta: &Metadata) -> Result<()> {
    let depth = meta.video["bits_per_raw_sample"]
        .as_str()
        .unwrap_or("8")
        .parse::<usize>()
        .unwrap_or(8);
    let format = meta.video["pix_fmt"].as_str().unwrap_or("");
    let eight_bit = [
        "yuv420p", "yuvj420p", "yuv422p", "yuvj422p", "yuv444p", "yuvj444p", "yuv411p", "yuv410p",
        "nv12", "nv21", "rgb24", "bgr24", "rgba", "bgra", "argb", "abgr", "gbrp", "gray", "gray8",
        "pal8", "uyvy422", "yuyv422",
    ];
    if depth > 8
        || !eight_bit.contains(&format)
        || ["smpte2084", "arib-std-b67"]
            .contains(&meta.video["color_transfer"].as_str().unwrap_or(""))
    {
        bail!("Rendering supports 8-bit SDR; export a color-managed SDR intermediate");
    }
    Ok(())
}
pub fn run(command: &mut Command, config: &Config) -> Result<(String, String)> {
    let out = tempfile::tempfile()?;
    let err = tempfile::tempfile()?;
    let mut child = command
        .stdout(Stdio::from(out.try_clone()?))
        .stderr(Stdio::from(err.try_clone()?))
        .spawn()?;
    let status = loop {
        if let Err(e) = config.check_cancelled() {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
        if let Some(status) = child.try_wait()? {
            break status;
        }
        thread::sleep(Duration::from_millis(25));
    };
    let mut stdout = String::new();
    let mut stderr = String::new();
    use std::io::{Seek, SeekFrom};
    let mut out = out;
    let mut err = err;
    out.seek(SeekFrom::Start(0))?;
    err.seek(SeekFrom::Start(0))?;
    out.read_to_string(&mut stdout)?;
    err.read_to_string(&mut stderr)?;
    if !status.success() {
        bail!("Media command failed: {stderr}");
    }
    Ok((stdout, stderr))
}
pub fn mux(
    source: &Path,
    video: &Path,
    output: &Path,
    metadata: &Metadata,
    config: &Config,
) -> Result<()> {
    let offset = -metadata.video["start_time"]
        .as_str()
        .unwrap_or("0")
        .parse::<f64>()
        .unwrap_or(0.);
    run(
        Command::new(tool("ffmpeg"))
            .args(["-v", "error", "-y", "-copyts", "-i"])
            .arg(video)
            .arg("-itsoffset")
            .arg(offset.to_string())
            .arg("-i")
            .arg(source)
            .args([
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-c",
                "copy",
                "-map_metadata",
                "1",
                "-metadata:s:v:0",
                "rotate=0",
                "-avoid_negative_ts",
                "disabled",
                "-movie_timescale",
                "720000",
                "-movflags",
                "+faststart",
            ])
            .arg(output),
        config,
    )?;
    fs::remove_file(video)?;
    Ok(())
}
