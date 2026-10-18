"""Record the captioned submission video of the REAL running app (no voice-over).

A local "stage" page shows a caption bar on top and either a document (business PDF, summary,
notebook, results) or the live Gradio app next to a live view of the server log and the
persisted leads/feedback files. Playwright drives the real app with real OpenAI calls and
records everything to demo/submission_demo.mp4.

Run from the project root:   python scripts/make_demo_video.py
"""
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import nbformat
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo" / "submission_demo.mp4"
APP_PORT, STAGE_PORT = 7860, 8765
W, H = 1920, 1080
STAGE = Path(tempfile.mkdtemp(prefix="suncedar_video_"))
DATA = STAGE / "data"
TOTAL_STEPS = 19
failures = []

STAGE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box} body{margin:0;font-family:Inter,system-ui,sans-serif;background:#0F172A;height:100vh;overflow:hidden}
#cap{height:150px;background:#111827;color:#F9FAFB;padding:18px 36px;border-bottom:4px solid #EA580C}
#step{color:#FDBA74;font-size:18px;font-weight:600;letter-spacing:.04em}
#title{font-size:34px;font-weight:700;margin:4px 0}
#text{font-size:21px;color:#D1D5DB;line-height:1.35}
#main{height:calc(100vh - 150px);background:#F8FAFC}
#doc{width:100%;height:100%;border:0;display:none;background:white}
#appview{display:none;height:100%;width:100%}
#app{width:1180px;height:100%;border:0;background:white;float:left}
#side{margin-left:1180px;height:100%;padding:12px 16px;background:#0B1220;color:#E5E7EB;font-family:ui-monospace,Menlo,monospace;font-size:13.5px;overflow:hidden}
#side h3{font-family:Inter,system-ui,sans-serif;color:#FDBA74;font-size:15px;margin:8px 0 6px}
#log{height:520px;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end}
.l{padding:3px 0;border-bottom:1px solid #1F2937;white-space:pre-wrap;word-break:break-word}
.ev{font-weight:700} .ROUTE{color:#60A5FA}.TOOL_CALL{color:#34D399}.REFLECTION{color:#F472B6}.REPLY{color:#9CA3AF}.ERROR{color:#F87171}.STARTUP{color:#FBBF24}
.rec{background:#111827;border-radius:6px;padding:6px 8px;margin:0 0 5px;white-space:pre-wrap;word-break:break-word}
.new{animation:flash 2.5s ease-out} @keyframes flash{from{background:#14532D}to{background:#111827}}
.empty{color:#6B7280;font-style:italic}
</style></head><body>
<div id="cap"><div id="step"></div><div id="title"></div><div id="text"></div></div>
<div id="main"><iframe id="doc" name="doc"></iframe>
<div id="appview"><iframe id="app" name="appframe"></iframe>
<div id="side"><h3>Server log: data/agent.log (live)</h3><div id="log"></div>
<h3>data/leads.jsonl</h3><div id="leads"></div><h3>data/feedback.jsonl</h3><div id="fb"></div></div></div></div>
<script>
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const cut=(s,n)=>{s=String(s??'');return s.length>n?s.slice(0,n)+'…':s};
function setCaption(step,title,text){document.getElementById('step').textContent=step;document.getElementById('title').textContent=title;document.getElementById('text').textContent=text}
function showDoc(url){const d=document.getElementById('doc');d.src=url;d.style.display='block';document.getElementById('appview').style.display='none'}
function showApp(){document.getElementById('doc').style.display='none';document.getElementById('appview').style.display='block';document.getElementById('app').src='http://127.0.0.1:%APP_PORT%/?t='+Date.now()}
function fmt(ev,d){
 if(ev==='ROUTE')return `intent=${d.intent} (${d.confidence}) · "${cut(d.message,70)}"`;
 if(ev==='TOOL_CALL'){let a=d.arguments;try{a=JSON.stringify(JSON.parse(a))}catch(e){};return `${d.tool}(${cut(a,150)}) → ${d.result.status}${d.result.errors?' '+cut(d.result.errors.join('; '),70):''}`}
 if(ev==='REFLECTION')return `verdict=${d.verdict}${d.issues&&d.issues.length?' · issues: '+cut(d.issues.join('; '),140):''}`;
 if(ev==='REPLY')return `intent=${d.intent} tools=[${d.tools.join(', ')}] · "${cut(d.reply,80)}"`;
 if(ev==='STARTUP')return `model=${d.model} router=${d.router_model} reflection=${d.reflection_model}`;
 return cut(JSON.stringify(d),160)}
const seen={leads:0,fb:0};
async function get(p){try{const r=await fetch(p+'?t='+Date.now());return r.ok?await r.text():''}catch(e){return ''}}
async function poll(){
 const log=(await get('data/agent.log')).trim().split('\\n').filter(Boolean).slice(-16);
 document.getElementById('log').innerHTML=log.map(l=>{const m=l.match(/^(\\d\\d:\\d\\d:\\d\\d) \\| (\\S+)\\s+(.*)$/);if(!m)return '';let d;try{d=JSON.parse(m[3])}catch(e){return ''}
  return `<div class="l">${m[1]} <span class="ev ${m[2]}">${m[2]}</span> ${esc(fmt(m[2],d))}</div>`}).join('');
 for(const [k,f,id,show] of [['leads','data/leads.jsonl','leads',r=>`${r.name} <${r.email}> · ${r.message}`],['fb','data/feedback.jsonl','fb',r=>r.question]]){
  const rows=(await get(f)).trim().split('\\n').filter(Boolean).map(x=>JSON.parse(x));
  document.getElementById(id).innerHTML=rows.length?rows.slice(-3).map((r,i,a)=>`<div class="rec ${rows.length>seen[k]&&i===a.length-1?'new':''}">${esc(r.id)}: ${esc(show(r))}</div>`).join(''):'<div class="empty">(no records yet)</div>';
  seen[k]=rows.length}}
setInterval(poll,700);poll();
</script></body></html>"""

SLIDE_CSS = """<style>body{margin:0;font-family:Inter,system-ui,sans-serif;background:#FFFBF5;color:#1F2937}
.wrap{padding:40px 70px} h1{color:#C2410C;font-size:52px;margin:10px 0} h2{color:#9A3412}
li{font-size:24px;margin:8px 0} table{border-collapse:collapse;font-size:20px;width:100%}
td,th{border:1px solid #FED7AA;padding:8px 12px;text-align:left} th{background:#FFEDD5}
.pass{color:#15803D;font-weight:700} .fail{color:#B91C1C;font-weight:700} pre{font-size:22px;white-space:pre-wrap}</style>"""


def write(name, body):
    (STAGE / name).write_text(f"<!doctype html><html><head><meta charset='utf-8'>{SLIDE_CSS}</head>"
                              f"<body><div class='wrap'>{body}</div></body></html>", encoding="utf-8")


def build_assets():
    DATA.mkdir(parents=True)
    (STAGE / "stage.html").write_text(STAGE_HTML.replace("%APP_PORT%", str(APP_PORT)), encoding="utf-8")
    write("title.html", """<div style="text-align:center;padding-top:90px"><div style="font-size:90px">☀️</div>
<h1>SunCedar Energy: Agent-Powered Business Assistant</h1>
<h2>EECE 503P/798S Agentic Systems · C3 Introduction to Agents</h2>
<ul style="display:inline-block;text-align:left;margin-top:30px">
<li>Persona and instructions defined separately</li><li>Intent router: general / lead collection / feedback</li>
<li>Real OpenAI tool calling: <code>record_customer_interest</code>, <code>record_feedback</code></li>
<li>Short-term memory · reflection bonus · Gradio ChatInterface</li></ul></div>""")
    subprocess.run(["pdftoppm", "-png", "-r", "110", str(ROOT / "me/about_business.pdf"), str(STAGE / "page")], check=True)
    pages = "".join(f"<img src='{p.name}' style='height:900px;margin:0 6px;box-shadow:0 2px 10px #0003'>"
                    for p in sorted(STAGE.glob("page-*.png")))
    (STAGE / "pdf.html").write_text(f"<html><body style='margin:0;background:#E5E7EB;text-align:center;padding-top:15px'>{pages}</body></html>")
    summary = html.escape((ROOT / "me/business_summary.txt").read_text())
    write("summary.html", f"<h2>me/business_summary.txt</h2><pre>{summary}</pre>")
    subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "html", str(ROOT / "business_agent.ipynb"),
                    "--output-dir", str(STAGE), "--output", "notebook"], check=True, capture_output=True)


def build_results_slide():
    pytest_out = subprocess.run([sys.executable, "-m", "pytest", "tests/test_unit.py", "-q"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip().splitlines()[-1]
    runs = json.loads((ROOT / "test_results/live_scenarios.json").read_text())
    rows = ""
    for i, s in enumerate(runs[0]):
        results = [r[i]["passed"] for r in runs]
        rows += (f"<tr><td>{s['id']}</td><td>{html.escape(s['title'])}</td><td class='{'pass' if all(results) else 'fail'}'>"
                 f"{sum(results)}/{len(results)} PASS</td></tr>")
    browser = json.loads((ROOT / "test_results/browser_results.json").read_text())["checks"]
    nb = nbformat.read(ROOT / "business_agent.ipynb", 4)
    code = [c for c in nb.cells if c.cell_type == "code"]
    nb_errors = sum(o.output_type == "error" for c in code for o in c.outputs)
    write("results.html", f"""<h1>Verification results</h1>
<ul><li>Unit tests (offline): <b>{html.escape(pytest_out)}</b></li>
<li>Live OpenAI scenarios: <b>{sum(s['passed'] for r in runs for s in r)}/{sum(len(r) for r in runs)}</b> scenario runs passed ({len(runs)} repeats)</li>
<li>Browser end-to-end (Playwright): <b>{sum(c['ok'] for c in browser)}/{len(browser)}</b> checks passed</li>
<li>Notebook on a clean kernel: <b>{sum(1 for c in code if c.execution_count)}/{len(code)}</b> code cells executed, {nb_errors} errors</li></ul>
<table><tr><th>#</th><th>Live scenario (real API)</th><th>Result</th></tr>{rows}</table>
<p style="font-size:20px">Full transcripts: test_results/live_scenarios.md · test_results/browser_results.md</p>""")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def start_servers():
    httpd = ThreadingHTTPServer(("127.0.0.1", STAGE_PORT), partial(QuietHandler, directory=str(STAGE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    env = {**os.environ, "GRADIO_SERVER_PORT": str(APP_PORT), "BUSINESS_BOT_DATA_DIR": str(DATA), "PYTHONUNBUFFERED": "1"}
    env.pop("PYTHONPATH", None)
    app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/", timeout=2)
            return httpd, app
        except OSError:
            time.sleep(1)
    raise RuntimeError("app did not start")


def main():
    build_assets()
    build_results_slide()
    httpd, app = start_servers()
    video_tmp = STAGE / "video"
    step = 0
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(video_tmp),
                                      record_video_size={"width": W, "height": H})
            page = ctx.new_page()
            page.goto(f"http://127.0.0.1:{STAGE_PORT}/stage.html")

            def caption(title, text):
                nonlocal step
                step += 1
                page.evaluate("a => setCaption(...a)", [f"STEP {step} / {TOTAL_STEPS}", title, text])

            def doc(url, wait=2.0):
                page.evaluate("u => showDoc(u)", url)
                page.wait_for_timeout(int(wait * 1000))

            def doc_scroll(text, block="start", hold=6.0):
                frame = page.frame(name="doc")
                found = frame.evaluate("""([t, b]) => {
                    const els = [...document.querySelectorAll('h1,h2,h3,pre,.jp-OutputArea-output')];
                    const el = els.find(e => e.textContent.includes(t));
                    if (el) el.scrollIntoView({behavior: 'smooth', block: b});
                    return !!el; }""", [text, block])
                if not found:
                    failures.append(f"notebook text not found: {text}")
                page.wait_for_timeout(int(hold * 1000))

            def app_frame():
                return page.frame(name="appframe")

            def open_app():
                page.evaluate("showApp()")
                page.wait_for_timeout(1500)
                app_frame().wait_for_selector("textarea", timeout=60_000)
                app_frame().evaluate("document.body.style.zoom = '1.0'")
                page.wait_for_timeout(800)

            def send(text, expect, hold=4.5):
                f = app_frame()
                n = f.locator("[data-testid='bot']").count()
                f.locator("textarea").click()
                f.locator("textarea").press_sequentially(text, delay=40)
                page.wait_for_timeout(400)
                f.locator("textarea").press("Enter")
                f.wait_for_function("""n => document.querySelectorAll('[data-testid="bot"]').length > n
                       && !document.querySelector('.pending')
                       && /Router|Error/.test(document.querySelector('#trace').innerText)""", arg=n, timeout=150_000)
                trace = f.locator("#trace").inner_text()
                reply = f.locator("[data-testid='bot']").last.inner_text()
                for needle in expect:
                    if needle.lower() not in (trace + reply).lower():
                        failures.append(f"step {step} '{text}': expected '{needle}' in trace/reply")
                page.wait_for_timeout(int(hold * 1000))
                return trace, reply

            # ---------------- the video ----------------
            caption("SunCedar Energy: Sunny, the virtual energy advisor",
                    "A fictional Beirut solar company. Everything that follows is the real app calling the real OpenAI API.")
            doc("title.html", 6)

            caption("Business identity: me/about_business.pdf",
                    "Mission, services and pricing, payment, warranties, process, service area, team and value proposition.")
            doc("pdf.html", 7)
            caption("Business identity: me/business_summary.txt",
                    "A shorter summary that matches the PDF. Both documents go into the system prompt.")
            doc("summary.html", 7)

            caption("Notebook: PERSONA (who the agent is)",
                    "Identity, tone and style only. It is kept separate from the operating rules.")
            doc("notebook.html", 1.5)
            doc_scroll("PERSONA", hold=6.5)
            caption("Notebook: INSTRUCTIONS (the rules)",
                    "Knowledge boundaries, when to call each tool, lead collection, feedback, off-topic handling.")
            doc_scroll("INSTRUCTIONS —", hold=7)
            caption("Notebook: tools with MCP-style schemas",
                    "record_customer_interest(email, name, message) and record_feedback(question): name, description, inputSchema, outputSchema.")
            doc_scroll("Tools (MCP-style definitions)", hold=7)
            caption("Notebook: the intent router",
                    "An LLM classifier using the recent conversation. A bare email sent after the bot asked for it routes to lead_collection.")
            doc_scroll("lead_collection   (", block="center", hold=7)
            caption("Notebook: reflection bonus",
                    "Given a flawed draft (made-up discount, false 'saved' claim), the reviewer flags the problems and returns a revised reply.")
            doc_scroll("VERDICT:", block="center", hold=8)

            caption("The Gradio app: live chat plus the agent's internals",
                    "Left: the ChatInterface with an Agent trace panel. Right: the server log and saved records, updating live.")
            open_app()
            page.wait_for_timeout(4000)

            caption("General question → general_question route",
                    "Sunny answers from the business documents. No tool is needed.")
            send("What solar packages do you offer, and how much do they cost?", ["general_question", "$6,500"], hold=6)

            caption("Lead collection, turn 1: customer shows interest",
                    "The router picks lead_collection. With no name or email yet, Sunny asks for contact details.")
            send("I'm interested in the Comfort package for my family home in Batroun.", ["lead_collection", "email"], hold=5.5)
            caption("Lead collection, turn 2: name only",
                    "Short-term memory keeps the context. Sunny asks for the missing email, and nothing is saved yet.")
            send("My name is Lina Khoury.", ["email"], hold=5)
            caption("Lead collection, turn 3: invalid email",
                    "An incomplete email is rejected. Sunny asks for a correction and leads.jsonl stays empty.")
            send("lina.khoury@example", ["email"], hold=6)
            caption("Lead collection, turn 4: valid email → record_customer_interest",
                    "The model calls the tool with the name from turn 2. Watch the TOOL_CALL log line and the new row in leads.jsonl.")
            send("Sorry, it's lina.khoury@example.com", ["record_customer_interest", "recorded"], hold=8)

            caption("Unanswered business question → record_feedback",
                    "Panel brands are not in the documents. Sunny says so, and the model logs the question for the team.")
            open_app()
            send("Which brand of solar panels do you install?", ["record_feedback", "recorded"], hold=8)

            caption("Customer feedback → feedback route → record_feedback",
                    "Clicking an example prompt. The compliment is summarised and saved to feedback.jsonl.")
            open_app()
            f = app_frame()
            n = f.locator("[data-testid='bot']").count()
            f.get_by_role("button", name="Select example 5: Your installation crew was fantastic, thank you!").click()
            f.wait_for_function("""n => document.querySelectorAll('[data-testid="bot"]').length > n
                   && !document.querySelector('.pending')""", arg=n, timeout=150_000)
            if "record_feedback" not in f.locator("#trace").inner_text():
                failures.append("example feedback: record_feedback not shown")
            page.wait_for_timeout(8000)

            caption("Off-topic request: stays in scope",
                    "Sunny politely declines and steers back to SunCedar. No tool is called.")
            send("Who won the 2022 FIFA World Cup?", ["No tools called"], hold=6)

            caption("Short-term memory: follow-up questions",
                    "\"How much does it cost?\" is resolved as the Comfort package from the previous turn.")
            send("Tell me about the Comfort package.", ["Comfort"], hold=3.5)
            send("How much does it cost?", ["6,500"], hold=7)

            caption("Verification",
                    "Unit tests, live API scenarios, browser tests and a clean notebook run (numbers from the real test reports).")
            doc("results.html", 10)

            video = page.video.path()
            ctx.close()
            browser.close()
    finally:
        app.terminate()
        httpd.shutdown()

    OUT.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-c:v", "libx264", "-preset", "slow",
                    "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)], check=True)
    shutil.rmtree(STAGE, ignore_errors=True)
    print(f"steps captioned: {step} (expected {TOTAL_STEPS})")
    print(f"Wrote {OUT}")
    if failures:
        print("EXPECTATION FAILURES (re-record):", *failures, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    main()
