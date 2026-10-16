use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
pub struct Quad(pub [[f64; 2]; 4]);
impl Quad {
    pub fn from_box(b: [f64; 4]) -> Self {
        let [x, y, w, h] = b;
        Self([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    }
    pub fn bounds(&self) -> [f64; 4] {
        let x = self.0.iter().map(|p| p[0]).fold(f64::INFINITY, f64::min);
        let y = self.0.iter().map(|p| p[1]).fold(f64::INFINITY, f64::min);
        let xx = self
            .0
            .iter()
            .map(|p| p[0])
            .fold(f64::NEG_INFINITY, f64::max);
        let yy = self
            .0
            .iter()
            .map(|p| p[1])
            .fold(f64::NEG_INFINITY, f64::max);
        [x, y, xx - x, yy - y]
    }
    pub fn scale(&self, s: f64) -> Self {
        Self(self.0.map(|p| [p[0] * s, p[1] * s]))
    }
    pub fn area(&self) -> f64 {
        (0..4)
            .map(|i| cross(self.0[i], self.0[(i + 1) % 4]))
            .sum::<f64>()
            .abs()
            / 2.
    }
    pub fn valid(&self) -> bool {
        if self.0.iter().flatten().any(|n| !n.is_finite()) || self.area() < 2. {
            return false;
        }
        let signs: Vec<_> = (0..4)
            .map(|i| {
                cross(
                    sub(self.0[(i + 1) % 4], self.0[i]),
                    sub(self.0[(i + 2) % 4], self.0[(i + 1) % 4]),
                )
            })
            .collect();
        signs.iter().all(|x| *x > 0.) || signs.iter().all(|x| *x < 0.)
    }
    pub fn padded(&self, padding: f64) -> Self {
        if padding == 0. {
            return *self;
        }
        let mut out = self.0;
        let direction = if (0..4)
            .map(|i| cross(self.0[i], self.0[(i + 1) % 4]))
            .sum::<f64>()
            > 0.
        {
            1.
        } else {
            -1.
        };
        for (i, p) in out.iter_mut().enumerate() {
            let prev = sub(self.0[i], self.0[(i + 3) % 4]);
            let next = sub(self.0[(i + 1) % 4], self.0[i]);
            let n1 = [
                direction * prev[1] / length(prev),
                -direction * prev[0] / length(prev),
            ];
            let n2 = [
                direction * next[1] / length(next),
                -direction * next[0] / length(next),
            ];
            let a = [
                self.0[i][0] + padding * n1[0],
                self.0[i][1] + padding * n1[1],
            ];
            let b = [
                self.0[i][0] + padding * n2[0],
                self.0[i][1] + padding * n2[1],
            ];
            let det = cross(prev, next);
            if det.abs() > 1e-8 {
                let t = cross(sub(b, a), next) / det;
                *p = [a[0] + prev[0] * t, a[1] + prev[1] * t];
            }
        }
        Self(out)
    }
    pub fn flat(&self) -> [f64; 8] {
        std::array::from_fn(|i| self.0[i / 2][i % 2])
    }
    pub fn iou(&self, other: &Self) -> f64 {
        let [x, y, w, h] = self.bounds();
        let [a, b, c, d] = other.bounds();
        let area =
            ((x + w).min(a + c) - x.max(a)).max(0.) * ((y + h).min(b + d) - y.max(b)).max(0.);
        area / (w * h + c * d - area).max(1.)
    }
}
fn sub(a: [f64; 2], b: [f64; 2]) -> [f64; 2] {
    [a[0] - b[0], a[1] - b[1]]
}
fn cross(a: [f64; 2], b: [f64; 2]) -> f64 {
    a[0] * b[1] - a[1] * b[0]
}
fn length(a: [f64; 2]) -> f64 {
    a[0].hypot(a[1]).max(1e-8)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn padding_and_overlap() {
        let q = Quad::from_box([20., 30., 40., 10.]);
        assert_eq!(q.padded(5.).bounds(), [15., 25., 50., 20.]);
        assert_eq!(q.iou(&q), 1.);
        assert!(q.valid());
    }
    #[test]
    fn reject_bad_geometry() {
        assert!(!Quad([[0., 0.], [10., 10.], [0., 10.], [10., 0.]]).valid());
        assert!(!Quad::from_box([0., 0., 0., 3.]).valid());
    }
    #[test]
    fn tilted_padding() {
        let q = Quad([[40., 20.], [90., 30.], [80., 60.], [30., 50.]]);
        let p = q.padded(8.);
        assert!(p.valid());
        assert!(p.area() > q.area());
    }
}
