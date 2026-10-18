# Demo video script (about 4–5 minutes)

> A captioned video is already recorded at `demo/submission_demo.mp4`
> (`python scripts/make_demo_video.py`). Use this script only if you want to record a narrated
> version yourself.

**Setup before recording:** put a terminal running `python app.py` side by side with the browser
at http://127.0.0.1:7860, so the `ROUTE` / `TOOL_CALL` / `REFLECTION` log lines are visible. Clear
old records first with `rm -f data/*.jsonl`. Never show `.env`.

| # | Show | Say / type | What viewers should see |
|---|---|---|---|
| 1 | `me/about_business.pdf`, `me/business_summary.txt` | "SunCedar Energy is a fictional solar installer: mission, services, pricing, team." | The business documents |
| 2 | Notebook §3–§4 | "The persona says who Sunny is; the instructions are the rules it follows." | Separate labeled `PERSONA` and `INSTRUCTIONS` cells |
| 3 | Notebook §5 | "Two tools, defined with MCP-style schemas." | `TOOL_DEFINITIONS` output |
| 4 | Notebook §6 output | "The router classifies each message, using the conversation for context." | The router demo table, including the bare email routed to `lead_collection` |
| 5 | Browser | Type **What solar packages do you offer, and how much do they cost?** | Correct prices. Trace panel: `general_question`, no tools, reflection result |
| 6 | Browser | **I'm interested in the Comfort package for my family home in Batroun.** | `lead_collection`; Sunny asks for name and email |
| 7 | Browser | **My name is Lina Khoury.** | Asks for the email; nothing recorded |
| 8 | Browser | **lina.khoury@example** | The tool rejects the invalid email (⚠️ error in the trace); Sunny asks for a correction |
| 9 | Browser + terminal | **Sorry, it's lina.khoury@example.com** | ✅ `record_customer_interest → recorded`; `[PUSH] New lead ...` in the terminal |
| 10 | Terminal | `cat data/leads.jsonl` | The saved lead with the name from step 7 |
| 11 | Browser (refresh the page) | **Which brand of solar panels do you install?** | Sunny says it doesn't know; ✅ `record_feedback → recorded` |
| 12 | Browser | Click the example **Your installation crew was fantastic, thank you!** (refresh first, since examples only show in an empty chat) | `feedback` route; `record_feedback` called |
| 13 | Browser | **Who won the 2022 FIFA World Cup?** | Politely declined; no tools called |
| 14 | Browser | **Tell me about the Comfort package.**, then **How much does it cost?** | Memory: "it" is understood as Comfort ($6,500) |
| 15 | Terminal / notebook §8 | "Reflection checks every draft before it is sent." | `REFLECTION` log lines. Notebook §8: a flawed draft is revised (invented discount removed, false "saved" claim removed, email requested) |
| 16 | Terminal | `cat data/feedback.jsonl`, then `python -m pytest tests/test_unit.py -q` | Saved feedback; tests passing |

Mention the live test report (`test_results/live_scenarios.md`: 10 scenarios, 3 runs, all
passing) to close.
