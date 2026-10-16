use crate::{geometry::Quad, native::Reader};
use anyhow::Result;
use regex::Regex;
use serde::Deserialize;
use std::sync::OnceLock;

#[derive(Clone, Debug)]
pub struct Detection {
    pub text: String,
    pub confidence: f64,
    pub quad: Quad,
}
#[derive(Deserialize)]
struct Line {
    text: String,
    confidence: f64,
    quad: Quad,
    chars: Vec<Option<Quad>>,
    turn: usize,
}
pub fn urls(text: &str) -> Vec<(usize, usize, String)> {
    static MATCHER: OnceLock<Regex> = OnceLock::new();
    let re=MATCHER.get_or_init(||Regex::new(r"(?i)https?://(?:\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::[0-9]{1,5})?(?:/[^\s<>]*)?|(?:w{3,4}\.)?(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,63}(?::[0-9]{1,5})?(?:/[^\s<>]*)?").unwrap());
    re.find_iter(text)
        .filter_map(|m| {
            if text[..m.start()]
                .chars()
                .next_back()
                .is_some_and(|c| c.is_alphanumeric() || c == '@')
            {
                return None;
            }
            if text[m.end()..]
                .chars()
                .next()
                .is_some_and(|c| c.is_alphanumeric() || c == '-')
            {
                return None;
            }
            let value = m
                .as_str()
                .trim_end_matches(['.', ',', ';', ':', '!', '?', ')', ']', '}']);
            let lower = value.to_ascii_lowercase();
            let host = lower
                .trim_start_matches("https://")
                .trim_start_matches("http://")
                .split(['/', ':'])
                .next()
                .unwrap_or("");
            let explicit = lower.starts_with("http://")
                || lower.starts_with("https://")
                || lower.starts_with("www.")
                || lower.starts_with("wwww.");
            let known = psl::suffix(host.as_bytes()).is_some_and(|s| s.is_known());
            if known || explicit {
                Some((m.start(), m.start() + value.len(), value.to_string()))
            } else {
                None
            }
        })
        .collect()
}
fn undo_rotation(q: Quad, turn: usize, width: f64) -> Quad {
    if turn == 0 {
        q
    } else {
        Quad(q.0.map(|p| [width - p[1], p[0]]))
    }
}
pub fn detect(
    reader: &mut Reader,
    width: usize,
    confidence: f64,
    sideways: bool,
) -> Result<Vec<Detection>> {
    parse(&reader.ocr_json(sideways)?, width, confidence)
}
pub fn parse(json: &str, width: usize, minimum: f64) -> Result<Vec<Detection>> {
    let lines: Vec<Line> = serde_json::from_str(json)?;
    let mut out: Vec<Detection> = Vec::new();
    for line in lines {
        if line.confidence < minimum {
            continue;
        }
        for (start, end, text) in urls(&line.text) {
            let start16 = line.text[..start].encode_utf16().count();
            let end16 = line.text[..end].encode_utf16().count();
            let chars: Vec<_> = line
                .chars
                .get(start16..end16)
                .unwrap_or(&[])
                .iter()
                .flatten()
                .collect();
            let q = if let (Some(first), Some(last)) = (chars.first(), chars.last()) {
                let selected = Quad([first.0[0], last.0[1], last.0[2], first.0[3]]);
                if selected.valid() {
                    selected
                } else {
                    line.quad
                }
            } else {
                line.quad
            };
            let quad = undo_rotation(q, line.turn, width as f64);
            if quad.valid() && !out.iter().any(|d| d.quad.iou(&quad) > 0.45) {
                out.push(Detection {
                    text,
                    confidence: line.confidence,
                    quad,
                });
            }
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn positive_urls() {
        for s in [
            "www.freakonomics.com",
            "https://example.com/path?q=1",
            "example.co.uk",
            "www.harpercollins.con",
            "example.technology",
            "EXAMPLE.TV",
            "http://127.0.0.1:8080/path",
            "https://localhost/page",
        ] {
            assert!(!urls(s).is_empty(), "{s}");
        }
    }
    #[test]
    fn negative_urls() {
        for s in [
            "person@example.com",
            "3.14",
            "scene.mp4",
            "Ordinary text",
            "J.Dubner",
        ] {
            assert!(urls(s).is_empty(), "{s}");
        }
    }
    #[test]
    fn multi_urls() {
        assert_eq!(
            urls("Visit www.example.com and https://other.org.").len(),
            2
        );
    }
    #[test]
    fn selected_range() {
        let line = serde_json::json!([{"text":"Visit www.example.com today","confidence":0.9,"quad":[[0,0],[260,0],[260,20],[0,20]],"turn":0,"chars":(0..27).map(|i|Quad::from_box([i as f64*10.,0.,10.,20.])).collect::<Vec<_>>()}]);
        let result = parse(&line.to_string(), 300, 0.4).unwrap();
        assert_eq!(result.len(), 1);
        assert!(result[0].quad.bounds()[0] >= 60.);
        assert!(result[0].quad.bounds()[2] < 260.);
    }
}
