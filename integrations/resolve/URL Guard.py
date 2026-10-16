"""DaVinci Resolve Workflow Integration script. Uses only the host's stdlib.

Install with scripts/build_resolve.py. Resolve supplies resolve/fusion/bmd globals.
"""

import json
import subprocess
from pathlib import Path


def current_item(resolve):
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project else None
    item = timeline.GetCurrentVideoItem() if timeline else None
    if not item or not item.GetMediaPoolItem():
        raise RuntimeError("Place the playhead on a source video clip.")
    return timeline, item


def launch(resolve, fusion, bmd, script_path):
    config = json.loads(Path(script_path).with_name("url_guard_config.json").read_text())
    ui = fusion.UIManager
    dispatcher = bmd.UIDispatcher(ui)
    win_id = "com.videoqc.urlguard"
    existing = ui.FindWindow(win_id)
    if existing:
        existing.Show()
        existing.Raise()
        return
    win = dispatcher.AddWindow(
        {
            "ID": win_id,
            "WindowTitle": "URL Guard · Delivery QC",
            "Geometry": [150, 150, 620, 380],
            "StyleSheet": "QWidget { background: #111214; color: #ededeb; font-size: 13px; } QPushButton { background: #f5d547; color: #111214; padding: 10px; border-radius: 6px; } QLineEdit { background: #232428; padding: 9px; }",
        },
        ui.VGroup(
            [
                ui.Label({"Text": '<h1 style="color:#f5d547">▧ URL GUARD</h1>', "Weight": 0}),
                ui.Label(
                    {
                        "Text": "Scan the source clip. Review the render. Import editable Fusion masks.",
                        "Weight": 0,
                    }
                ),
                ui.Button({"ID": "Scan", "Text": "Open current clip in URL Guard", "Weight": 0}),
                ui.LineEdit({"ID": "Bundle", "PlaceholderText": "Result folder from URL Guard"}),
                ui.HGroup(
                    [
                        ui.Button({"ID": "Browse", "Text": "Choose result"}),
                        ui.Button({"ID": "Masks", "Text": "Import Fusion masks"}),
                        ui.Button({"ID": "Render", "Text": "Import render to bin"}),
                    ]
                ),
                ui.Label(
                    {
                        "Text": "Masks: matching resolution, 1:1 speed, no retiming. Full source scan.",
                        "Weight": 0,
                    }
                ),
                ui.Label({"ID": "Status", "Text": "Ready", "WordWrap": True}),
            ]
        ),
    )
    items = win.GetItems()

    def safe(callback):
        def wrapped(event):
            try:
                callback(event)
            except Exception as error:  # noqa: BLE001 — host API failures must reach the panel
                items["Status"].Text = str(error)

        return wrapped

    def scan(_event):
        _, item = current_item(resolve)
        source = item.GetMediaPoolItem().GetClipProperty("File Path")
        if not source or not Path(source).is_file():
            raise RuntimeError("Clip source file is unavailable. Relink media first.")
        app = Path(config.get("native_app", "")) / "Contents/MacOS/URLGuard"
        if not app.is_file():
            raise RuntimeError("Build the Swift app first: bash scripts/build_macos.sh")
        subprocess.Popen([str(app), source], cwd=config["project_root"])
        items["Status"].Text = "Desktop opened. Render there, then choose its result folder here."

    def browse(_event):
        selected = fusion.RequestFile()
        if selected:
            items["Bundle"].Text = str(Path(selected).parent)

    def bundle():
        path = Path(items["Bundle"].Text).expanduser()
        if not (path / "report.json").is_file():
            raise RuntimeError("Choose a completed URL Guard result folder.")
        return path

    def masks(_event):
        path = bundle()
        timeline, item = current_item(resolve)
        report = json.loads((path / "report.json").read_text())
        source = item.GetMediaPoolItem().GetClipProperty("File Path")
        if Path(source).resolve() != Path(report["source"]).resolve():
            raise RuntimeError("Tracking belongs to another source clip.")
        tracking = json.loads((path / "tracking.json").read_text())
        comp = item.GetFusionCompByIndex(1) if item.GetFusionCompCount() else item.AddFusionComp()
        if not comp:
            raise RuntimeError("Could not open the clip's Fusion composition.")
        dimensions = tracking["source"]
        for key, expected in [("Width", dimensions["width"]), ("Height", dimensions["height"])]:
            actual = comp.GetPrefs("Comp.FrameFormat." + key)
            if actual and int(actual) != expected:
                raise RuntimeError(
                    "Fusion resolution differs from tracking. Use a matching-resolution timeline."
                )
        fps = float(timeline.GetSetting("timelineFrameRate"))
        source_fps = dimensions["fps"].split("/")
        source_rate = float(source_fps[0]) / float(source_fps[1])
        if abs(fps - source_rate) > 0.1:
            raise RuntimeError("Source and timeline frame rates differ. Export a matching-rate clip first.")
        global_start = comp.GetAttrs().get("COMPN_GlobalStart", 0)
        comp.SetData("video_qc.offset", global_start - float(item.GetLeftOffset()))
        comp.SetData("video_qc.fps", fps)
        comp.RunScript(str(path / "masks.fusion.lua"))
        resolve.OpenPage("fusion")
        items["Status"].Text = "Mask script dispatched. Review the Fusion console and all URL masks."

    def rendered(_event):
        path = bundle() / "blurred.mp4"
        if not path.is_file():
            raise RuntimeError("Rendered video is missing.")
        added = resolve.GetMediaStorage().AddItemListToMediaPool([str(path)])
        if not added:
            raise RuntimeError("Resolve could not import the rendered video.")
        items["Status"].Text = "Blurred render added to the media pool."

    win.On[win_id].Close = lambda _event: dispatcher.ExitLoop()
    win.On.Scan.Clicked = safe(scan)
    win.On.Browse.Clicked = safe(browse)
    win.On.Masks.Clicked = safe(masks)
    win.On.Render.Clicked = safe(rendered)
    win.Show()
    dispatcher.RunLoop()
    win.Hide()


if __name__ == "__main__":
    launch(resolve, fusion, bmd, __file__)  # noqa: F821 — injected by Resolve
