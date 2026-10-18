"""Build business_agent.ipynb from the SECTION blocks of app.py plus explanatory Markdown and demos.

app.py is the single source of truth for the agent code, so the notebook and the deployed app
cannot drift apart. Re-run after editing app.py:   python scripts/build_notebook.py
"""
import re
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
source = (ROOT / "app.py").read_text(encoding="utf-8")
source = source.split('\nif __name__ == "__main__":')[0]
sections = {name: body.strip("\n") for name, body in
            re.findall(r"# ==== SECTION: (\w+) ====\n(.*?)(?=\n# ==== SECTION: |\Z)", source, re.S)}

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("""# ☀️ SunCedar Energy — Agent-Powered Business Assistant
**EECE 503P/798S Agentic Systems · C3 Introduction to Agents**

This notebook builds **Sunny**, a virtual energy advisor for *SunCedar Energy*, a fictional solar and
battery installer in Beirut. The agent:

| Capability | Where |
|---|---|
| Answers questions grounded in `me/about_business.pdf` and `me/business_summary.txt` | §2, §7 |
| Separates **persona** (who it is) from **instructions** (rules it follows) | §3, §4 |
| **Routes** each message: general question / lead collection / feedback | §6 |
| Collects leads with `record_customer_interest(email, name, message)` via real tool calling | §5, §9 |
| Logs feedback and unanswered questions with `record_feedback(question)` | §5, §9 |
| Keeps short-term memory (chat history) | §9 |
| **Reflection** bonus: drafts, self-checks, revises, logs both | §8 |
| Gradio `ChatInterface` demo | §11 |

### Architecture
```
user message + chat history
        │
        ▼
 ┌──────────────┐   JSON {intent, confidence, reason}
 │   ROUTER     │── general_question │ lead_collection │ feedback
 └──────────────┘
        │  route-specific guidance + allowed tools
        ▼
 ┌──────────────────────────────┐    tool_calls    ┌──────────────────────────┐
 │ AGENT (OpenAI Chat Completions│ ───────────────▶ │ record_customer_interest │──▶ data/leads.jsonl
 │ persona+instructions+knowledge│ ◀─────────────── │ record_feedback          │──▶ data/feedback.jsonl
 └──────────────────────────────┘   tool results    └──────────────────────────┘
        │ draft reply
        ▼
 ┌──────────────┐  verdict approved / revised (draft + final logged)
 │  REFLECTION  │
 └──────────────┘
        │
        ▼
     final reply
```

> The agent code lives in `app.py` (used for deployment). This notebook is generated from the same
> code blocks by `scripts/build_notebook.py`, so both stay identical. Run it from the project root
> with `OPENAI_API_KEY` set in `.env`."""),

    md("""## 1. Setup and configuration
Loads the API key from `.env` (never printed), picks the models (`gpt-5.4` for the agent, `gpt-5.4-mini`
for the router and reflection; override with `OPENAI_MODEL`, `OPENAI_ROUTER_MODEL`, `OPENAI_REFLECTION_MODEL`), and configures **structured logging**: every router decision, tool call,
reflection and reply is logged as `EVENT {json}` to the console and to `data/agent.log`."""),
    code(sections["setup"]),
    code('print(f"Agent model: {MODEL} | router: {ROUTER_MODEL} | reflection: {REFLECTION_MODEL} (enabled={ENABLE_REFLECTION})")\n'
         'print("API key configured:", bool(os.getenv("OPENAI_API_KEY")))'),

    md("""## 2. Business knowledge
Both business documents are loaded and placed in the system prompt, so answers are grounded in them."""),
    code(sections["knowledge"]),
    code('print(f"Summary: {len(BUSINESS_SUMMARY):,} chars | PDF profile: {len(BUSINESS_PROFILE):,} chars")\n'
         'print(BUSINESS_PROFILE[:600], "...")'),

    md("""## 3. 🎭 PERSONA — *who* the agent is
The persona only shapes **identity, tone and style**. It contains no rules about tools or facts."""),
    code(sections["persona"]),

    md("""## 4. 📋 INSTRUCTIONS — *what* the agent must and must not do
Operational guardrails: knowledge boundaries, when to call each tool, how to collect leads, how to
handle unknown and off-topic questions."""),
    code(sections["instructions"]),

    md("""## 5. Tools (MCP-style definitions)
Each tool is documented the way MCP tools are described: **name**, **description**, **inputSchema**
and **outputSchema**. `openai_tool_specs()` converts them to the OpenAI `tools` format.

| Tool | Parameters | Output | Side effect |
|---|---|---|---|
| `record_customer_interest` | `email` (str), `name` (str), `message` (str) | `{status: recorded \\| already_recorded \\| error, lead_id?, errors?}` | validates name and email, appends to `data/leads.jsonl`, push/print notification |
| `record_feedback` | `question` (str) | `{status: recorded \\| error, feedback_id?, errors?}` | appends to `data/feedback.jsonl`, push/print notification |

The tools are only executed when **the model** requests them (`execute_tool_call` is driven by the
model's `tool_calls`). Invalid input, such as a malformed email, is rejected with an error the
model reads and explains to the customer, so incomplete leads are never stored."""),
    code(sections["tools"]),
    code('print(json.dumps(TOOL_DEFINITIONS, indent=2))'),
    code('# Validation check (no API call, nothing is written for invalid input):\n'
         'print(record_customer_interest(email="karim@gmail", name="Karim", message="Comfort package"))\n'
         'print(record_customer_interest(email="karim@example.com", name="", message="Comfort package"))'),

    md("""## 6. Router
A lightweight LLM call (JSON mode) classifies the **latest** message into one of three intents. It
also sees the last few turns, so a bare email address sent after the assistant asked for contact
details is routed to `lead_collection`. Each intent maps to its own handling: extra guidance for
the agent and the set of tools it may use on that path (`ROUTES`)."""),
    code(sections["router"]),
    code('''router_demo = [
    ("What does the Premium package include?", []),
    ("I want a quote for solar at my clinic in Jbeil.", []),
    ("The SunPulse app keeps logging me out, please fix it.", []),
    ("Do you offer a discount for teachers?", []),
    ("karim.aoun.test@example.com", [
        {"role": "user", "content": "I'd like the Essential package."},
        {"role": "assistant", "content": "Great choice! Could I have your name and email?"},
        {"role": "user", "content": "Karim"},
        {"role": "assistant", "content": "Thanks Karim! What's your email address?"}]),
]
for text, hist in router_demo:
    d = route_message(text, hist)
    print(f"{d.intent:<17} ({d.confidence:.2f})  <- {text!r}{'  [with context]' if hist else ''}")'''),

    md("""## 7. System prompt assembly
`system_prompt` = **PERSONA** + **INSTRUCTIONS** + **BUSINESS KNOWLEDGE** (summary + PDF). For each
turn, `build_system_prompt(intent)` appends the router's handling guidance for that path."""),
    code(sections["system_prompt"]),
    code('print([line for line in system_prompt.splitlines() if line.startswith("#")])\n'
         'print(f"system_prompt length: {len(system_prompt):,} chars")'),

    md("""## 8. Reflection step (bonus)
Before replying, a second LLM pass checks the draft against the instructions (grounding, honest
claims about tool results, lead flow, scope and persona) and returns `approved` or a minimally
`revised` reply. The draft and the revision are both logged (`REFLECTION` events)."""),
    code(sections["reflection"]),
    md("""**Reflection check on a deliberately flawed draft.** The draft below invents a discount, claims a
lead was saved although no tool ran, and does not ask for the missing email. The reviewer should
catch these problems and return a revised reply."""),
    code('''flawed = reflect(
    message="I'm Hadi. I'm interested in the Essential package for my apartment.",
    history=[], intent="lead_collection", tool_calls=[],
    draft="Great news Hadi! The Essential package is $3,900, and this month you get a 20% student "
          "discount. I've saved your details and our team will call you tomorrow.")
print("VERDICT:", flawed["verdict"])
print("ISSUES :", *flawed["issues"], sep="\\n  - ")
print("\\nDRAFT  :", flawed["draft"])
print("\\nREVISED:", flawed["final_reply"])'''),

    md("""## 9. Agent loop: memory, tool calling and reflection
`respond(message, history)`:
1. trims chat history to the last 20 messages (**short-term memory**),
2. **routes** the message,
3. calls the model with the route's system prompt, history and **tools**,
4. if the model returns `tool_calls`, **executes them** and sends the results back; this repeats until
   the model answers in text,
5. runs **reflection** on the draft and returns the final reply plus a full trace."""),
    code(sections["agent"]),

    md("""## 10. Live demonstrations
Each demo is a real conversation with the OpenAI API. The `ROUTE`, `TOOL_CALL`, `REFLECTION` and
`REPLY` log lines show what happened at each step."""),
    code('''def run_conversation(turns):
    """Run a multi-turn conversation, carrying the history forward like the Gradio UI does."""
    history = []
    for user_msg in turns:
        r = respond(user_msg, history)
        print(f"\\n👤 USER: {user_msg}\\n🧭 ROUTE: {r.route.intent} | 🔧 TOOLS: "
              f"{[(t['name'], t['result']['status']) for t in r.tool_calls] or 'none'} | "
              f"🪞 REFLECTION: {r.reflection['verdict'] if r.reflection else 'off'}\\n☀️ SUNNY: {r.reply}\\n" + "-" * 90)
        history += [{"role": "user", "content": user_msg}, {"role": "assistant", "content": r.reply}]
    return history'''),
    md("### 10.1 General questions (services, team)"),
    code('_ = run_conversation(["What services does SunCedar offer?", "Who is on your team?"])'),
    md("### 10.2 Unanswered question → `record_feedback`"),
    code('_ = run_conversation(["Which brand of solar panels do you install?"])'),
    md("### 10.3 Multi-turn lead collection (name first, invalid email, then a valid email)"),
    code('_ = run_conversation([\n'
         '    "I\'m interested in the Comfort package for my family home in Batroun.",\n'
         '    "My name is Nadia Farah.",\n'
         '    "nadia.farah@example",\n'
         '    "Sorry, it\'s nadia.farah@example.com",\n'
         '])'),
    md("### 10.4 Customer feedback and an off-topic request"),
    code('_ = run_conversation(["The installation crew left my roof spotless and finished a day early, great job!",\n'
         '                      "Can you write me a Python function that sorts a list?"])'),
    md("### 10.5 Persisted records"),
    code('for path in (LEADS_FILE, FEEDBACK_FILE):\n'
         '    rows = _read_jsonl(path)\n'
         '    print(f"{path.name}: {len(rows)} records; latest:")\n'
         '    for row in rows[-3:]:\n'
         '        print("  ", row)'),

    md("""## 11. Gradio interface
`build_demo()` wraps `chat()` in a `gr.ChatInterface`, which keeps multi-turn history. A side panel
shows the router decision, tool calls and reflection result for the last message. API problems are
shown as a clear error message in the chat instead of failing silently. For the standalone app run
`python app.py` and open http://127.0.0.1:7860."""),
    code(sections["gradio"]),
    code('demo = build_demo()\n'
         'demo.launch(theme=THEME, css=CSS, prevent_thread_lock=True)'),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
})
out = ROOT / "business_agent.ipynb"
nbf.write(nb, out)
print(f"Wrote {out} ({len(cells)} cells)")
