"""LIVE integration tests: the 10 assignment scenarios against the real OpenAI API.

Usage (from the project root):   python tests/run_scenarios.py [--repeat N]
Writes test_results/live_scenarios.md and .json. Records are persisted to a fresh
test_results/live_data/ folder so they can be inspected. Exit code 1 if any check fails.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "test_results"
LIVE_DATA = RESULTS_DIR / "live_data"
shutil.rmtree(LIVE_DATA, ignore_errors=True)
os.environ["BUSINESS_BOT_DATA_DIR"] = str(LIVE_DATA)
sys.path.insert(0, str(ROOT))

import app  # noqa: E402  (must be imported after BUSINESS_BOT_DATA_DIR is set)

if not os.getenv("OPENAI_API_KEY"):
    sys.exit("OPENAI_API_KEY not set: live integration tests cannot run (no results fabricated).")


def has(text, *words):
    return all(w.lower() in text.lower() for w in words)


def tools_named(turn, name, status=None):
    return [t for t in turn.tool_calls if t["name"] == name and (status is None or t["result"]["status"] == status)]


UNCERTAIN = re.compile(r"don.?t have|do not have|not sure|isn.?t (?:in|something)|not (?:available|listed|"
                       r"specified|in our)|no (?:information|details)|can.?t confirm|unable to confirm|"
                       r"passed (?:it|your question|this) (?:on|along)|shared (?:it|your question) with", re.I)
ASKS_EMAIL = re.compile(r"email", re.I)
BRANDS = ["Jinko", "LONGi", "Huawei", "Growatt", "Canadian Solar", "Trina", "SMA", "Victron", "Deye", "Tesla"]

# Each scenario: (id, title, list of user turns, checks(turns, new_leads, new_feedback) -> [(ok, note)])
SCENARIOS = [
    (1, "Ask about the company's services", ["What services does SunCedar Energy offer?"],
     lambda t, L, F: [
         (t[0].route.intent == "general_question", f"route={t[0].route.intent}"),
         (not t[0].tool_calls, "no tools called"),
         (all(re.search(pat, t[0].reply, re.I) for pat in
              [r"audit", r"package|Essential|Comfort|Premium", r"business", r"retrofit", r"CareShield"]),
          "covers all 5 service lines: audit, home packages, business solar, retrofit, CareShield"),
         (not re.search(r"we (?:also )?(?:install|offer) (?:solar water heaters|EV chargers)", t[0].reply, re.I),
          "no invented services"),
     ]),
    (2, "Ask about the company's team", ["Who founded SunCedar, and who else is on the team?"],
     lambda t, L, F: [
         (t[0].route.intent == "general_question", f"route={t[0].route.intent}"),
         (has(t[0].reply, "Rania Haddad", "Karim Aoun"), "names both founders"),
         (has(t[0].reply, "Maya Saliba") and has(t[0].reply, "Elie Nassar"), "names the wider team from the PDF"),
         (not t[0].tool_calls, "no tools called"),
     ]),
    (3, "Unsupported business question", ["Which brand of solar panels and inverters do you install?"],
     lambda t, L, F: [
         (bool(tools_named(t[0], "record_feedback", "recorded")), "record_feedback called by the model, status=recorded"),
         (any("brand" in f["question"].lower() for f in F), "question persisted to feedback.jsonl"),
         (bool(UNCERTAIN.search(t[0].reply)), "reply acknowledges uncertainty"),
         (not any(b.lower() in t[0].reply.lower() for b in BRANDS), "no invented brand names"),
     ]),
    (4, "Interest in a service -> lead collection, then name only, then email (tests 4, 5, 6)",
     ["I'm interested in the Premium package for my villa in Mount Lebanon. How do I get started?",
      "My name is Omar Haddad.",
      "omar.haddad@example.com"],
     lambda t, L, F: [
         (t[0].route.intent == "lead_collection", f"[T4] route={t[0].route.intent}"),
         (not tools_named(t[0], "record_customer_interest", "recorded"), "[T4] no lead recorded without details"),
         (has(t[0].reply, "name") and bool(ASKS_EMAIL.search(t[0].reply)), "[T4] asks for name and email"),
         (t[1].route.intent == "lead_collection", f"[T5] route={t[1].route.intent}"),
         (not tools_named(t[1], "record_customer_interest", "recorded"), "[T5] no lead recorded with name only"),
         (bool(ASKS_EMAIL.search(t[1].reply)), "[T5] asks for the missing email"),
         (t[2].route.intent == "lead_collection", f"[T6] route={t[2].route.intent} (bare email understood in context)"),
         (bool(tools_named(t[2], "record_customer_interest", "recorded")), "[T6] record_customer_interest status=recorded"),
         (any(l["name"] == "Omar Haddad" and l["email"] == "omar.haddad@example.com"
              and "premium" in l["message"].lower() for l in L),
          "[T6] lead persisted with name from earlier turn + Premium in notes"),
         (len(L) == 1, f"[T6] exactly one lead persisted (got {len(L)})"),
     ]),
    (7, "Submit customer feedback",
     ["The SunPulse app is great, but I really wish it had an Arabic language option."],
     lambda t, L, F: [
         (t[0].route.intent == "feedback", f"route={t[0].route.intent}"),
         (bool(tools_named(t[0], "record_feedback", "recorded")), "record_feedback status=recorded"),
         (any("arabic" in f["question"].lower() for f in F), "feedback persisted with key detail (Arabic)"),
         (not tools_named(t[0], "record_customer_interest"), "no lead tool called"),
     ]),
    (8, "Unrelated question", ["Who won the 2022 FIFA World Cup?"],
     lambda t, L, F: [
         (not t[0].tool_calls, "no tools called (off-topic is not logged)"),
         ("argentina" not in t[0].reply.lower(), "does not answer the off-topic question"),
         (has(t[0].reply, "SunCedar") or has(t[0].reply, "solar"), "steers back to SunCedar/solar"),
     ]),
    (9, "Multi-turn short-term memory",
     ["Tell me about the Comfort package.", "How much does it cost?", "And what's the warranty on its battery?"],
     lambda t, L, F: [
         ("6,500" in t[1].reply, "turn 2 resolves 'it' = Comfort -> $6,500"),
         (has(t[2].reply, "10 years") or has(t[2].reply, "6,000"), "turn 3 gives battery warranty (10 years / 6,000 cycles)"),
         (all(not tools_named(x, "record_feedback") for x in t), "no spurious feedback logging"),
     ]),
    (10, "Invalid email, then corrected",
     ["I'd like to book a free energy audit for my apartment in Achrafieh. I'm Rita Nassar.",
      "rita.nassar@gmail",
      "Oops, it's rita.nassar@example.com"],
     lambda t, L, F: [
         (not any(l["email"] == "rita.nassar@gmail" for l in L), "invalid email never persisted"),
         (not tools_named(t[1], "record_customer_interest", "recorded"), "no lead recorded on invalid email turn"),
         (bool(re.search(r"valid|check|correct|complete|missing|full|incomplete|double", t[1].reply, re.I))
          and bool(ASKS_EMAIL.search(t[1].reply)), "asks the user to correct the email"),
         (bool(tools_named(t[2], "record_customer_interest", "recorded")), "corrected email -> lead recorded"),
         (any(l["email"] == "rita.nassar@example.com" and l["name"] == "Rita Nassar" for l in L),
          "corrected lead persisted with name from turn 1"),
     ]),
]


def run_scenario(sid, title, turns, checks):
    leads_before = len(app._read_jsonl(app.LEADS_FILE))
    fb_before = len(app._read_jsonl(app.FEEDBACK_FILE))
    history, results, error = [], [], None
    try:
        for msg in turns:
            r = app.respond(msg, history)
            results.append(r)
            history += [{"role": "user", "content": msg}, {"role": "assistant", "content": r.reply}]
        new_leads = app._read_jsonl(app.LEADS_FILE)[leads_before:]
        new_fb = app._read_jsonl(app.FEEDBACK_FILE)[fb_before:]
        check_results = [(bool(ok), note) for ok, note in checks(results, new_leads, new_fb)]
    except Exception as exc:  # an exception is a failure, never hidden
        error, new_leads, new_fb = f"{type(exc).__name__}: {exc}", [], []
        check_results = [(False, f"exception: {error}")]
    return {
        "id": sid, "title": title, "passed": all(ok for ok, _ in check_results), "error": error,
        "checks": [{"ok": ok, "note": note} for ok, note in check_results],
        "turns": [{"user": m, "route": r.route.__dict__, "tool_calls": r.tool_calls, "reply": r.reply,
                   "reflection": {k: v for k, v in (r.reflection or {}).items() if k != "final_reply"}}
                  for m, r in zip(turns, results)],
        "persisted": {"leads": new_leads, "feedback": new_fb},
    }


def to_markdown(runs):
    lines = [f"# Live scenario results\n\nModel: `{app.MODEL}` · router: `{app.ROUTER_MODEL}` · "
             f"reflection: `{app.REFLECTION_MODEL}` (enabled={app.ENABLE_REFLECTION}) · run at {time.strftime('%Y-%m-%d %H:%M:%S')}\n"]
    for i, run in enumerate(runs, 1):
        passed = sum(s["passed"] for s in run)
        lines.append(f"## Run {i}: {passed}/{len(run)} scenarios passed\n")
        lines.append("| # | Scenario | Result | Checks |\n|---|---|---|---|")
        for s in run:
            checks = "<br>".join(("✅ " if c["ok"] else "❌ ") + c["note"] for c in s["checks"])
            lines.append(f"| {s['id']} | {s['title']} | {'PASS' if s['passed'] else 'FAIL'} | {checks} |")
        lines.append("\n### Transcripts\n")
        for s in run:
            lines.append(f"#### {s['id']}. {s['title']} — {'PASS' if s['passed'] else 'FAIL'}\n")
            for t in s["turns"]:
                tools = ", ".join(f"`{c['name']}({json.dumps(c['arguments'], ensure_ascii=False)})` → "
                                  f"{c['result']['status']}" for c in t["tool_calls"]) or "none"
                refl = t["reflection"].get("verdict", "off")
                lines.append(f"- **User:** {t['user']}\n  - route: `{t['route']['intent']}` "
                             f"({t['route']['confidence']:.2f}) · tools: {tools} · reflection: {refl}\n"
                             f"  - **Sunny:** {t['reply'].replace(chr(10), ' ')}")
                if refl == "revised":
                    lines.append(f"  - _draft before reflection:_ {t['reflection']['draft'].replace(chr(10), ' ')}")
            if s["persisted"]["leads"] or s["persisted"]["feedback"]:
                lines.append(f"- persisted: `{json.dumps(s['persisted'], ensure_ascii=False)}`")
            lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    runs = []
    for run_no in range(1, args.repeat + 1):
        # fresh record files per run, so duplicate-lead protection does not leak across runs
        run_dir = LIVE_DATA / f"run_{run_no}"
        run_dir.mkdir(parents=True, exist_ok=True)
        app.LEADS_FILE, app.FEEDBACK_FILE = run_dir / "leads.jsonl", run_dir / "feedback.jsonl"
        run = []
        for sid, title, turns, checks in SCENARIOS:
            res = run_scenario(sid, title, turns, checks)
            run.append(res)
            print(f"[{'PASS' if res['passed'] else 'FAIL'}] {sid}. {title}")
            for c in res["checks"]:
                print(f"     {'✓' if c['ok'] else '✗'} {c['note']}")
        runs.append(run)
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "live_scenarios.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False))
    (RESULTS_DIR / "live_scenarios.md").write_text(to_markdown(runs))
    total = sum(len(r) for r in runs)
    passed = sum(s["passed"] for r in runs for s in r)
    print(f"\n{passed}/{total} scenario runs passed. Report: test_results/live_scenarios.md")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
