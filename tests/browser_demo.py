"""End-to-end browser test of the real Gradio app with Playwright.

Starts two app.py servers (real API key on :7860, deliberately invalid key on :7870), drives the
UI like a user, saves screenshots to screenshots/, records a walkthrough video to demo/, and writes
test_results/browser_results.{json,md}. Run from the project root:

    python tests/browser_demo.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS, RESULTS, DEMO = ROOT / "screenshots", ROOT / "test_results", ROOT / "demo"
BROWSER_DATA = RESULTS / "browser_data"
MAIN_PORT, ERROR_PORT = 7860, 7870
checks, transcript, console_errors = [], [], []


def check(ok, note):
    checks.append({"ok": bool(ok), "note": note})
    print(f"  {'✓' if ok else '✗'} {note}")


def start_server(port, extra_env):
    env = {**os.environ, "GRADIO_SERVER_PORT": str(port), "PYTHONUNBUFFERED": "1", **extra_env}
    env.pop("PYTHONPATH", None)
    log = open(RESULTS / f"server_{port}.log", "w")
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(90):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return proc
        except OSError:
            time.sleep(1)
    proc.terminate()
    raise RuntimeError(f"server on port {port} did not start; see test_results/server_{port}.log")


def shot(page, name):
    page.wait_for_timeout(400)
    page.screenshot(path=str(SHOTS / name), full_page=True)
    print(f"  📸 screenshots/{name}")


def send(page, text, pause_ms=1800):
    """Type a message like a user, press Enter and wait until the bot reply AND trace are rendered."""
    n = page.locator("[data-testid='bot']").count()
    box = page.locator("textarea")
    box.click()
    box.press_sequentially(text, delay=18)
    page.keyboard.press("Enter")
    page.wait_for_function(
        """n => document.querySelectorAll('[data-testid="bot"]').length > n
               && !document.querySelector('.pending')
               && /Router|Error/.test(document.querySelector('#trace').innerText)""",
        arg=n, timeout=150_000)
    page.wait_for_timeout(pause_ms)
    turn = {"user": text, "reply": page.locator("[data-testid='bot']").last.inner_text(),
            "trace": page.locator("#trace").inner_text()}
    transcript.append(turn)
    print(f"  👤 {text}\n  ☀️ {turn['reply'][:160].replace(chr(10), ' ')}...")
    return turn


def wait_ready(page, url):
    page.goto(url, wait_until="load")
    page.wait_for_selector("textarea", timeout=60_000)
    page.wait_for_timeout(1000)


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def main():
    for d in (SHOTS, RESULTS, DEMO):
        d.mkdir(exist_ok=True)
    shutil.rmtree(BROWSER_DATA, ignore_errors=True)
    servers = [start_server(MAIN_PORT, {"BUSINESS_BOT_DATA_DIR": str(BROWSER_DATA)}),
               start_server(ERROR_PORT, {"BUSINESS_BOT_DATA_DIR": str(BROWSER_DATA / "error_instance"),
                                         "OPENAI_API_KEY": "sk-invalid-demo-key"})]
    video_tmp = RESULTS / "video_tmp"
    reflection_revised_shot = False
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1400, "height": 900},
                                      record_video_dir=str(video_tmp),
                                      record_video_size={"width": 1400, "height": 900})
            page = ctx.new_page()
            page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
            page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

            def note_reflection(turn, name):
                nonlocal reflection_revised_shot
                check("Reflection" in turn["trace"], f"{name}: reflection result shown in trace")
                if "Draft revised" in turn["trace"] and not reflection_revised_shot:
                    shot(page, "10_reflection_revised.png")
                    reflection_revised_shot = True

            print("1. Initial interface")
            wait_ready(page, f"http://127.0.0.1:{MAIN_PORT}/")
            check(page.get_by_text("SunCedar Energy · Virtual Energy Advisor").is_visible(), "title visible")
            check(page.locator("button.example").count() == 5, "5 example prompts rendered")
            shot(page, "01_initial_interface.png")

            print("2. General business question")
            t = send(page, "What solar packages do you offer, and how much do they cost?")
            check("general_question" in t["trace"], "routed to general_question")
            check(all(x in t["reply"] for x in ("$3,900", "$6,500", "$9,800")), "reply lists the 3 real package prices")
            shot(page, "02_general_question.png")
            note_reflection(t, "general")

            print("3. Multi-turn lead collection")
            t = send(page, "I'm interested in the Comfort package for my family home in Batroun.")
            check("lead_collection" in t["trace"], "interest routed to lead_collection")
            check("email" in t["reply"].lower(), "asks for contact details")
            shot(page, "03_lead_interest.png")
            note_reflection(t, "lead 1")
            t = send(page, "My name is Lina Khoury.")
            check("lead_collection" in t["trace"] and "email" in t["reply"].lower(), "name only -> asks for email")
            check("→ recorded" not in t["trace"], "no lead recorded with name only")
            shot(page, "04_lead_name_only.png")
            note_reflection(t, "lead 2")
            t = send(page, "lina.khoury@example")
            check("→ recorded" not in t["trace"], "invalid email -> nothing recorded")
            check("email" in t["reply"].lower(), "asks to correct the email")
            shot(page, "05_lead_invalid_email.png")
            note_reflection(t, "lead 3")
            t = send(page, "Sorry, it's lina.khoury@example.com")
            check("record_customer_interest` → recorded" in t["trace"] or
                  ("record_customer_interest" in t["trace"] and "recorded" in t["trace"]),
                  "record_customer_interest executed with status recorded (trace panel)")
            leads = read_jsonl(BROWSER_DATA / "leads.jsonl")
            check(any(l["email"] == "lina.khoury@example.com" and l["name"] == "Lina Khoury" for l in leads),
                  "lead persisted to leads.jsonl with name from an earlier turn")
            shot(page, "06_lead_recorded.png")
            note_reflection(t, "lead 4")

            print("4. Unsupported question (fresh session)")
            wait_ready(page, f"http://127.0.0.1:{MAIN_PORT}/")
            t = send(page, "Which brand of solar panels do you install?")
            check("record_feedback" in t["trace"] and "recorded" in t["trace"], "record_feedback executed (trace panel)")
            check(any("brand" in f["question"].lower() for f in read_jsonl(BROWSER_DATA / "feedback.jsonl")),
                  "unanswered question persisted to feedback.jsonl")
            shot(page, "07_unanswered_question_feedback_tool.png")
            note_reflection(t, "unanswered")

            print("5. Feedback via example button (examples only show in an empty chat: fresh session)")
            wait_ready(page, f"http://127.0.0.1:{MAIN_PORT}/")
            n = page.locator("[data-testid='bot']").count()
            page.get_by_role("button", name="Select example 5: Your installation crew was fantastic, thank you!").click()
            page.wait_for_function("""n => document.querySelectorAll('[data-testid="bot"]').length > n
                                       && !document.querySelector('.pending')""", arg=n, timeout=150_000)
            page.wait_for_timeout(1800)
            trace = page.locator("#trace").inner_text()
            transcript.append({"user": "(example) Your installation crew was fantastic, thank you!",
                               "reply": page.locator("[data-testid='bot']").last.inner_text(), "trace": trace})
            check("feedback" in trace and "record_feedback" in trace, "example click -> feedback route + record_feedback")
            shot(page, "08_feedback_via_example.png")

            print("6. Off-topic request")
            t = send(page, "Can you help me with my calculus homework?")
            check("No tools called" in t["trace"], "no tool called for off-topic request")
            shot(page, "09_off_topic.png")
            note_reflection(t, "off-topic")

            if not reflection_revised_shot:
                print("6b. Reflection revision (real prompts that triggered revisions in earlier runs)")
                for prompt in ["Is the Comfort package enough for two AC units and an electric oven at night?",
                               "The SunPulse app is great, but I really wish it had an Arabic language option.",
                               "I'm interested in the Premium package for my villa in Mount Lebanon. How do I get started?"]:
                    wait_ready(page, f"http://127.0.0.1:{MAIN_PORT}/")
                    note_reflection(send(page, prompt), "reflection attempt")
                    if reflection_revised_shot:
                        break

            video_path = page.video.path()
            ctx.close()

            print("7. Mobile layout")
            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
            wait_ready(mobile, f"http://127.0.0.1:{MAIN_PORT}/")
            overflow = mobile.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(overflow <= 1, f"no horizontal scroll at 390px width (overflow={overflow}px)")
            shot(mobile, "11_mobile_layout.png")
            mobile.close()

            print("8. API unavailable (invalid key instance)")
            err = browser.new_page(viewport={"width": 1400, "height": 900})
            wait_ready(err, f"http://127.0.0.1:{ERROR_PORT}/")
            t = send(err, "What packages do you offer?", pause_ms=800)
            check("temporarily unavailable" in t["reply"] and "rejected our API key" in t["reply"],
                  "clear error message shown in chat")
            check("sk-invalid" not in t["reply"] and "sk-invalid" not in t["trace"], "no key material shown in UI")
            shot(err, "12_api_error_handling.png")
            browser.close()

        check(not console_errors, f"no browser console errors ({len(console_errors)} found)")
        print(f"  reflection revision captured in UI: {reflection_revised_shot}"
              + ("" if reflection_revised_shot else " (see notebook §8 for a forced example)"))

        webm = DEMO / "demo_walkthrough.webm"
        shutil.move(video_path, webm)
        mp4 = DEMO / "demo_walkthrough.mp4"
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart", str(mp4)], check=True)
            webm.unlink()
        shutil.rmtree(video_tmp, ignore_errors=True)
    finally:
        for s in servers:
            s.terminate()

    passed = sum(c["ok"] for c in checks)
    (RESULTS / "browser_results.json").write_text(json.dumps(
        {"checks": checks, "console_errors": console_errors, "transcript": transcript,
         "reflection_revised_captured": reflection_revised_shot}, indent=2, ensure_ascii=False))
    md = [f"# Browser test results\n\n{passed}/{len(checks)} checks passed · "
          f"run at {time.strftime('%Y-%m-%d %H:%M:%S')}\n", "| Result | Check |", "|---|---|"]
    md += [f"| {'✅' if c['ok'] else '❌'} | {c['note']} |" for c in checks]
    md.append(f"\nConsole errors: {console_errors or 'none'}\n\n## Transcript\n")
    for t in transcript:
        md.append(f"**User:** {t['user']}\n\n**Sunny:** {t['reply']}\n\n<details><summary>Trace</summary>\n\n"
                  f"```\n{t['trace']}\n```\n</details>\n")
    (RESULTS / "browser_results.md").write_text("\n".join(md))
    print(f"\n{passed}/{len(checks)} browser checks passed")
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
