"""ScoutAI — Agentic AI for Student Internship & Hackathon Discovery (terminal app).

Run:
    python cli.py        (or double-click run.bat)

The app asks you questions in the terminal, runs the multi-agent LangGraph
workflow with a live agent-trace output, and prints personalized, source-linked
results in a rich terminal UI. Data comes ONLY from whitelisted
student-opportunity sites — nothing is fabricated; missing information is
shown as "Not specified".
"""

import os
import sys
import uuid
from typing import Any, Dict, List

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import FloatPrompt, IntPrompt, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from app.config import settings
from app.database.mongo_service import APPLICATION_STATUSES, MongoService
from app.graph import trace
from app.graph.workflow import scout_graph

console = Console(highlight=False)

# ------------------------------- theme ------------------------------------- #
TYPE_LABELS = {
    "internship": ("INTERNSHIP", "magenta"),
    "hackathon": ("HACKATHON", "bright_blue"),
    "coding_competition": ("CODING COMPETITION", "cyan"),
}

STATUS_STYLES = {
    "ELIGIBLE": "bold green",
    "POSSIBLY ELIGIBLE": "bold yellow",
    "NOT ELIGIBLE": "bold red",
    "UNKNOWN": "grey58",
}

AGENT_STYLES = {
    "planner": "magenta",
    "researcher": "bright_blue",
    "eligibility": "cyan",
    "match_calculator": "yellow",
    "quality_evaluator": "green",
    "recommender": "bright_red",
}

AGENT_ICONS = {
    "planner": "◆",
    "researcher": "◇",
    "eligibility": "●",
    "match_calculator": "◐",
    "quality_evaluator": "◑",
    "recommender": "★",
}

COMPONENT_LABELS = {
    "skill": "Skill",
    "education": "Education",
    "year": "Year",
    "cgpa": "CGPA",
    "interest": "Interest",
    "location": "Location",
}

BANNER_ART = r"""
   ____            _    ____ _   _
  / ___|  ___ __ _| |__/ ___| | | |_   _  __ _  __ _  ___
  \___ \ / __/ _` | '_ \___ \ | | | | | |/ _` |/ _` |/ _ \
   ___) | (_| (_| | |_) |__) | |_| | |_| | (_| | (_| |  __/
  |____/ \___\__,_|_.__/____/ \__, |\__,_|\__, |\__, |\___|
                              |___/       |___/ |___/
"""


def banner() -> None:
    console.print()
    console.print(
        Panel(
            Text(BANNER_ART, style="bold cyan", justify="center"),
            border_style="bright_cyan",
            padding=(0, 2),
            subtitle="Agentic AI · Internship & Hackathon Discovery",
            subtitle_align="center",
        )
    )
    console.print(
        Text(
            "Searches ONLY official student platforms: Internshala, Unstop, LinkedIn, Indeed,\n"
            "Wellfound, Naukri, AICTE  |  Devpost, HackerEarth, Devfolio, MLH, CodeChef, HackerRank",
            style="dim",
            justify="center",
        )
    )


def print_status(mongo: MongoService) -> None:
    from app.llm import llm_available

    llm_on = llm_available()
    tavily_on = settings.tavily_api_key not in ("", "your_tavily_api_key_here")
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()
    grid.add_row("LLM planning", "[green]ON[/]" if llm_on else "[yellow]OFF[/] [dim](rule-based mode — add GEMINI_API_KEY in .env to enable)[/]")
    grid.add_row("Web search", "[cyan]Tavily[/]" if tavily_on else "[cyan]DuckDuckGo[/] [dim](free fallback)[/]")
    grid.add_row("MongoDB", "[green]connected[/]" if mongo.available else "[yellow]not available[/] [dim](results won't be saved)[/]")
    console.print(Panel(grid, border_style="dim", title="[dim]environment[/dim]", title_align="left", padding=(0, 2)))


# ----------------------------- prompt helpers ------------------------------ #

def ask(prompt: str, default: str = "", required: bool = False) -> str:
    hint = f" [dim]\\[{default}][/]" if default else ""
    while True:
        raw = Prompt.ask(f"[bold]{prompt}[/]{hint}", default="", show_default=False).strip()
        if raw:
            return raw
        if default:
            return default
        if not required:
            return ""
        console.print("      [red]This field is required.[/red]")


def ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    while True:
        value = IntPrompt.ask(f"[bold]{prompt}[/] [dim]({lo}-{hi})[/]", default=default)
        if lo <= value <= hi:
            return value
        console.print(f"      [red]Enter a number between {lo} and {hi}.[/]")


def ask_float(prompt: str, default: float, lo: float, hi: float) -> float:
    while True:
        value = FloatPrompt.ask(f"[bold]{prompt}[/] [dim]({lo}-{hi})[/]", default=default)
        if lo <= value <= hi:
            return value
        console.print(f"      [red]Enter a number between {lo} and {hi}.[/]")


def ask_list(prompt: str, default: str) -> List[str]:
    raw = ask(prompt + " (comma-separated)", default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def ask_choice(title: str, options: List[str], default: int = 1) -> int:
    console.print(f"[bold]{title}[/]")
    for i, option in enumerate(options, start=1):
        marker = "  [dim](default)[/]" if i == default else ""
        console.print(f"   [bold cyan]{i}[/]) {escape(option)}{marker}")
    valid = [str(i) for i in range(1, len(options) + 1)]
    raw = Prompt.ask("[bold]Choose[/]", default=str(default), choices=valid, show_choices=False, show_default=False)
    return int(raw)
# --------------------------- live agent trace ------------------------------- #

def _fmt_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "0"
        if all(isinstance(v, str) for v in value):
            joined = ", ".join(value)
            if len(joined) <= 55:
                return joined
            return f"{value[0]} …(+{len(value) - 1} more)"
        return f"{len(value)} items"
    if isinstance(value, dict):
        inner = ", ".join(f"{k}={v}" for k, v in list(value.items())[:3])
        return inner[:55]
    text = str(value)
    return text if len(text) <= 55 else text[:52] + "…"


def _trace_sink(step: Dict[str, Any]) -> None:
    agent = step["agent"]
    action = escape(str(step["action"]))
    style = AGENT_STYLES.get(agent, "white")
    icon = AGENT_ICONS.get(agent, "•")
    details = step.get("details") or {}
    det = "  ".join(
        f"[dim]{escape(str(k))}=[/][dim italic]{escape(_fmt_value(v))}[/]"
        for k, v in details.items()
        if v not in (None, "", [])
    )
    console.print(f"   [{style}]{icon} {agent:<17}[/] {action}{('  ' + det) if det else ''}")


# ----------------------------- user interaction ----------------------------- #

DEMO_PROFILE: Dict[str, Any] = {
    "name": "Saravanan",
    "email": "saravanan@example.com",
    "college": "College of Engineering Guindy",
    "degree": "B.Tech",
    "department": "Information Technology",
    "year": 3,
    "cgpa": 9.54,
    "programming_languages": ["C++", "Python", "JavaScript"],
    "skills": ["Data Structures", "SQL", "Web Development"],
    "technologies": ["React", "Node.js"],
    "interests": ["AI", "Web Development", "Software Development"],
    "preferred_locations": ["Chennai", "Bangalore", "Remote"],
}


def collect_profile() -> Dict[str, Any]:
    console.print()
    console.rule("[bold cyan]STEP 1 · YOUR PROFILE")
    mode = ask_choice(
        "How do you want to set up your profile?",
        [
            "Enter my profile manually",
            "Use the demo profile (Saravanan · College of Engineering Guindy · CGPA 9.54)",
        ],
    )
    if mode == 2:
        profile = dict(DEMO_PROFILE)
        profile["user_id"] = "usr_" + uuid.uuid4().hex[:8]
        console.print(f"   [green]✔[/] Demo profile loaded: [bold]Saravanan[/] · {escape(profile['department'])} · year {profile['year']} · CGPA {profile['cgpa']}")
        return profile

    console.print("   [dim]Press Enter to accept the [default] value.[/]")
    profile: Dict[str, Any] = {"user_id": "usr_" + uuid.uuid4().hex[:8]}
    profile["name"] = ask("Name", required=True)
    profile["email"] = ask("Email")
    profile["college"] = ask("College")
    profile["degree"] = ask("Degree", "B.Tech")
    profile["department"] = ask("Department", "Information Technology")
    profile["year"] = ask_int("Academic year", 3, 1, 5)
    profile["cgpa"] = ask_float("CGPA", 8.0, 0.0, 10.0)
    profile["programming_languages"] = ask_list("Programming languages", "C++, Python, JavaScript")
    profile["skills"] = ask_list("Technical skills", "Data Structures, SQL, Web Development")
    profile["technologies"] = ask_list("Technologies / frameworks", "React, Node.js")
    profile["interests"] = ask_list("Interests (AI, Web Development, Data Science...)", "AI, Web Development")
    profile["preferred_locations"] = ask_list("Preferred locations", "Chennai, Bangalore")
    remote = ask_choice("Open to remote opportunities?", ["Yes", "No"], default=1) == 1
    if remote and "remote" not in [p.lower() for p in profile["preferred_locations"]]:
        profile["preferred_locations"].append("Remote")
    return profile


def choose_search_type() -> str:
    console.print()
    console.rule("[bold cyan]STEP 2 · WHAT SHOULD SCOUTAI FIND?")
    console.print("   [dim]ScoutAI only searches internships, hackathons and coding competitions.[/]")
    choice = ask_choice(
        "Pick what to search for:",
        [
            "Internships",
            "Hackathons & coding competitions",
            "Both internships and hackathons",
        ],
        default=3,
    )
    return {1: "internship", 2: "hackathon", 3: "both"}[choice]


def run_search(profile: Dict[str, Any], search_type: str) -> Dict[str, Any]:
    console.print()
    console.rule("[bold cyan]STEP 3 · AGENT WORKFLOW RUNNING")
    console.print("   [dim]planner → researcher (search + scrape) → eligibility → match[/]")
    console.print("   [dim]→ quality evaluation → (re-plan if insufficient) → recommender[/]")
    console.print()

    trace.reset()
    trace.set_sink(_trace_sink)
    initial_state: Dict[str, Any] = {
        "student_profile": profile,
        "search_type": search_type,
        "iteration": 1,
        "search_queries": [],
        "used_queries": [],
        "raw_search_results": [],
        "processed_urls": [],
        "scraped_opportunities": [],
        "eligible_opportunities": [],
        "ranked_opportunities": [],
        "quality": {},
        "final_output": [],
        "errors": [],
    }
    try:
        result = scout_graph.invoke(initial_state, config={"recursion_limit": 60})
    finally:
        trace.set_sink(None)
    console.print()
    console.print("   [bold green]✔ Agent workflow finished.[/]")
    return result
# ------------------------------ results display ----------------------------- #

def _score_color(percent: float) -> str:
    if percent >= 70:
        return "green"
    if percent >= 50:
        return "yellow"
    if percent >= 35:
        return "dark_orange"
    return "red"


def _bar(score: float, max_score: float, width: int = 16) -> str:
    ratio = 0.0 if not max_score else max(0.0, min(1.0, score / max_score))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


def _info_row(grid: Table, label: str, value: Any, always: bool = False, style: str = "") -> None:
    text = str(value or "").strip()
    if not text or (text == "Not specified" and not always):
        return
    if text == "Not specified":
        style = "dim"
    grid.add_row(f"{label}:", Text(escape(text), style=style) if style else Text(escape(text)))


def print_opportunity_card(index: int, opp: Dict[str, Any]) -> None:
    match = opp.get("match_score") or {}
    score = float(match.get("total", 0) or 0)
    label = match.get("label", "")
    breakdown = match.get("breakdown", {})
    status = opp.get("eligibility_status", "UNKNOWN")
    status_style = STATUS_STYLES.get(status, "dim")
    color = _score_color(score)
    type_label, type_style = TYPE_LABELS.get(opp.get("type"), (str(opp.get("type", "")).upper(), "white"))
    verified = bool(opp.get("verified"))
    title = str(opp.get("title", "Untitled opportunity"))

    # ---- info grid ----
    info = Table.grid(padding=(0, 1))
    info.add_column(style="dim", justify="right", min_width=12)
    info.add_column(ratio=1, overflow="fold")
    info.add_row("Title:", Text(escape(title), style="bold white"))
    _info_row(info, "Organizer", opp.get("organization"))
    _info_row(info, "Type", type_label, always=True, style=f"bold {type_style}")
    _info_row(info, "Location", opp.get("location"))
    _info_row(info, "Mode", opp.get("mode"))
    _info_row(info, "Duration", opp.get("duration"))
    if opp.get("type") == "internship":
        _info_row(info, "Stipend", opp.get("stipend"), always=True, style="bright_green")
    else:
        _info_row(info, "Prize", opp.get("prize"), always=True, style="bright_green")
    _info_row(info, "Deadline", opp.get("deadline"), always=True, style="bright_yellow")
    skills = ", ".join(opp.get("required_skills") or [])
    _info_row(info, "Skills wanted", skills, always=True)

    inner: List[Any] = [info]

    # ---- eligibility verdict ----
    reason = str(opp.get("eligibility_reason") or "Unable to verify")
    inner += [
        Text(""),
        Text.from_markup(
            f" Eligibility: [{status_style}]{escape(status)}[/] [dim]— {escape(reason)}[/]",
            overflow="fold",
        ),
    ]

    # ---- description ----
    desc = str(opp.get("description") or "").strip()
    if desc and desc != "Not specified":
        inner += [Text(""), Text(escape(desc[:300]) + ("…" if len(desc) > 300 else ""), style="dim italic")]

    # ---- transparent score breakdown with bars ----
    if breakdown:
        bt = Table.grid(padding=(0, 2))
        bt.add_column(min_width=10, style="bold")
        bt.add_column(width=16)
        bt.add_column(justify="right", min_width=7)
        bt.add_column(ratio=1, overflow="fold")
        for key in ("skill", "education", "year", "cgpa", "interest", "location"):
            part = breakdown.get(key)
            if not part:
                continue
            pct = 0 if not part["max"] else part["score"] / part["max"] * 100
            bt.add_row(
                COMPONENT_LABELS.get(key, key),
                Text(_bar(part["score"], part["max"]), style=_score_color(pct)),
                f"{part['score']:g}/{part['max']:g}",
                Text(escape(str(part["note"])), style="dim"),
            )
        inner += [Text(""), bt]
    # ---- explanation ----
    why = str(opp.get("fit_explanation") or "").strip()
    if why:
        inner += [Text(""), Text("Why this matches you:", style="bold bright_white"), Text(escape(why))]

    # ---- links ----
    apply_url = str(opp.get("application_url") or opp.get("source_url") or "")
    src_url = str(opp.get("source_url") or "")
    links = Table.grid(padding=(0, 1))
    links.add_column(style="dim", justify="right", min_width=12)
    links.add_column(ratio=1, overflow="fold")
    if apply_url:
        links.add_row("Apply:", Text(apply_url, style="bold link " + apply_url))
    if src_url:
        badge = "[green]✓ verified from source[/]" if verified else "[yellow]⚠ could not fully verify — treat with care[/]"
        links.add_row("Source:", Text.from_markup(f"[link {src_url}]{escape(src_url)}[/]  {badge}"))
    inner += [Text(""), links]

    console.print(
        Panel(
            Group(*inner),
            title=f"[bold {color}]#{index} · {score:.0f}% Match — {escape(label)}[/]",
            title_align="left",
            subtitle=f"{escape(str(opp.get('source_name') or ''))} · {type_label}",
            subtitle_align="right",
            border_style=color,
            padding=(0, 2),
        )
    )
def show_results(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    final_output = result.get("final_output", [])
    quality = result.get("quality") or {}

    console.print()
    console.rule("[bold cyan]RESULTS")

    if not final_output:
        console.print(
            Panel(
                "[bold yellow]No verified opportunities could be found this time.[/]\n\n"
                "[dim]Possible reasons: no internet connection, search-provider rate limits, or the\n"
                "whitelisted sites blocked automated access. Try running it again, or add a\n"
                "Tavily / Gemini API key in .env for more reliable searching.[/]",
                border_style="yellow",
                title="Nothing found",
                title_align="left",
            )
        )
        errors = result.get("errors") or []
        if errors:
            console.print(f"  [dim]Agent notes ({len(errors)}):[/]")
            for err in errors[:6]:
                console.print(f"   [dim]· {escape(err[:110])}[/]")
        return []

    console.print(
        f"  [bold green]{len(final_output)}[/] ranked opportunities  "
        f"[dim]·[/] {quality.get('verified_relevant', '?')} verified  "
        f"[dim]·[/] {quality.get('eligible', '?')} fully eligible  "
        f"[dim]·[/] {quality.get('total_found', '?')} raw candidates"
    )

    # ---- compact overview table ----
    overview = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold",
        padding=(0, 1),
        show_edge=False,
        expand=True,
    )
    overview.add_column("#", justify="right", style="bold cyan", width=3)
    overview.add_column("Opportunity", ratio=1, overflow="ellipsis", no_wrap=True)
    overview.add_column("Type", width=14)
    overview.add_column("Match", justify="right", width=6)
    overview.add_column("Eligibility", width=17)
    for i, opp in enumerate(final_output, start=1):
        score = float((opp.get("match_score") or {}).get("total", 0) or 0)
        t_label, t_style = TYPE_LABELS.get(opp.get("type"), (str(opp.get("type", "")).upper(), "white"))
        status = opp.get("eligibility_status", "UNKNOWN")
        overview.add_row(
            str(i),
            str(opp.get("title", "")),
            Text(t_label, style=t_style),
            Text(f"{score:.0f}%", style=f"bold {_score_color(score)}"),
            Text(status, style=STATUS_STYLES.get(status, "dim")),
        )
    console.print(overview)

    # ---- detailed cards ----
    for i, opp in enumerate(final_output, start=1):
        print_opportunity_card(i, opp)

    return final_output


def show_full_trace(result: Dict[str, Any]) -> None:
    steps = result.get("agent_trace") or trace.get_trace()
    console.print()
    console.rule(f"[bold cyan]FULL AGENT TRACE · {len(steps)} STEPS")
    table = Table(box=box.SIMPLE, padding=(0, 1), show_edge=False, expand=True)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Agent", width=18)
    table.add_column("Action", ratio=1, overflow="fold")
    table.add_column("Details", ratio=2, overflow="fold", style="dim")
    for i, step in enumerate(steps, start=1):
        agent = step["agent"]
        details = step.get("details") or {}
        det = "  ".join(f"{k}={_fmt_value(v)}" for k, v in details.items() if v not in (None, "", []))
        table.add_row(
            str(i),
            Text(f"{AGENT_ICONS.get(agent, '•')} {agent}", style=AGENT_STYLES.get(agent, "white")),
            escape(str(step["action"])),
            escape(det),
        )
    console.print(table)
# ------------------------------ persistence flows --------------------------- #

def persist_run(mongo: MongoService, profile: Dict[str, Any], search_type: str, result: Dict[str, Any]) -> None:
    if not mongo.available:
        console.print("   [dim]MongoDB not reachable — results not saved (app continues normally).[/]")
        return
    search_id = "srch_" + uuid.uuid4().hex[:8]
    final_output = result.get("final_output", [])
    try:
        mongo.save_profile(profile)
        mongo.save_opportunities(result.get("scraped_opportunities", []), profile["user_id"])
        strong = sum(1 for o in final_output if (o.get("match_score") or {}).get("total", 0) >= 70)
        mongo.save_search_history(
            user_id=profile["user_id"],
            search_id=search_id,
            query=f"{search_type} opportunities for {profile.get('name', 'student')}",
            filters={"search_type": search_type, "min_results": settings.min_results},
            opportunities_found=len(final_output),
            strong_matches=strong,
        )
        mongo.save_agent_trace(search_id, profile["user_id"], result.get("agent_trace", []))
        console.print(
            f"   [green]✔[/] Saved to MongoDB ([dim]{escape(settings.mongodb_db_name)}[/]): profile, "
            f"{len(result.get('scraped_opportunities', []))} opportunities, search history, agent trace "
            f"[dim]({search_id})[/]"
        )
    except Exception as e:
        console.print(f"   [yellow]MongoDB save failed: {escape(str(e))}[/]")


def save_bookmarks(mongo: MongoService, profile: Dict[str, Any], final_output: List[Dict[str, Any]]) -> None:
    if not mongo.available:
        console.print("   [yellow]MongoDB is not reachable, so opportunities cannot be bookmarked.[/]")
        return
    raw = ask("Enter result numbers to save (e.g. 1,3) — Enter to skip")
    if not raw:
        return
    chosen: List[Dict[str, Any]] = []
    for token in raw.replace(" ", "").split(","):
        if token.isdigit() and 1 <= int(token) <= len(final_output):
            chosen.append(final_output[int(token) - 1])
    if not chosen:
        console.print("   [yellow]No valid numbers entered.[/]")
        return
    count = mongo.save_saved_opportunities(profile["user_id"], chosen)
    console.print(f"   [green]✔[/] Bookmarked {count} opportunities (application status: [bold]Saved[/]).")
def manage_saved(mongo: MongoService, profile: Dict[str, Any]) -> None:
    if not mongo.available:
        console.print("   [yellow]MongoDB is not reachable.[/]")
        return
    saved = mongo.get_saved(profile["user_id"])
    if not saved:
        console.print("   [dim]No bookmarked opportunities yet — save some from the results first.[/]")
        return
    console.print()
    console.rule("[bold cyan]YOUR SAVED OPPORTUNITIES")
    table = Table(box=box.SIMPLE_HEAVY, padding=(0, 1), show_edge=False, expand=True, header_style="bold")
    table.add_column("#", justify="right", style="bold cyan", width=3)
    table.add_column("Opportunity", ratio=1, overflow="ellipsis", no_wrap=True)
    table.add_column("Status", width=12)
    table.add_column("Source", ratio=1, overflow="ellipsis", style="dim", no_wrap=True)
    for i, doc in enumerate(saved, start=1):
        table.add_row(str(i), str(doc.get("opportunity_title", "?")), str(doc.get("application_status", "Saved")), str(doc.get("source_url", "")))
    console.print(table)
    raw = ask("Enter a number to update its status — Enter to skip")
    if not raw or not raw.isdigit() or not (1 <= int(raw) <= len(saved)):
        return
    doc = saved[int(raw) - 1]
    idx = ask_choice("New application status", list(APPLICATION_STATUSES), default=1)
    if mongo.update_application_status(profile["user_id"], doc.get("source_url"), APPLICATION_STATUSES[idx - 1]):
        console.print(f"   [green]✔[/] Status updated to [bold]{APPLICATION_STATUSES[idx - 1]}[/].")
    else:
        console.print("   [yellow]Could not update status.[/]")


# ----------------------------------- main ----------------------------------- #

def main() -> None:
    banner()
    mongo = MongoService()
    mongo.connect()
    print_status(mongo)

    while True:
        try:
            profile = collect_profile()
            search_type = choose_search_type()
            result = run_search(profile, search_type)
            final_output = show_results(result)
            persist_run(mongo, profile, search_type, result)

            while True:
                console.print()
                choice = ask_choice(
                    "What next?",
                    [
                        "Show the full agent trace",
                        "Bookmark opportunities (saved list)",
                        "View saved list / update application status",
                        "New search",
                        "Exit ScoutAI",
                    ],
                    default=5,
                )
                if choice == 1:
                    show_full_trace(result)
                elif choice == 2 and final_output:
                    save_bookmarks(mongo, profile, final_output)
                elif choice == 2:
                    console.print("   [yellow]Nothing to bookmark — no results.[/]")
                elif choice == 3:
                    manage_saved(mongo, profile)
                elif choice == 4:
                    break
                else:
                    console.print()
                    console.print(
                        Panel(
                            Text("Good luck with your applications! 🚀", justify="center", style="bold bright_cyan"),
                            border_style="bright_cyan",
                            padding=(0, 4),
                        )
                    )
                    mongo.close()
                    return
        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print("   [cyan]Interrupted — goodbye! 👋[/]")
            mongo.close()
            return
        except Exception as e:  # never crash the loop silently
            console.print(f"\n   [bold red]Unexpected error:[/] {escape(str(e))}")
            console.print("   [dim]Please try again (traceback below for debugging).[/]")
            import traceback

            console.print_exception()


if __name__ == "__main__":
    main()






