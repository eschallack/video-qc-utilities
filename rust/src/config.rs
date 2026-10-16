use anyhow::{bail, Result};
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "lowercase")]
pub enum TrackingType {
    #[default]
    Transform,
    Perspective,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub scan_interval: usize,
    pub confidence: f64,
    pub padding: f64,
    pub blur_sigma: f64,
    pub feather: f64,
    pub tracking_type: TrackingType,
    pub hold_seconds: f64,
    pub threads: usize,
    pub bitrate_mbps: f64,
    pub sideways: bool,
    pub run_qc: bool,
    #[serde(skip)]
    pub cancel_file: Option<PathBuf>,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            scan_interval: 8,
            confidence: 0.45,
            padding: 10.,
            blur_sigma: 18.,
            feather: 4.,
            tracking_type: TrackingType::Transform,
            hold_seconds: 2.,
            threads: 2,
            bitrate_mbps: 12.,
            sideways: true,
            run_qc: true,
            cancel_file: None,
        }
    }
}
impl Config {
    pub fn validate(&self) -> Result<()> {
        if self.scan_interval == 0
            || self.scan_interval > 120
            || self.threads == 0
            || self.threads > 64
        {
            bail!("Scan interval must be 1–120; threads must be 1–64");
        }
        for n in [
            self.confidence,
            self.padding,
            self.blur_sigma,
            self.feather,
            self.hold_seconds,
            self.bitrate_mbps,
        ] {
            if !n.is_finite() {
                bail!("Settings must be finite");
            }
        }
        if !(0.0..=1.0).contains(&self.confidence)
            || !(0.0..=100.0).contains(&self.padding)
            || !(0.1..=100.0).contains(&self.blur_sigma)
            || !(0.0..=100.0).contains(&self.feather)
            || !(0.0..=10.0).contains(&self.hold_seconds)
            || !(1.0..=100.0).contains(&self.bitrate_mbps)
        {
            bail!("Mask or encoder setting outside supported range");
        }
        Ok(())
    }
    pub fn check_cancelled(&self) -> Result<()> {
        if self.cancel_file.as_ref().is_some_and(|p| p.exists()) {
            bail!("cancelled");
        }
        Ok(())
    }
}
