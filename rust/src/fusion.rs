use crate::{config::Config, geometry::Quad, media::Metadata, store::Store};
use anyhow::Result;
use std::{
    fs::File,
    io::{BufWriter, Write},
    path::Path,
};

pub fn export(store: &Store, path: &Path, meta: &Metadata, config: &Config) -> Result<()> {
    let mut out = BufWriter::new(File::create(path)?);
    writeln!(out,"-- URL Guard v2: tracked quadrilaterals, transform/perspective, feathered masks\nlocal comp = comp or composition or (fu and fu:GetCurrentComp())\nassert(comp, 'Open a Fusion composition')\nlocal offset = VIDEO_QC_OFFSET or comp:GetData('video_qc.offset') or comp:GetAttrs().COMPN_GlobalStart or 0\nlocal fps = VIDEO_QC_FPS or comp:GetData('video_qc.fps') or {}\nlocal mediaOut = comp:FindTool('MediaOut1')\nassert(mediaOut and mediaOut.Input:GetConnectedOutput(), 'Connect MediaOut1 first')\nassert(not comp:FindTool('URLBlur_1'), 'Masks already imported; undo first')\ncomp:Lock()\ncomp:StartUndo('Import tracked URL masks')\nlocal ok, err = pcall(function()\nlocal previous = mediaOut.Input:GetConnectedOutput():GetTool()",meta.rate())?;
    let mut tracks = store.db.prepare("SELECT id FROM tracks ORDER BY id")?;
    for id in tracks.query_map([], |r| r.get::<_, usize>(0))? {
        let id = id?;
        writeln!(out,"do\n  local bg=comp:AddTool('Background',-32768,-32768)\n  bg:SetAttrs({{TOOLS_Name='URLMatte_{id}'}})\n  bg:SetInput('TopLeftRed',1)\n  bg:SetInput('TopLeftGreen',1)\n  bg:SetInput('TopLeftBlue',1)\n  bg:SetInput('TopLeftAlpha',1)\n  local pin=comp:AddTool('CornerPositioner',-32768,-32768)\n  pin:SetAttrs({{TOOLS_Name='URLCorners_{id}'}})\n  pin:ConnectInput('Input',bg)\n  for _,name in ipairs({{'TopLeft','TopRight','BottomRight','BottomLeft'}}) do pin[name]=comp:Path({{}}) end\n  local mask=comp:AddTool('BitmapMask',-32768,-32768)\n  mask:SetAttrs({{TOOLS_Name='URLMask_{id}'}})\n  mask:ConnectInput('Image',pin)\n  mask:SetInput('Channel','Alpha')\n  mask:SetInput('SoftEdge',{})\n  mask.Level=comp:BezierSpline({{}})\n  local samples={{",config.feather/(meta.width.max(meta.height) as f64))?;
        let mut stmt = store
            .db
            .prepare("SELECT seconds,quad FROM samples WHERE track=?1 ORDER BY frame")?;
        let mut rows = stmt.query([id])?;
        while let Some(r) = rows.next()? {
            let seconds = r.get::<_, f64>(0)?;
            let q: Quad = serde_json::from_str(&r.get::<_, String>(1)?)?;
            let q = q.padded(config.padding);
            write!(out, "    {{{seconds:0.9}")?;
            for [x, y] in q.0 {
                write!(
                    out,
                    ",{:0.9},{:0.9}",
                    x / meta.width as f64,
                    1. - y / meta.height as f64
                )?;
            }
            writeln!(out, "}},")?;
        }
        writeln!(out,"  }}\n  local names={{'TopLeft','TopRight','BottomRight','BottomLeft'}}\n  local levels={{}}\n  local last=nil\n  for _,s in ipairs(samples) do\n    local t=math.floor(s[1]*fps+0.5)+offset\n    for i,name in ipairs(names) do pin[name][t]={{s[2*i],s[2*i+1]}} end\n    if not last or t>last+1 then levels[t-1]={{0,Flags={{StepIn=true}}}} end\n    levels[t]={{1,Flags={{StepIn=true}}}}\n    levels[t+1]={{0,Flags={{StepIn=true}}}}\n    last=t\n  end\n  mask.Level:GetConnectedOutput():GetTool():SetKeyFrames(levels,true)\n  local blur=comp:AddTool('Blur',-32768,-32768)\n  blur:SetAttrs({{TOOLS_Name='URLBlur_{id}'}})\n  blur:ConnectInput('Input',previous)\n  blur:ConnectInput('EffectMask',mask)\n  blur:SetInput('XBlurSize',{})\n  blur:SetInput('YBlurSize',{})\n  previous=blur\nend",config.blur_sigma,config.blur_sigma)?;
    }
    writeln!(out,"mediaOut:ConnectInput('Input',previous)\nend)\ncomp:EndUndo(true)\ncomp:Unlock()\nif not ok then comp:Undo();error(err) end\nprint('Tracked URL masks imported. Review before delivery.')")?;
    Ok(())
}
