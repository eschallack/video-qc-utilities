# DaVinci Resolve extension

The adapter is a Python Workflow Integration script. This mechanism is documented in the developer package shipped with Resolve. Its black/yellow panel uses Resolve's UIManager. The desktop engine has a separate Python environment, so Resolve's embedded Python does not need ONNX, OpenCV, or Qt installed.

## Build and install

```sh
uv sync --locked --extra gui
uv run python scripts/build_resolve.py
```

Copy **both** files from `dist/resolve` to one of these folders:

| Platform | Folder |
| --- | --- |
| macOS, Workflow Integrations | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/` |
| Windows, Workflow Integrations | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\` |
| macOS, user Scripts fallback | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/` |
| Windows, user Scripts fallback | `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\` |

The builder prepares files locally. It does not change the system plugin folder. Restart Resolve after copying. Use **Workspace → Workflow Integrations → URL Guard**, or **Workspace → Scripts → Utility → URL Guard** for the fallback location. Workflow Integration/UIManager availability depends on the Resolve edition; Studio is the target host.

The generated configuration points at this checkout's Python and project directory. Rebuild after moving the checkout or recreating its virtual environment. On Windows the builder picks the current environment's `python.exe`. `--destination` and `--python` allow explicit paths.

## Use

1. Place the timeline playhead on the source clip.
2. Open URL Guard. Click **Open current clip in URL Guard**.
3. In the desktop app, choose a new result folder. Analyze and render.
4. Review the complete render. The source scan includes the full source file, not just the timeline trim.
5. In the Resolve panel, enter the result folder, or choose any file inside it with **Choose result**.
6. Click **Import Fusion masks** to attach editable masks, or **Import render to bin** for the baked video.

The adapter verifies that tracking belongs to the selected source, that composition dimensions match display dimensions, and that source/timeline frame rates agree within 0.1 fps. It adjusts the source-frame offset for a left trim. It rejects a duplicate mask import. It inserts the blur chain before MediaOut, retaining the previously connected image chain.

Masks assume 1:1 speed, matching dimensions, and no spatial transform that changes the coordinate relationship. The adapter does not automatically detect all speed changes, stabilization, cropping, lens correction, or Edit-page transform settings. For those cases, export a matching-resolution, matching-frame-rate intermediate and analyze it. Make sure its Fusion image coordinates match the export.

Import dispatch is asynchronous. The panel reports dispatch, not successful execution. Check the Fusion console for errors and inspect `URLMask_*` / `URLBlur_*`. The importer uses one undo group and unlocks the composition after errors. Undo an earlier import before retrying.

## Import without the extension

Open the source clip in Fusion. The composition needs `MediaOut1` with a connected image. In the Lua console:

```lua
comp:RunScript([[C:\results\my-clip\masks.fusion.lua]])
```

On macOS use the absolute POSIX path. In Fusion Studio, use a MediaOut node for this importer or adapt the output target to your composition.

For a trim or a composition with a nonzero starting frame, set persistent offsets first:

```lua
comp:SetData("video_qc.offset", -48) -- composition frame = source frame - 48
comp:SetData("video_qc.fps", 24)
comp:RunScript([[/absolute/path/masks.fusion.lua]])
```

The default offset is the composition's global start. The panel computes this automatically for supported source trims. Set the offset back when using another source. JSON contains presentation times for custom retiming adapters.

## Host verification

On 2026-10-12, the generated importer ran through `Composition.RunScript` in a hidden temporary composition on **Resolve 21.0.1.11**. Real RectangleMask/Blur tools were created. Center coordinates, stepped visibility across a tracking gap, and MediaOut connections were checked through the host API. The temporary composition was closed. No existing project or timeline was edited.

The built Python panel also loaded in the host. Its Scan, Masks, and Status controls were inspected, then the window was closed. The panel's media-pool/timeline workflows have automated API guards and an installation guide. A full interactive end-to-end panel session and Windows host execution remain manual acceptance checks. The local host validation records only the behaviors actually exercised.

References: Resolve's installed `Developer/Workflow Integrations/README_workflow.txt` and `Developer/Scripting/README.txt`; [Blackmagic Fusion scripting guide](https://documents.blackmagicdesign.com/UserManuals/Fusion8_Scripting_Guide.pdf).
