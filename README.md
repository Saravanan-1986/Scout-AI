# ScoutAI — Agentic AI for Student Internship & Hackathon Discovery


# DEMO VIDEOS:

  Terminal - https://drive.google.com/file/d/1RJGLpMMDPb4oEXV98vhlxnCRGGEaJgNc/view?usp=drive_link

  Browser - https://drive.google.com/file/d/1Zuix6sbSF1hlgi3E3MBhmR3uEhbLC2NQ/view?usp=drive_link
  

## 📌 Project Description

ScoutAI is a **Agentic AI web application** designed specifically for
college students to discover relevant **internships, hackathons, coding
competitions and technical competitions**.

The core problem it solves: students currently have to manually search multiple
websites (Internshala, Unstop, Devpost, Devfolio, AICTE Internship Portal,
HackerEarth, etc.) and manually check eligibility, deadlines, stipends and
prizes for every opportunity.

Instead of simply displaying a list of opportunities (a normal search/filter
website), **ScoutAI behaves as a personal research agent**:

1. It understands the student's profile (college, degree, year, CGPA, skills,
   technologies, interests, preferred locations).
2. It plans what to search and **dynamically generates search queries**.
3. It searches only curated, whitelisted student platforms.
4. It **reads the actual opportunity webpages**.
5. It extracts structured opportunity information — **never inventing data**.
6. It checks the student's **eligibility** against each opportunity.
7. It calculates a **transparent, personalized 0–100 match score**.
8. It **ranks** the opportunities and **explains why each one matches**.
9. It evaluates result quality and **re-searches with a new strategy** when the
   collected results are insufficient.
10. It stores everything in **MongoDB** and presents it in a rich **terminal UI**
    (main mode) and a **web UI**.

**Scope:** internships, hackathons, coding competitions, technical competitions.
Not included: general jobs, scholarships, courses, freelancing or unrelated
features.

---

## 🤖 What Makes It Agentic

ScoutAI does **not** use a fixed pipeline like
`User → Search → Filter → Display`. It is orchestrated by **LangGraph** with a
bounded autonomous **re-planning loop**:

```
Student Profile
      ↓
Planner Agent ───────────────► creates a search strategy + dynamic queries
      ↓
Web Search Tool ─────────────► searches ONLY whitelisted sites (Tavily / DuckDuckGo)
      ↓
Researcher Agent ────────────► collects, deduplicates & prioritizes URLs
      ↓
Web Scraper ─────────────────► Reads pages (Requests → Playwright for JS-only)
      ↓
Opportunity Extractor ───────► structured opportunity (grounded in page text)
      ↓
Eligibility Agent ───────────► ELIGIBLE / POSSIBLY ELIGIBLE / NOT ELIGIBLE / UNKNOWN
      ↓
Match Calculator ────────────► transparent 100-point score
      ↓
Quality Evaluator ───────────► "Enough relevant results?"
      ├── NO  → back to Planner (generates DIFFERENT queries) ──► search again
      └── YES → Recommender Agent ──► ranked recommendations with explanations
                                            ↓
                                    Save to MongoDB → Terminal / Web UI
```

- **LangGraph** (`app/graph/workflow.py`) orchestrates the agents and the
  conditional edge `quality_evaluator → planner (replan)`.
- The re-plan loop is **bounded** by `MAX_ITERATIONS` (default 3 rounds), so it
  can never run forever.
- Every agent action is recorded in a **live agent trace** — printed in the
  terminal in real time and persisted to MongoDB (`agent_traces`).

---

## ✅ Data Quality Guarantees (No Fabricated Data)

ScoutAI **never invents** opportunities. Every result must come from a real,
whitelisted source page:

- Search and scraping are restricted to the **whitelisted platforms below** —
  random web pages can never enter the pipeline.
- Missing information is always shown as **"Not specified"** /
  **"Unable to verify"** — never guessed.
- LLM-extracted values (from Gemini) are accepted **only when they are grounded
  in the actual page text** (anti-hallucination gate).
- Every opportunity carries its **source URL** so you can verify it yourself.
- Opportunities with **passed deadlines / concluded events / past editions**
  are automatically filtered out, so only current & upcoming items are shown.
- The old fabricated "default fallback opportunities" were removed entirely.

### Whitelisted sources — Internships (full URLs)

| Platform | URL |
| --- | --- |
| Internshala | https://internshala.com/internships/ |
| Unstop | https://unstop.com/internships |
| LinkedIn Jobs | https://www.linkedin.com/jobs/ |
| Indeed India | https://in.indeed.com/jobs?q=internship |
| Wellfound | https://wellfound.com/jobs |
| Naukri | https://www.naukri.com/internship-jobs |
| AICTE Internship Portal | https://internship.aicte-india.org/ |

### Whitelisted sources — Hackathons / Coding Competitions (full URLs)

| Platform | URL |
| --- | --- |
| Devpost | https://devpost.com/hackathons |
| Unstop | https://unstop.com/hackathons |
| HackerEarth | https://www.hackerearth.com/challenges/ |
| Devfolio | https://devfolio.co/hackathons |
| MLH | https://mlh.io/seasons/2026/events |
| CodeChef | https://www.codechef.com/contests |
| HackerRank | https://www.hackerrank.com/contests |

