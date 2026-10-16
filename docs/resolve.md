# Resolve integration

The Python Workflow Integration panel uses Resolve's UIManager and standard library. It launches the Swift app. The app's bundled Rust engine owns processing; Resolve imports no OCR/Qt dependencies.

## Build and install

```sh
bash scripts/build_macos.sh
python3 scripts/build_resolve.py
```

Copy `dist/resolve/URL Guard.py` and `url_guard_config.json` together to:

- Workflow Integrations: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/`
- User script fallback: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/`

Restart Resolve. Open **Workspace → Workflow Integrations → URL Guard**, or **Workspace → Scripts → Utility → URL Guard**. Studio is the target host; UIManager/workflow availability depends on the Resolve edition.

The configuration points to the local `.app` and checkout. Rebuild the configuration after moving them. No system plugin folder is changed by the builder. The native app is macOS-only; Windows needs a separate native media/application adapter or the legacy CLI.

## Workflow

1. Place the playhead on a source video clip.
2. Click **Open current clip in URL Guard**.
3. In SwiftUI, choose Transform or Perspective, set feather/blur/padding, and render to a new folder.
4. Review the full movie.
5. Enter that result folder in the Resolve panel, or choose any file inside it.
6. Click **Import Fusion masks**, or **Import render to bin** for the baked result.

The engine scans the complete source file. The panel validates source identity, display dimensions, and matching frame rate, then adjusts the composition offset for a left trim. Existing mask imports are rejected; undo before importing again.

## Native mask graph

Each track gets a white Background image, animated CornerPositioner, Alpha BitmapMask, and Blur. All four corners are keyed independently from the tracked polygon. This preserves rotation/scale in Transform mode and projective distortion in Perspective mode. BitmapMask Level uses stepped keys with disabled guard frames, keeping gaps unmasked. SoftEdge implements editable feathering.

Masks insert before MediaOut1's existing image input. All changes share an undo group. The importer unlocks and undoes partial changes after errors. Import dispatch is asynchronous; inspect the Fusion console and resulting graph before delivery.

Matching resolution and 1:1 speed are required. Edit transforms, cropping, stabilization, lens correction, speed changes, and retiming can change the coordinate relationship. Export and analyze a matching intermediate for those workflows. The adapter does not automatically detect every such transformation.

Fusion blur and SoftEdge have host-specific units/kernels. The geometry and feather setting are included, but Core Image and Fusion do not produce pixel-identical Gaussian results. Adjust them in Fusion as needed.

## Direct import

In a matching composition with connected `MediaOut1`, use the Lua console:

```lua
comp:SetData("video_qc.offset", 0)
comp:SetData("video_qc.fps", 30)
comp:RunScript([[/absolute/path/result/masks.fusion.lua]])
```

For a 48-frame source trim, set the offset to composition global start minus 48. Tracking schema 2 includes source presentation times and actual quadrilaterals for custom retiming adapters.

## Host verification

The native importer was run in a hidden temporary Fusion composition on **Resolve 21.0.1.11**. CornerPositioner/BitmapMask/Blur creation, four animated point inputs, Alpha channel, normalized feather, mask visibility, and MediaOut connection passed. The temporary composition was closed. No existing timeline was changed.

Evidence: `demos/native/resolve-validation.txt`. The earlier panel load check remains in `demos/resolve-panel-validation.txt`; a complete interactive timeline workflow still merits acceptance testing.

References: Resolve's installed `Developer/Workflow Integrations/README_workflow.txt`, `Developer/Scripting/README.txt`, and [Blackmagic's Fusion scripting guide](https://documents.blackmagicdesign.com/UserManuals/Fusion8_Scripting_Guide.pdf).
