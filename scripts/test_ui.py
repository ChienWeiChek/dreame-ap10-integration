"""Local test page: read and set properties on your Dreame purifiers from a browser.

Usage:  .venv/bin/python scripts/test_ui.py [port]    then open http://127.0.0.1:8765
Credentials come from the repo .env (DREAME_USERNAME / DREAME_PASSWORD / DREAME_COUNTRY).
Listens on 127.0.0.1 only. Writes go to the real device.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from probe_properties import api_mod, load_env

# Properties known on the NP10 (3.4/3.5 only exist in the cloud cache); editable on the page.
DEFAULT_PROPS = "2.1 2.2 2.3 2.4 3.4 3.5 3.12 4.7 4.8 4.9 4.10 4.11 4.12 6.1 6.3 6.4 6.8 6.10 6.15"
_client = None
_devices = {}  # did -> bindDomain host


def client():
    global _client
    if _client is None:
        env = load_env()
        if not env.get("DREAME_USERNAME") or not env.get("DREAME_PASSWORD"):
            raise RuntimeError("Set DREAME_USERNAME and DREAME_PASSWORD in .env")
        c = api_mod.DreameCloudAPI(env["DREAME_USERNAME"], env["DREAME_PASSWORD"], env.get("DREAME_COUNTRY") or "us")
        if not c.login():
            raise RuntimeError("Login failed (check .env region and password)")
        _client = c
    return _client


def parse_props(text):
    """'2.1 6.10' -> [(2, 1), (6, 10)]; raises ValueError on bad input."""
    out = []
    for tok in text.replace(",", " ").split():
        s, _, p = tok.partition(".")
        out.append((int(s), int(p)))
    if not out:
        raise ValueError("no properties given")
    return out


def handle(req):
    op = req.get("op")
    if op == "devices":
        devs = [d for d in (client().get_devices() or []) if ".airp." in d.get("model", "")]
        _devices.update({str(d["did"]): d.get("bindDomain") for d in devs})
        return [{"did": str(d["did"]), "model": d.get("model"), "name": d.get("customName") or d.get("model")} for d in devs]
    did = str(req.get("did", ""))
    if did not in _devices:
        raise ValueError("unknown device; load devices first")
    host, c = _devices[did], client()
    if op == "read":
        params = [{"did": did, "siid": s, "piid": p} for s, p in parse_props(req.get("props", ""))]
        result = []
        for i in range(0, len(params), 5):  # small batches: big get_properties calls time out
            result.append(c.send_command(did, "get_properties", params[i:i + 5], host))
        # Props the device didn't answer: fall back to the cloud cache (notify-only values like PM2.5)
        got = {(p["siid"], p["piid"]) for batch in result if isinstance(batch, list) for p in batch if p.get("code") == 0}
        missing = [{"siid": p["siid"], "piid": p["piid"]} for p in params if (p["siid"], p["piid"]) not in got]
        if missing:
            cached = c.get_cached_properties(did, missing)
            result.append([{"siid": s, "piid": p, "code": 0, "value": v, "cloud": True} for (s, p), v in cached.items()])
        return result
    if op == "set":
        value = json.loads(req["value"])  # 1, "text", true ...
        return c.send_command(did, "set_properties", [{"did": did, "siid": int(req["siid"]), "piid": int(req["piid"]), "value": value}], host)
    # No free-form actions: unknown NP10 actions 2/1 and 2/2 coincided with the device
    # being unbound from the Dreamehome account (2026-11-15).
    raise ValueError(f"unknown op {op!r}")


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dreame Test Bench</title>
<style>
:root{color-scheme:light dark;--bg:#f6f6f4;--fg:#1d1d1b;--card:#fff;--line:#d9d9d4;--accent:#8a6d4b;--warn:#a23b2a}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecece8;--card:#222220;--line:#3a3a37;--accent:#c9a57c;--warn:#e07a66}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;max-width:860px;margin-inline:auto}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:0 0 12px}
h1{font-size:20px;margin:4px 0 12px}h2{font-size:15px;margin:0 0 8px}
input,select,button{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
button{cursor:pointer}button:hover{border-color:var(--accent)}
input.n{width:4.5em}input.w{width:100%;box-sizing:border-box}
.row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0}
.warn{color:var(--warn);font-size:13px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{text-align:left;padding:3px 8px;border-bottom:1px solid var(--line)}
td.chg{color:var(--accent);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.tile{border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.tile b{display:block;font-size:12px;font-weight:500;opacity:.7}.tile span{font-size:18px;font-variant-numeric:tabular-nums}
pre{white-space:pre-wrap;word-break:break-all;font-size:12px;max-height:320px;overflow:auto;margin:0}
</style></head><body>
<h1>Dreame Test Bench</h1>
<section><div class="row"><button onclick="devices()">Load devices</button><select id="dev" aria-label="Device"></select></div></section>

<section><h2>Current status <span class="warn" id="stime" style="font-weight:400"></span></h2>
<div id="status" class="grid" aria-live="polite"><span class="warn">Load devices, then Read.</span></div>
<div class="row"><label><input type="checkbox" id="auto" onchange="autoRead()"> Auto-refresh every 15 s</label></div></section>

<section><h2>Read properties</h2>
<div class="row"><input id="props" class="w" aria-label="Properties (siid.piid)" value="__PROPS__"></div>
<div class="row"><button onclick="read()">Read</button><span class="warn" id="rmsg"></span></div>
<table id="tbl" aria-label="Property values"></table></section>

<section><h2>NP10 quick controls</h2>
<div class="row">Mode: <button onclick="setp(2,3,0)">AI Purify</button><button onclick="setp(2,3,2)">Sleep</button><button onclick="setp(2,3,3)">Custom</button></div>
<div class="row">Speed: <button onclick="setp(2,4,1)">1</button><button onclick="setp(2,4,2)">2</button><button onclick="setp(2,4,3)">3</button></div>
<div class="row">Child lock: <button onclick="setp(6,10,1)">On</button><button onclick="setp(6,10,0)">Off</button>
&nbsp; Timer: <button onclick="setp(6,8,0)">Off</button><button onclick="setp(6,8,1)">1 h</button></div></section>

<section><h2>Set property</h2>
<div class="row">siid <input id="ss" class="n" type="number"> piid <input id="sp" class="n" type="number">
value (JSON) <input id="sv" class="n" value="1"> <button onclick="setp(+ss.value,+sp.value,sv.value)">Set</button></div></section>


<section><h2>Log</h2><pre id="log" aria-live="polite"></pre></section>
<script>
const $=id=>document.getElementById(id); let last={};
function log(label,data){$('log').textContent=new Date().toLocaleTimeString()+'  '+label+'\\n'+JSON.stringify(data,null,1)+'\\n\\n'+$('log').textContent}
async function call(body){const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();log(body.op+(r.ok?'':' ERROR'),j);if(!r.ok)throw j;return j}
async function devices(){const ds=await call({op:'devices'});$('dev').innerHTML=ds.map(d=>`<option value="${d.did}">${d.name} (${d.model})</option>`).join('')}
// Labels as the Dreamehome app shows them (NP10 map; see README)
const MODES={0:'AI Purify',1:'Strong Purification',2:'Sleep Purification',3:'Custom',4:'Pet Purify'},AQ={1:'Excellent'};
function status(v){const has=k=>k in v,t=(l,x)=>`<div class="tile"><b>${l}</b><span>${x}</span></div>`,pct=k=>has(k)?v[k]+'%':'–',d=k=>has(k)?v[k]+' days':'–';
 $('status').innerHTML=[t('Power',{1:'On',2:'Off (standby)'}[v['2.1']]??(has('2.1')?'? '+v['2.1']:'–')),
  t('Mode',has('2.3')?MODES[v['2.3']]??'? '+v['2.3']:'–'),t('Fan speed',v['2.4']??'–'),
  t('PM2.5',has('3.5')?v['3.5']+' µg/m³':'–'),t('Air quality',has('3.4')?AQ[v['3.4']]??'level '+v['3.4']:'–'),
  t('Child lock',has('6.10')?(v['6.10']?'On':'Off'):'–'),t('Delayed power off',has('6.8')?(v['6.8']?v['6.8']+' h':'OFF'):'–'),
  t('Pre-filter',pct('4.7')+' · '+d('4.8')),t('High-voltage electrode',pct('4.9')+' · '+d('4.10'))].join('');
 $('stime').textContent='updated '+new Date().toLocaleTimeString()}
let timer=null,busy=false;
function autoRead(){clearInterval(timer);timer=$('auto').checked?setInterval(()=>{if(!busy&&$('dev').value)read()},15000):null}
async function read(){busy=true;try{await doRead()}finally{busy=false}}
async function doRead(){$('rmsg').textContent='reading…';const res=await call({op:'read',did:$('dev').value,props:$('props').value});
 const now={},vals={};res.flat().forEach(p=>{if(p&&p.siid&&p.code===0)vals[p.siid+'.'+p.piid]=p.value});status(vals);
 res.flat().forEach(p=>{if(p&&p.siid)now[p.siid+'.'+p.piid]=p.code===0?JSON.stringify(p.value)+(p.cloud?' (cloud)':''):'err '+p.code});
 $('tbl').innerHTML='<tr><th>prop</th><th>value</th><th>before</th></tr>'+Object.keys(now).map(k=>`<tr><td>${k}</td><td class="${k in last&&last[k]!==now[k]?'chg':''}">${now[k]}</td><td>${last[k]??''}</td></tr>`).join('');
 $('rmsg').textContent=Object.keys(now).length?'':'no data (offline or deep standby?)';last=now}
async function setp(s,p,v){await call({op:'set',did:$('dev').value,siid:s,piid:p,value:String(v)});setTimeout(read,2000)}
</script></body></html>""".replace("__PROPS__", DEFAULT_PROPS)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api":
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self._send(200, handle(req))
        except (ValueError, KeyError, TypeError, RuntimeError) as ex:
            self._send(400, {"error": str(ex)})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Dreame test bench on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