---

## 🔑 API Keys Used (`.env`)

Copy `.env.example` → `.env` and fill in what you have. **Everything works
without keys** (rule-based + free DuckDuckGo fallback), but keys make results
better and the app much faster:

| Key | Purpose | Where to get it |
| --- | --- | --- |
| `GEMINI_API_KEY` | LLM query planning, structured opportunity extraction and natural "why this matches you" explanations. Values are still validated against page text. | https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | Optional — defaults to `models/gemini-3.6-flash`. | — |
| `TAVILY_API_KEY` | Reliable, site-restricted web search (1,000 free searches/month). Without it the app falls back to DuckDuckGo. | https://tavily.com |
| `MONGODB_URI` | MongoDB connection string (local or Atlas). Without it results simply aren't persisted. | Local: `mongodb://localhost:27017` · Atlas: https://cloud.mongodb.com |

```dotenv
GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=models/gemini-3.6-flash
TAVILY_API_KEY=your_tavily_api_key_here
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=scout_ai
```

---

## 🚀 Running the Project

### 1) Running via Terminal (MAIN MODE)

Fresh pull from GitHub — PowerShell / CMD on Windows:

```powershell
# 1. Clone the repository
git clone https://github.com/<your-user>/Scout-AI.git
cd Scout-AI

# 2. Create a virtual environment (first time only)
python -m venv .venv

# 3. Activate it
.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. (Optional) create the env file and paste your API keys
copy .env.example .env
#   → then edit .env and add your GEMINI_API_KEY / TAVILY_API_KEY / MONGODB_URI

# 6. Run ScoutAI — the terminal app (MAIN MODE)
.venv\Scripts\python.exe cli.py

# ...or, when the venv is active:
python cli.py
```

> 💡 On Windows you can also just **double-click `run.bat`** in File Explorer,
> or run it **from a terminal** with `.\run.bat` — it creates the venv on first
> run, sets UTF-8 and starts the app.

**What you'll see (rich terminal UI, powered by `rich`):**

1. **STEP 1 · Your Profile** — enter your details manually, or use the built-in
   demo profile (*Saravanan, College of Engineering Guindy, 3rd Year IT,
   CGPA 9.54*).
2. **STEP 2 · What should ScoutAI find?** — choose **Internships** /
   **Hackathons & coding competitions** / **Both**.
3. **STEP 3 · Agent workflow running** — a live, color-coded agent trace
   (planner → researcher → eligibility → match → quality → recommender)
   streams as the agents work.
4. **Ranked results** — an overview table + detailed opportunity cards with
   match %, transparent score bars, eligibility verdict + reason, stipend/prize,
   deadline, skills, and clickable **Apply** / **Source** links.
5. **What next?** — view the full agent trace, bookmark opportunities, update
   application statuses (Saved → Applied → Interview → Selected → Rejected),
   search again, or exit.

> The terminal is the **primary, main mode** of ScoutAI.

### 2) Running via Frontend (Web UI)

The web UI mirrors the terminal: fill the profile form, choose what to find,
watch the **live agent trace** stream, and get the same detailed opportunity
cards.

```powershell
# Terminal 1 — start the FastAPI backend
cd Scout-AI
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# → API runs at http://localhost:8000  (POST /discover streams the workflow)
```

```powershell
# Terminal 2 — open the frontend (CORS is already enabled for local use)
start frontend\index.html
# or simply double-click frontend/index.html in File Explorer
```

The page connects to `http://localhost:8000/discover`, which now **streams**
trace events + opportunities in real time — same results and presentation as
the terminal.

---

## 🧩 Project Structure

```
Scout-AI/
├── cli.py                        # Terminal app (main mode): questions → agents → results
├── run.bat                       # One-click Windows launcher (creates venv + runs cli.py)
├── requirements.txt
├── .env.example                  # Template for API keys (copy to .env)
├── app/
│   ├── main.py                   # FastAPI backend — POST /discover (streaming SSE)
│   ├── llm.py                    # Optional Gemini / Claude access (graceful fallback)
│   ├── config.py                 # All tunable settings (iterations, limits, timeouts)
│   ├── agents/
│   │   ├── planner.py            # Agent 1 — profiles → dynamic search strategy/queries
│   │   ├── researcher.py         # Agent 2 — search, dedupe, rank, concurrent scrape, extract
│   │   ├── eligibility.py        # Agent 4 — eligibility verdicts (ELIGIBLE/…/UNKNOWN)
│   │   ├── quality_evaluator.py  # “Enough results?” → replan or finish (bounded loop)
│   │   └── recommender.py        # Agent 5 — rank, cap at 10, explain each pick
│   ├── graph/
│   │   ├── state.py              # LangGraph AgentState
│   │   ├── workflow.py           # LangGraph orchestration + re-plan conditional edge
│   │   └── trace.py              # Global live agent-trace store (terminal + SSE sink)
│   ├── tools/
│   │   ├── site_registry.py      # Whitelist of student platforms (search/scrape ONLY these)
│   │   ├── web_search.py         # Tool 1 — Tavily search (DuckDuckGo fallback), site-restricted
│   │   ├── web_scraper.py        # Tool 2 — Requests → BeautifulSoup → Playwright, concurrent
│   │   ├── opportunity_extractor.py  # Tool 3 — page → structured opportunity (grounded)
│   │   ├── match_calculator.py   # Tool 4 — transparent 0–100 match score
│   │   ├── eligibility_rules.py  # Rule-based eligibility checks (degree/year/CGPA/skills)
│   │   ├── freshness.py          # Deadline / past-edition / concluded-event filtering
│   │   └── opp_cache.py          # MongoDB-backed opportunity cache (don’t re-scrape)
│   └── database/
│       ├── mongo_service.py      # Sync pymongo service used by the CLI
│       ├── mongodb.py            # Async motor setup for FastAPI
│       └── models.py             # Pydantic models (StudentProfile, Opportunity, …)
└── frontend/
    ├── index.html                # Web UI — profile form + live trace + results
    ├── script.js                 # Streaming client + terminal-style card rendering
    └── style.css                 # Styles (trace panel, score bars, badges, cards)
```

