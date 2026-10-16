use crate::{config::Config, geometry::Quad, media::Metadata, tracking::Track};
use anyhow::Result;
use rusqlite::{params, Connection};
use serde_json::json;
use std::{
    fs::File,
    io::{BufWriter, Write},
    path::Path,
};

pub struct Store {
    pub db: Connection,
}
impl Store {
    pub fn new(path: &Path) -> Result<Self> {
        let db = Connection::open(path)?;
        db.execute_batch("CREATE TABLE tracks(id INTEGER PRIMARY KEY,text TEXT,confidence REAL);
            CREATE TABLE samples(track INTEGER,frame INTEGER,seconds REAL,quad TEXT,method TEXT,PRIMARY KEY(track,frame));
            CREATE INDEX samples_frame ON samples(frame);BEGIN;")?;
        Ok(Self { db })
    }
    pub fn save(
        &self,
        t: &Track,
        frame: usize,
        seconds: f64,
        quad: Quad,
        method: &str,
    ) -> Result<()> {
        self.db
            .prepare_cached("INSERT OR IGNORE INTO tracks VALUES (?1,?2,?3)")?
            .execute(params![t.id, t.text, t.confidence])?;
        self.db
            .prepare_cached("INSERT OR REPLACE INTO samples VALUES (?1,?2,?3,?4,?5)")?
            .execute(params![
                t.id,
                frame,
                seconds,
                serde_json::to_string(&quad)?,
                method
            ])?;
        Ok(())
    }
    pub fn commit(&self) -> Result<()> {
        self.db.execute_batch("COMMIT;BEGIN;")?;
        Ok(())
    }
    pub fn at(&self, frame: usize) -> Result<Vec<Quad>> {
        let mut stmt = self
            .db
            .prepare_cached("SELECT quad FROM samples WHERE frame=?1")?;
        let strings = stmt
            .query_map([frame], |r| r.get::<_, String>(0))?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        strings
            .into_iter()
            .map(|s| Ok(serde_json::from_str(&s)?))
            .collect()
    }
    pub fn export(&self, path: &Path, metadata: &Metadata, config: &Config) -> Result<()> {
        let mut out = BufWriter::new(File::create(path)?);
        let header = json!({"schema_version":2,"coordinates":"display_pixels_top_left","frame_origin":0,"source":metadata,"config":config});
        let header = header.to_string();
        write!(out, "{},\"tracks\":[", &header[..header.len() - 1])?;
        let mut stmt = self
            .db
            .prepare("SELECT id,text,confidence FROM tracks ORDER BY id")?;
        let mut tracks = stmt.query([])?;
        let mut first = true;
        while let Some(t) = tracks.next()? {
            let id = t.get::<_, usize>(0)?;
            let text = t.get::<_, String>(1)?;
            let confidence = t.get::<_, f64>(2)?;
            if !first {
                write!(out, ",")?;
            }
            first = false;
            let header = json!({"id":id,"text":text,"confidence":confidence}).to_string();
            write!(out, "{},\"samples\":[", &header[..header.len() - 1])?;
            let mut samples = self.db.prepare(
                "SELECT frame,seconds,quad,method FROM samples WHERE track=?1 ORDER BY frame",
            )?;
            let mut rows = samples.query([id])?;
            let mut first_sample = true;
            while let Some(r) = rows.next()? {
                if !first_sample {
                    write!(out, ",")?;
                }
                first_sample = false;
                let q: Quad = serde_json::from_str(&r.get::<_, String>(2)?)?;
                serde_json::to_writer(
                    &mut out,
                    &json!({"frame":r.get::<_,usize>(0)?,"seconds":r.get::<_,f64>(1)?,"quad":q,"box":q.bounds(),"method":r.get::<_,String>(3)?}),
                )?;
            }
            write!(out, "]}}")?;
        }
        write!(out, "]}}")?;
        out.flush()?;
        Ok(())
    }
}
