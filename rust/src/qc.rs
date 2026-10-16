use crate::{
    config::Config,
    media::{self, Metadata},
};
use anyhow::Result;
use regex::Regex;
use serde_json::{json, Value};
use std::{path::Path, process::Command};

fn finite(v: &Value) -> Value {
    v.as_str()
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|n| n.is_finite())
        .map_or(Value::Null, |n| json!(n))
}
pub fn inspect(source: &Path, meta: &Metadata, config: &Config) -> Result<Value> {
    let mut cmd = Command::new(media::tool("ffmpeg"));
    cmd.args(["-hide_banner", "-nostats", "-i"])
        .arg(source)
        .args([
            "-map",
            "0:v:0",
            "-vf",
            "scale=320:-2,blackdetect=d=0.5:pix_th=0.10:pic_th=0.98,freezedetect=n=-50dB:d=1",
        ]);
    if !meta.audio.is_empty() {
        cmd.args([
            "-map",
            "0:a:0",
            "-af",
            "silencedetect=n=-50dB:d=1,loudnorm=I=-24:TP=-2:LRA=7:print_format=json",
        ]);
    }
    cmd.args(["-f", "null", "-"]);
    let (_, log) = media::run(&mut cmd, config)?;
    Ok(parse(&log, meta))
}
pub fn parse(log: &str, meta: &Metadata) -> Value {
    let mut events = Vec::new();
    let black = Regex::new(r"black_start:([\d.]+) black_end:([\d.]+)").unwrap();
    for m in black.captures_iter(log) {
        events.push(json!({"kind":"black","start":m[1].parse::<f64>().unwrap_or(0.),"end":m[2].parse::<f64>().unwrap_or(0.)}));
    }
    for (kind, prefix) in [
        ("freeze", "lavfi.freezedetect.freeze"),
        ("silence", "silence"),
    ] {
        let re = Regex::new(&format!(
            r"{}_(start|end)[:=]\s*([\d.]+)",
            regex::escape(prefix)
        ))
        .unwrap();
        let mut start = None;
        for m in re.captures_iter(log) {
            let time = m[2].parse::<f64>().unwrap_or(0.);
            if &m[1] == "start" {
                start = Some(time);
            } else if let Some(t) = start.take() {
                events.push(json!({"kind":kind,"start":t,"end":time}));
            }
        }
        if let Some(t) = start {
            events.push(json!({"kind":kind,"start":t,"end":meta.duration}));
        }
    }
    let loudness=Regex::new(r#"(?s)\{\s*"input_i".*?\}"#).unwrap().find(log)
        .and_then(|m|serde_json::from_str::<Value>(m.as_str()).ok())
        .map(|v|json!({"integrated_lufs":finite(&v["input_i"]),"true_peak_dbtp":finite(&v["input_tp"]),"range_lu":finite(&v["input_lra"])}));
    events.sort_by(|a, b| {
        a["start"]
            .as_f64()
            .unwrap_or(0.)
            .total_cmp(&b["start"].as_f64().unwrap_or(0.))
    });
    json!({"schema_version":2,"source":meta,"events":events,"loudness":loudness,"audio_measured":"first audio stream only","notice":"Editorial measurements; no platform certification."})
}
