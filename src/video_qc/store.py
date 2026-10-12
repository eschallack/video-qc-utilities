"""Disk-backed tracking: memory use is independent of video duration."""

import json
import sqlite3
from pathlib import Path


class TrackStore:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE tracks (id INTEGER PRIMARY KEY, text TEXT, confidence REAL);
            CREATE TABLE samples (track INTEGER, frame INTEGER, seconds REAL,
                x REAL, y REAL, w REAL, h REAL, method TEXT, PRIMARY KEY(track, frame));
            CREATE INDEX samples_frame ON samples(frame);
        """)

    def save(self, track, frame, seconds, method=None, box=None):
        d = track.detection
        self.db.execute("INSERT OR IGNORE INTO tracks VALUES (?, ?, ?)", (track.id, d.text, d.confidence))
        self.db.execute(
            "INSERT OR REPLACE INTO samples VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (track.id, frame, seconds, *(box or d.box), method or track.method),
        )

    def at(self, frame):
        return self.db.execute("SELECT x,y,w,h FROM samples WHERE frame=?", (frame,)).fetchall()

    def export(self, path: Path, metadata: dict, config: dict):
        self.db.commit()
        with path.open("w", encoding="utf-8") as out:
            header = {
                "schema_version": 1,
                "coordinates": "display_pixels_top_left",
                "frame_origin": 0,
                "source": metadata,
                "config": config,
            }
            out.write(json.dumps(header, ensure_ascii=False)[:-1] + ', "tracks": [')
            first = True
            for track_id, text, confidence in self.db.execute("SELECT * FROM tracks ORDER BY id"):
                if not first:
                    out.write(",")
                first = False
                out.write(
                    json.dumps({"id": track_id, "text": text, "confidence": confidence})[:-1] + ',"samples":['
                )
                for i, row in enumerate(
                    self.db.execute(
                        "SELECT frame,seconds,x,y,w,h,method FROM samples WHERE track=? ORDER BY frame",
                        (track_id,),
                    )
                ):
                    if i:
                        out.write(",")
                    out.write(
                        json.dumps({"frame": row[0], "seconds": row[1], "box": row[2:6], "method": row[6]})
                    )
                out.write("]}")
            out.write("]}\n")

    def close(self):
        self.db.close()