---

## 🛠️ Tools Used (and what each one does)

ScoutAI's agents use a small set of well-defined tools. Each tool has a clear
**input → output** contract, and no tool ever invents data.

| Tool | File | What it does | Input → Output |
| --- | --- | --- | --- |
| **Web Search** | `app/tools/web_search.py` | Searches the web **restricted to whitelisted sites only** (Tavily when a key is set, otherwise a free DuckDuckGo fallback). | Search query → `[{title, url, content, source}]` |
| **Web Scraper** | `app/tools/web_scraper.py` | Fetches a page with `requests`, parses it with BeautifulSoup, and re-renders it with **Playwright** when the page is JavaScript-only. Pages are scraped **concurrently** and cached in memory. | URL → `{ok, title, text, links, status, ...}` |
| **Opportunity Extractor** | `app/tools/opportunity_extractor.py` | Turns raw page text into a structured opportunity. Rule-based extraction first; Gemini refinement only when values are **grounded in the page text**. Missing fields → `"Not specified"`. | Webpage → opportunity dict (`title`, `organization`, `deadline`, `stipend`, `prize`, `required_skills`, ...) |
| **Eligibility Rules** | `app/tools/eligibility_rules.py` | Compares the student profile against the opportunity's stated requirements (degree, department, year, CGPA, skills, location). Never assumes eligibility. | Profile + opportunity → `ELIGIBLE` / `POSSIBLY ELIGIBLE` / `NOT ELIGIBLE` / `UNKNOWN` + reason |
| **Match Calculator** | `app/tools/match_calculator.py` | Pure-Python, transparent 0–100 score (Skill 40 · Education 20 · Year 15 · CGPA 10 · Interest 10 · Location 5). Unknown components get half credit + a note. | Profile + eligibility → `{total, label, breakdown}` |
| **Freshness Check** | `app/tools/freshness.py` | Skips past editions, concluded events and passed deadlines so only current/upcoming opportunities survive. | URL + page text → `(fresh: bool, reason)` |
| **Site Registry** | `app/tools/site_registry.py` | The whitelist of student platforms. Search and scraping are **only** allowed on these domains. | URL → site info, `is_detail_url(url)`, `is_aggregate_url(url)` |
| **Opportunity Cache** | `app/tools/opp_cache.py` | MongoDB-backed cache — recently scraped opportunities (< 24 h) are reused instead of re-scraped. | URL → cached opportunity or `None` |
| **Database Tool** | `app/database/mongo_service.py` | Saves profiles, opportunities, search history, agent traces and bookmarks to MongoDB (local or Atlas). | Save/query calls → writes/reads in the `scout_ai` database |
| **Agent Trace** | `app/graph/trace.py` | Records every agent action live (planner, researcher, eligibility, ...) and streams it to the terminal / frontend. | Agent + action + details → trace step |

**Which agent uses which tool:**

| Agent | Tools it uses |
| --- | --- |
| Planner Agent | Web Search (generates the dynamic queries) |
| Researcher Agent | Web Search, Web Scraper, Opportunity Extractor, Freshness Check, Opportunity Cache, Site Registry |
| Eligibility Agent | Eligibility Rules (pure Python) |
| Match Calculator | Match Calculator (pure Python) |
| Quality Evaluator | Agent Trace + result counts → decides replan / finish |
| Recommender Agent | ranks the scored opportunities, caps at 10, explains each pick |

---

## ⚙️ Match Score (Transparent, /100)

| Component | Weight |
| --- | --- |
| Skill match | 40 |
| Education match | 20 |
| Academic year eligibility | 15 |
| CGPA eligibility | 10 |
| Interest match | 10 |
| Location match | 5 |

When a component cannot be evaluated (the source page doesn't state it), it is
scored **neutral (half credit)** and clearly marked — never silently given full
credit.

