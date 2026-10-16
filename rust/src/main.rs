use clap::{Parser, Subcommand};
use serde_json::json;
use std::path::PathBuf;
use video_qc::{media, native, process, qc, Config, TrackingType};

#[derive(Parser)]
#[command(
    version,
    about = "Native URL tracking, feathered blur, and editorial QC"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}
#[derive(Subcommand)]
enum Commands {
    Blur {
        source: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
        #[arg(long, default_value_t = 8)]
        scan_interval: usize,
        #[arg(long,value_enum,default_value_t=TrackingType::Transform)]
        tracking_type: TrackingType,
        #[arg(long, default_value_t = 4.)]
        feather: f64,
        #[arg(long, default_value_t = 18.)]
        sigma: f64,
        #[arg(long, default_value_t = 10.)]
        padding: f64,
        #[arg(long, default_value_t = 0.45)]
        confidence: f64,
        #[arg(long, default_value_t = 2)]
        threads: usize,
        #[arg(long, default_value_t = 12.)]
        bitrate_mbps: f64,
        #[arg(long)]
        no_sideways: bool,
        #[arg(long)]
        no_qc: bool,
        #[arg(long)]
        cancel_file: Option<PathBuf>,
        #[arg(long)]
        json_progress: bool,
    },
    Check {
        source: PathBuf,
        #[arg(short, long)]
        output: Option<PathBuf>,
    },
    Doctor,
}
fn main() {
    if let Err(error) = run() {
        eprintln!("{error:#}");
        std::process::exit(if error.to_string() == "cancelled" {
            130
        } else {
            1
        });
    }
}
fn run() -> anyhow::Result<()> {
    match Cli::parse().command {
        Commands::Blur {
            source,
            output,
            scan_interval,
            tracking_type,
            feather,
            sigma,
            padding,
            confidence,
            threads,
            bitrate_mbps,
            no_sideways,
            no_qc,
            cancel_file,
            json_progress,
        } => {
            let config = Config {
                scan_interval,
                tracking_type,
                feather,
                blur_sigma: sigma,
                padding,
                confidence,
                threads,
                bitrate_mbps,
                sideways: !no_sideways,
                run_qc: !no_qc,
                cancel_file,
                ..Config::default()
            };
            let report = process(&source, &output, &config, |event| {
                if json_progress {
                    println!("{event}");
                } else {
                    eprintln!("{} · frame {}", event["stage"], event["frame"]);
                }
            })?;
            println!("{}", json!({"stage":"result","report":report}));
        }
        Commands::Check { source, output } => {
            let meta = media::probe(&source)?;
            let checks = qc::inspect(&source, &meta, &Config::default())?;
            let text = serde_json::to_string_pretty(&checks)?;
            if let Some(p) = output {
                std::fs::write(p, text)?;
            } else {
                println!("{text}");
            }
        }
        Commands::Doctor => {
            let result = json!({"version":env!("CARGO_PKG_VERSION"),"metal":native::metal_available(),"ocr":"Apple Vision","encoder":"VideoToolbox hardware H.264","ffmpeg":media::tool("ffmpeg"),"architecture":std::env::consts::ARCH});
            println!("{result}");
            if !native::metal_available() {
                anyhow::bail!("Metal device unavailable");
            }
        }
    }
    Ok(())
}
