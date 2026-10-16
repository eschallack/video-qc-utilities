use crate::{config::Config, geometry::Quad, native, ocr::Detection};
use anyhow::Result;

#[derive(Clone, Debug)]
pub struct Track {
    pub id: usize,
    pub text: String,
    pub confidence: f64,
    pub quad: Quad,
    pub last_seen: f64,
    pub method: &'static str,
}
pub struct Tracker {
    pub active: Vec<Track>,
    next_id: usize,
}
impl Default for Tracker {
    fn default() -> Self {
        Self {
            active: Vec::new(),
            next_id: 1,
        }
    }
}
impl Tracker {
    pub fn advance(
        &mut self,
        a: &[u8],
        b: &[u8],
        w: usize,
        h: usize,
        seconds: f64,
        config: &Config,
    ) -> Result<usize> {
        let before = self.active.len();
        let mut alive = Vec::with_capacity(before);
        for mut t in self.active.drain(..) {
            if seconds - t.last_seen > config.hold_seconds {
                continue;
            }
            if let Some(q) = native::track(a, b, w, h, t.quad, config.tracking_type)? {
                t.quad = q;
                t.method = "flow";
                alive.push(t);
            }
        }
        self.active = alive;
        Ok(before - self.active.len())
    }
    pub fn update(&mut self, detections: Vec<Detection>, seconds: f64) -> Vec<Track> {
        let mut used = Vec::new();
        let mut new = Vec::new();
        for d in detections {
            let found = self
                .active
                .iter()
                .enumerate()
                .filter(|(_, t)| !used.contains(&t.id))
                .map(|(i, t)| (i, t.quad.iou(&d.quad)))
                .filter(|(_, overlap)| *overlap > 0.2)
                .max_by(|a, b| a.1.total_cmp(&b.1))
                .map(|(i, _)| i);
            if let Some(i) = found {
                let t = &mut self.active[i];
                t.quad = d.quad;
                t.last_seen = seconds;
                t.method = "ocr";
                used.push(t.id);
            } else {
                let t = Track {
                    id: self.next_id,
                    text: d.text,
                    confidence: d.confidence,
                    quad: d.quad,
                    last_seen: seconds,
                    method: "ocr",
                };
                self.next_id += 1;
                used.push(t.id);
                new.push(t.clone());
                self.active.push(t);
            }
        }
        // Each OCR scan is authoritative. Flow alone cannot keep a mask alive
        // after a negative scan, even if background features still track well.
        self.active.retain(|t| used.contains(&t.id));
        new
    }
}

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::*;
    use crate::config::TrackingType;
    fn texture(w: usize, h: usize) -> Vec<u8> {
        let mut pixels = vec![0; w * h];
        unsafe { native::qc_test_texture(pixels.as_mut_ptr(), w as i32, h as i32) };
        pixels
    }
    fn warp(input: &[u8], w: usize, h: usize, m: [f64; 9]) -> Vec<u8> {
        let mut out = vec![0; w * h];
        assert_eq!(
            unsafe {
                native::qc_test_warp(
                    input.as_ptr(),
                    out.as_mut_ptr(),
                    w as i32,
                    h as i32,
                    m.as_ptr(),
                )
            },
            1
        );
        out
    }
    #[test]
    fn transform_rotation_scale() {
        let (w, h) = (320, 240);
        let a = texture(w, h);
        let m = [1.01, -0.025, 6., 0.025, 1.01, 2., 0., 0., 1.];
        let b = warp(&a, w, h, m);
        let q = Quad::from_box([80., 60., 100., 60.]);
        let moved = native::track(&a, &b, w, h, q, TrackingType::Transform)
            .unwrap()
            .unwrap();
        for (i, p) in q.0.iter().enumerate() {
            let x = m[0] * p[0] + m[1] * p[1] + m[2];
            let y = m[3] * p[0] + m[4] * p[1] + m[5];
            assert!((moved.0[i][0] - x).abs() < 1.);
            assert!((moved.0[i][1] - y).abs() < 1.);
        }
    }
    #[test]
    fn perspective_changes_shape() {
        let (w, h) = (320, 240);
        let a = texture(w, h);
        let m = [1., 0.015, 3., 0.01, 1., 2., 0.0004, -0.0002, 1.];
        let b = warp(&a, w, h, m);
        let q = Quad::from_box([80., 60., 100., 60.]);
        let p = native::track(&a, &b, w, h, q, TrackingType::Perspective)
            .unwrap()
            .unwrap();
        for (i, v) in q.0.iter().enumerate() {
            let z = m[6] * v[0] + m[7] * v[1] + 1.;
            let x = (m[0] * v[0] + m[1] * v[1] + m[2]) / z;
            let y = (m[3] * v[0] + m[4] * v[1] + m[5]) / z;
            assert!((p.0[i][0] - x).abs() < 1.5, "{:?} vs {x}", p.0[i]);
            assert!((p.0[i][1] - y).abs() < 1.5, "{:?} vs {y}", p.0[i]);
        }
        let top = [p.0[1][0] - p.0[0][0], p.0[1][1] - p.0[0][1]];
        let bottom = [p.0[2][0] - p.0[3][0], p.0[2][1] - p.0[3][1]];
        assert!(
            (top[0] * bottom[1] - top[1] * bottom[0]).abs() > 0.5,
            "Perspective edges must change independently"
        );
    }
    #[test]
    fn blank_fails_without_drifting() {
        let a = vec![0; 320 * 240];
        assert!(native::track(
            &a,
            &a,
            320,
            240,
            Quad::from_box([20., 30., 80., 40.]),
            TrackingType::Perspective
        )
        .unwrap()
        .is_none());
    }
}
