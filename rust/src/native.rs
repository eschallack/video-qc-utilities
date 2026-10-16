use crate::{config::TrackingType, geometry::Quad};
use anyhow::{bail, Context, Result};
use std::{
    ffi::{c_char, c_void, CStr, CString},
    path::Path,
};

#[cfg(target_os = "macos")]
unsafe extern "C" {
    fn qc_apple_error() -> *const c_char;
    fn qc_reader_open(path: *const c_char) -> *mut c_void;
    fn qc_reader_close(handle: *mut c_void);
    fn qc_reader_next(
        handle: *mut c_void,
        gray: *mut u8,
        w: i32,
        h: i32,
        pts: *mut i64,
        scale: *mut i32,
    ) -> i32;
    fn qc_ocr(handle: *mut c_void, sideways: i32) -> *mut c_char;
    fn qc_free_string(value: *mut c_char);
    fn qc_writer_open(path: *const c_char, w: i32, h: i32, fps: f64, bitrate: i32) -> *mut c_void;
    fn qc_writer_frame(
        writer: *mut c_void,
        reader: *mut c_void,
        quads: *const f64,
        count: i32,
        sigma: f64,
        feather: f64,
        pts: i64,
        scale: i32,
    ) -> i32;
    fn qc_writer_finish(handle: *mut c_void, duration: f64) -> i32;
    fn qc_writer_close(handle: *mut c_void);
    fn qc_cv_threads(threads: i32);
    fn qc_track(
        a: *const u8,
        b: *const u8,
        w: i32,
        h: i32,
        quad: *const f32,
        perspective: i32,
        result: *mut f32,
    ) -> i32;
    fn qc_metal_available() -> i32;
    #[cfg(test)]
    pub(crate) fn qc_test_warp(
        input: *const u8,
        output: *mut u8,
        w: i32,
        h: i32,
        matrix: *const f64,
    ) -> i32;
    #[cfg(test)]
    pub(crate) fn qc_test_texture(output: *mut u8, w: i32, h: i32);
}
fn error() -> anyhow::Error {
    #[cfg(target_os = "macos")]
    {
        unsafe {
            anyhow::anyhow!(CStr::from_ptr(qc_apple_error())
                .to_string_lossy()
                .to_string())
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        anyhow::anyhow!("Native media backend currently requires macOS 13+")
    }
}
pub fn metal_available() -> bool {
    #[cfg(target_os = "macos")]
    {
        unsafe { qc_metal_available() != 0 }
    }
    #[cfg(not(target_os = "macos"))]
    {
        false
    }
}
pub fn set_threads(n: usize) {
    #[cfg(target_os = "macos")]
    unsafe {
        qc_cv_threads(n as i32)
    }
}
pub struct Reader {
    handle: *mut c_void,
}
pub struct Frame {
    pub pts: i64,
    pub timescale: i32,
    pub gray: Vec<u8>,
}
impl Reader {
    pub fn open(path: &Path) -> Result<Self> {
        let path = CString::new(path.to_string_lossy().as_bytes())?;
        #[cfg(target_os = "macos")]
        {
            let handle = unsafe { qc_reader_open(path.as_ptr()) };
            if handle.is_null() {
                return Err(error());
            }
            Ok(Self { handle })
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = path;
            Err(error())
        }
    }
    pub fn next(&mut self, w: usize, h: usize) -> Result<Option<Frame>> {
        let mut gray = vec![0; w.checked_mul(h).context("Tracking dimensions overflow")?];
        let mut pts = 0;
        let mut scale = 0;
        #[cfg(target_os = "macos")]
        {
            let status = unsafe {
                qc_reader_next(
                    self.handle,
                    if gray.is_empty() {
                        std::ptr::null_mut()
                    } else {
                        gray.as_mut_ptr()
                    },
                    w as i32,
                    h as i32,
                    &mut pts,
                    &mut scale,
                )
            };
            if status < 0 {
                return Err(error());
            }
            if status == 0 {
                return Ok(None);
            }
            if scale <= 0 {
                bail!("Invalid presentation timestamp");
            }
            Ok(Some(Frame {
                pts,
                timescale: scale,
                gray,
            }))
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = (gray, pts, scale);
            Err(error())
        }
    }
    pub fn ocr_json(&mut self, sideways: bool) -> Result<String> {
        #[cfg(target_os = "macos")]
        unsafe {
            let value = qc_ocr(self.handle, sideways as i32);
            if value.is_null() {
                return Err(error());
            }
            let result = CStr::from_ptr(value).to_string_lossy().to_string();
            qc_free_string(value);
            Ok(result)
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = sideways;
            Err(error())
        }
    }
}
impl Drop for Reader {
    fn drop(&mut self) {
        #[cfg(target_os = "macos")]
        unsafe {
            qc_reader_close(self.handle)
        }
    }
}
pub struct Writer {
    handle: *mut c_void,
}
impl Writer {
    pub fn open(path: &Path, w: usize, h: usize, fps: f64, bitrate_mbps: f64) -> Result<Self> {
        let path = CString::new(path.to_string_lossy().as_bytes())?;
        #[cfg(target_os = "macos")]
        {
            let handle = unsafe {
                qc_writer_open(
                    path.as_ptr(),
                    w as i32,
                    h as i32,
                    fps,
                    (bitrate_mbps * 1e6) as i32,
                )
            };
            if handle.is_null() {
                return Err(error());
            }
            Ok(Self { handle })
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = (path, w, h, fps, bitrate_mbps);
            Err(error())
        }
    }
    pub fn append(
        &mut self,
        reader: &Reader,
        quads: &[Quad],
        sigma: f64,
        feather: f64,
        pts: i64,
        scale: i32,
    ) -> Result<()> {
        let flat: Vec<f64> = quads.iter().flat_map(Quad::flat).collect();
        #[cfg(target_os = "macos")]
        {
            if unsafe {
                qc_writer_frame(
                    self.handle,
                    reader.handle,
                    flat.as_ptr(),
                    quads.len() as i32,
                    sigma,
                    feather,
                    pts,
                    scale,
                )
            } < 0
            {
                return Err(error());
            }
            Ok(())
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = (reader, flat, sigma, feather, pts, scale);
            Err(error())
        }
    }
    pub fn finish(&mut self, duration: f64) -> Result<()> {
        #[cfg(target_os = "macos")]
        {
            if unsafe { qc_writer_finish(self.handle, duration) } < 0 {
                return Err(error());
            }
            Ok(())
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = duration;
            Err(error())
        }
    }
}
impl Drop for Writer {
    fn drop(&mut self) {
        #[cfg(target_os = "macos")]
        unsafe {
            qc_writer_close(self.handle)
        }
    }
}

pub fn track(
    a: &[u8],
    b: &[u8],
    w: usize,
    h: usize,
    quad: Quad,
    kind: TrackingType,
) -> Result<Option<Quad>> {
    if a.len() != w * h || b.len() != w * h {
        bail!("Tracking buffer dimensions do not match");
    }
    let input = quad.flat().map(|n| n as f32);
    let mut output = [0f32; 8];
    #[cfg(target_os = "macos")]
    {
        let status = unsafe {
            qc_track(
                a.as_ptr(),
                b.as_ptr(),
                w as i32,
                h as i32,
                input.as_ptr(),
                (kind == TrackingType::Perspective) as i32,
                output.as_mut_ptr(),
            )
        };
        if status < 0 {
            bail!("OpenCV optical flow failed");
        }
        if status == 0 {
            return Ok(None);
        }
        let next = Quad(std::array::from_fn(|i| {
            [output[2 * i] as f64, output[2 * i + 1] as f64]
        }));
        let ratio = next.area() / quad.area();
        let [x, y, bw, bh] = next.bounds();
        if !next.valid()
            || !(0.55..1.8).contains(&ratio)
            || x + bw < 0.
            || y + bh < 0.
            || x >= w as f64
            || y >= h as f64
        {
            return Ok(None);
        }
        Ok(Some(next))
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (input, output, kind);
        Err(error())
    }
}
