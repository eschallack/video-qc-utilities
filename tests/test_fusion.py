import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

from video_qc.fusion import export_lua
from video_qc.models import Config, Detection
from video_qc.store import TrackStore
from video_qc.tracking import Track


def test_lua_importer_coordinates_gaps_connections_and_unlock(tmp_path):
    if not shutil.which("lua"):
        pytest.skip("Lua interpreter is optional; host smoke test is documented separately")
    store = TrackStore(tmp_path / "track.sqlite")
    track = Track(1, Detection("www.example.com", 0.9, (20, 30, 40, 10)), 0)
    for frame in [0, 1, 5]:
        store.save(track, frame, frame / 25)
    path = tmp_path / "masks.lua"
    export_lua(store, path, {"width": 200, "height": 100, "fps": "25/1"}, Config(padding=0))
    store.close()
    harness = tmp_path / "harness.lua"
    harness.write_text("""
local tools = {}
local unlocked = false
local ended = false
local function animated()
  local obj = {}
  function obj:GetConnectedOutput() return self end
  function obj:GetTool() return self end
  function obj:SetKeyFrames(values, replace) self.keys = values end
  return obj
end
local original = { GetTool = function(self) return self end }
local output = { Input = {GetConnectedOutput = function() return original end} }
function output:ConnectInput(name, tool) self.connected = tool end
comp = {}
function comp:GetAttrs() return {COMPN_GlobalStart=100} end
function comp:GetData(name) return nil end
function comp:FindTool(name) if name == 'MediaOut1' then return output end end
function comp:Lock() end
function comp:Unlock() unlocked = true end
function comp:StartUndo(name) end
function comp:EndUndo(ok) ended = ok end
function comp:Path(options) return animated() end
function comp:BezierSpline(options) return animated() end
function comp:AddTool(kind)
  local t = { kind=kind, connections={}, inputs={} }
  function t:SetAttrs(attrs) self.name=attrs.TOOLS_Name end
  function t:ConnectInput(name, tool) self.connections[name]=tool end
  function t:SetInput(name, value) self.inputs[name]=value end
  table.insert(tools, t)
  return t
end
dofile(arg[1])
assert(unlocked and ended)
local mask, blur = tools[1], tools[2]
assert(mask.kind == 'RectangleMask' and blur.kind == 'Blur')
assert(math.abs(mask.Center[100][1] - 0.2025) < 0.00001)
assert(math.abs(mask.Center[100][2] - 0.645) < 0.00001)
assert(mask.Level.keys[99][1] == 0)
assert(mask.Level.keys[100][1] == 1 and mask.Level.keys[101][1] == 1)
assert(mask.Level.keys[102][1] == 0 and mask.Level.keys[104][1] == 0)
assert(mask.Level.keys[105][1] == 1 and mask.Level.keys[106][1] == 0)
assert(blur.connections.Input == original and blur.connections.EffectMask == mask)
assert(output.connected == blur)
""")
    subprocess.run(["lua", str(harness), str(path)], check=True, capture_output=True)


def test_resolve_clip_guard():
    source = Path(__file__).parents[1] / "integrations/resolve/URL Guard.py"
    spec = importlib.util.spec_from_file_location("resolve_extension", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Resolve:
        def GetProjectManager(self):
            return self

        def GetCurrentProject(self):
            return None

    with pytest.raises(RuntimeError, match="playhead"):
        module.current_item(Resolve())
