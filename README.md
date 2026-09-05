# ScoutAI — Agentic AI for Student Internship & Hackathon Discovery

ScoutAI is a full-stack **Agentic AI** application that researches internships,
hackathons and coding competitions **for a specific student**. It is not a
search/filter website — it is an agent that plans, searches, reads, extracts,
verifies, checks eligibility, scores, ranks and explains opportunities.

## ✅ What makes it agentic

```
Student profile (terminal) → Planner Agent → Web Search Tool (site-restricted)
    → Researcher Agent → Web Scraper → Opportunity Extractor → Eligibility Agent
    → Match Calculator → Quality Evaluator ── not enough? → back to Planner (re-plan loop)
                                            └─ enough → Recommender Agent → results
```

- **LangGraph** orchestrates the workflow with a bounded re-planning loop
  (`MAX_ITERATIONS`, default 2 rounds).
- Every agent action is recorded in an **agent trace** (printed live in the
  terminal and saved to MongoDB).

## 🚫 Data quality guarantees (no fabricated data)

- Search + scraping are restricted to a **whitelist** of student platforms only.
- The old "default fallback opportunities" (invented data) were removed.
- Missing information is displayed as **"Not specified"** / **"Unable to verify"**.
- LLM-extracted values are validated against the page text (anti-hallucination
  gate) before being accepted.

**Whitelisted sources**

| Internships | Hackathons / competitions |
| --- | --- |
| Internshala, Unstop, LinkedIn Jobs, Indeed India, Wellfound, Naukri, AICTE Internship Portal | Devpost, Unstop, HackerEarth, Devfolio, MLH, CodeChef, HackerRank |

## 🖥 Run in the terminal (the main mode)

```powershell
cd e:\IOC\Scout-AI

# Easiest — double-click this file in Explorer, or run it from a terminal:
.\run.bat

# Or manually:
uv venv .venv --python 3.12      # first time only
uv pip install -r requirements.txt
.venv\Scripts\python.exe cli.py
```

The terminal app has a **rich UI** (powered by the `rich` library): boxed
opportunity cards, colored match-score bars, overview/trace tables and styled
prompts. It:

1. Asks for your profile (or use the built-in demo profile: *Saravanan, College
   of Engineering Guindy, 3rd year IT, CGPA 9.54*).
2. Asks what to find: **Internships / Hackathons & coding competitions / Both**.
3. Runs the agent workflow with a **live agent trace**.
4. Prints ranked opportunities: overview table + detailed cards with match %,
   transparent score bars, eligibility verdict + reason, stipend/prize,
   deadline, skills, and clickable Apply/Source links.
5. Optionally saves everything to MongoDB and lets you bookmark opportunities
   and update application statuses (Saved → Applied → Interview → Selected /
   Rejected).

## 🔑 Optional API keys (`.env`)

Copy `.env.example` → `.env`. Everything works **without** keys; keys make it
better:

- `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`) — LLM query planning, structured
  extraction and natural explanations. Values are still grounded in page text.
- `TAVILY_API_KEY` — better site-restricted web search (free fallback: DuckDuckGo).
- `MONGODB_URI` — persistence (free fallback: skip saving).

## 🌐 Web UI (optional, still available)

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# open frontend/index.html in a browser (posts to http://localhost:8000/discover)
```

## 🧩 Project structure

```
Scout-AI/
├── cli.py                       # ← terminal app (questions → agents → results)
├── app/
│   ├── agents/                  # planner, researcher, eligibility,
│   │                            # quality_evaluator, recommender
│   ├── graph/                   # LangGraph state, workflow (with re-plan loop), live trace
│   ├── tools/                   # web_search, web_scraper, opportunity_extractor,
│   │                            # eligibility_rules, match_calculator, site_registry (whitelist)
│   ├── database/                # mongo_service (CLI), mongodb (async, FastAPI), models
│   ├── llm.py                   # optional Gemini/Claude access (graceful fallback)
│   └── main.py                  # FastAPI /discover endpoint
├── frontend/                    # existing web UI (unchanged behaviour)
└── requirements.txt
```

## ⚙️ Match score (transparent, /100)

| Component | Weight |
| --- | --- |
| Skill match | 40 |
| Education match | 20 |
| Academic year eligibility | 15 |
| CGPA eligibility | 10 |
| Interest match | 10 |
| Location match | 5 |

When a component cannot be evaluated (the source page doesn't state it), it is
scored **neutral (half credit)** and clearly marked — never given full credit.

