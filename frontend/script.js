// ScoutAI frontend — mirrors the terminal UI experience.
// Streams /discover events and renders trace + opportunity cards like the terminal.

const BACKEND_URL = "http://localhost:8000/discover";
const STATE = { opportunities: [], traceSteps: [], done: false, user_id: null };

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("profile-form");
  const submitBtn = document.getElementById("submit-btn");
  const validationError = document.getElementById("validation-error");
  const loadingState = document.getElementById("loading-state");
  const errorState = document.getElementById("error-state");
  const errorMessage = document.getElementById("error-message");
  const resultsSection = document.getElementById("results-section");
  const resultsContainer = document.getElementById("results-container");
  const resultsCount = document.getElementById("results-count");
  const emptyState = document.getElementById("empty-state");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    validationError.classList.add("hidden");
    errorState.classList.add("hidden");
    resultsSection.classList.add("hidden");
    emptyState.classList.add("hidden");
    resultsContainer.innerHTML = "";
    STATE.opportunities = [];
    STATE.traceSteps = [];
    STATE.done = false;

    const name = document.getElementById("name").value.trim();
    const degree = document.getElementById("degree").value.trim() || "B.Tech";
    const department = document.getElementById("department").value.trim() || "Computer Science";
    const year = parseInt(document.getElementById("year").value, 10);
    const cgpa = parseFloat(document.getElementById("cgpa").value.trim());
    const skillsRaw = document.getElementById("skills").value.trim();
    const interestsRaw = document.getElementById("interests").value.trim();
    const location = document.getElementById("location").value.trim() || "Remote";

    if (!name || !skillsRaw || isNaN(cgpa) || cgpa < 0 || cgpa > 10) {
      validationError.textContent = "Please fill in Name, valid CGPA (0.0 to 10.0), and at least one Skill.";
      validationError.classList.remove("hidden");
      return;
    }
    const skills = skillsRaw.split(",").map(s => s.trim()).filter(Boolean);
    const interests = interestsRaw ? interestsRaw.split(",").map(i => i.trim()).filter(Boolean) : [];
    const searchType = (document.getElementById("opptype") || {}).value || "both";
    const studentProfile = {
      user_id: "usr_" + Math.random().toString(36).substring(2, 9),
      name, degree, department, year, cgpa, skills, interests, location,
      search_type: searchType,
    };

    loadingState.classList.remove("hidden");
    submitBtn.disabled = true;
    submitBtn.querySelector("span").textContent = "Searching...";

    try {
      const response = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(studentProfile),
      });
      if (!response.ok) {
        throw new Error("HTTP " + response.status + ": " + response.statusText);
      }

      // Stream the agentic workflow: trace steps + opportunities as they happen
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const raw of events) {
          const line = raw.trim();
          if (!line || !line.startsWith("data:")) continue;
          const payload = line.split("\n")
            .filter(l => l.startsWith("data:"))
            .map(l => l.slice(5)).join("\n").trim();
          if (!payload) continue;
          let event;
          try { event = JSON.parse(payload); } catch { continue; }

          if (event.type === "trace") {
            STATE.traceSteps.push(event.step);
            renderTraceStep(event.step);
          } else if (event.type === "opportunity") {
            STATE.opportunities.push(event.item);
            renderOpportunityCard(event.item, resultsContainer);
            resultsCount.textContent = STATE.opportunities.length + " found";
            resultsSection.classList.remove("hidden");
          } else if (event.type === "error") {
            throw new Error(event.message || "Workflow failed");
          } else if (event.type === "done") {
            STATE.done = true;
            loadingState.classList.add("hidden");
            if (STATE.opportunities.length === 0) emptyState.classList.remove("hidden");
          }
        }
      }
    } catch (err) {
      errorMessage.textContent = "Couldn't reach ScoutAI backend at " + BACKEND_URL + " — " + err.message;
      errorState.classList.remove("hidden");
    } finally {
      loadingState.classList.add("hidden");
      submitBtn.disabled = false;
      submitBtn.querySelector("span").textContent = "Find Opportunities";
    }
  });
});

function escapeHtml(str) {
  if (typeof str !== "string") return str;
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
// ── Live agent trace panel ──────────────────────────────
function renderTraceStep(step) {
  const content = getOrCreateTracePanel();
  const entry = document.createElement("div");
  entry.className = "trace-entry";
  entry.innerHTML =
    '<span class="agent-tag agent-' + escapeHtml(step.agent) + '">' + escapeHtml(step.agent) + "</span>" +
    '<span class="trace-action">' + escapeHtml(step.action) + "</span>" +
    '<span class="trace-time">' + new Date(step.timestamp).toLocaleTimeString() + "</span>";
  if (step.details && Object.keys(step.details).length) {
    const d = document.createElement("div");
    d.className = "trace-details";
    d.textContent = JSON.stringify(step.details).substring(0, 250);
    entry.appendChild(d);
  }
  content.appendChild(entry);
  content.scrollTop = content.scrollHeight;
}

function getOrCreateTracePanel() {
  let panel = document.getElementById("trace-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "trace-panel";
    panel.className = "trace-panel";
    const header = document.createElement("div");
    header.className = "trace-panel-header";
    header.innerHTML = '<span>🔍 Live Agent Trace</span><span class="trace-toggle">−</span>';
    header.addEventListener("click", () => {
      const t = panel.querySelector(".trace-toggle");
      if (panel.classList.toggle("collapsed")) t.textContent = "+"; else t.textContent = "−";
    });
    const content = document.createElement("div");
    content.className = "trace-content";
    panel.append(header, content);
    document.querySelector(".main-content").insertBefore(panel, document.querySelector(".form-card"));
  }
  return panel.querySelector(".trace-content");
}
// ── Opportunity card (mirrors terminal layout) ───────────
function renderOpportunityCard(item, container) {
  const total = (item.match_score && item.match_score.total) || 0;
  const cls = total >= 70 ? "score-high" : total >= 50 ? "score-medium" : total >= 35 ? "score-low-35" : "score-low";
  const typeCls = (item.type === "hackathon" || item.type === "competition" || item.type === "coding_competition") ? "type-competition" : "type-internship";
  const appUrl = item.application_url || item.source_url || "#";

  const card = document.createElement("article");
  card.className = "opportunity-card";

  let h = '<div class="card-header"><div class="header-left">';
  h += '<h3 class="opp-title">' + escapeHtml(item.title || "Opportunity") + "</h3>";
  h += '<span class="organization">' + escapeHtml(item.organization || "Organization not specified") + "</span>";
  h += '</div><div class="badges">';
  h += '<span class="badge ' + typeCls + '">' + escapeHtml(item.type || "opportunity") + "</span>";
  h += '<span class="badge ' + cls + '">' + total + "% Match</span></div></div>";

  h += '<div class="opp-details-grid">';
  h += '<span class="detail-item">📍 <strong>' + escapeHtml(item.location || "Not specified") + "</strong></span>";
  h += '<span class="detail-item">🖥️ <strong>Mode:</strong> ' + escapeHtml(item.mode || "Not specified") + "</span>";
  h += '<span class="detail-item">⏱️ <strong>Duration:</strong> ' + escapeHtml(item.duration || "Not specified") + "</span>";
  if (item.prize || item.stipend) {
    h += '<span class="detail-item">💰 <strong>' + (item.prize ? "Prize" : "Stipend") + ":</strong> " + escapeHtml(item.prize || item.stipend) + "</span>";
  }
  if (item.deadline) {
    h += '<span class="detail-item">⏳ <strong>Deadline:</strong> ' + escapeHtml(item.deadline) + "</span>";
  }
  h += '<span class="detail-item">✅ <em>' + (item.verified ? "verified" : "Unable to verify") + "</em></span>";
  h += "</div>";

  if (Array.isArray(item.required_skills) && item.required_skills.length) {
    h += '<div class="skills-section"><strong>Required Skills:</strong><div class="skills-list">';
    item.required_skills.forEach(s => { h += '<span class="skill-tag">' + escapeHtml(s) + "</span>"; });
    h += "</div></div>";
  }

  const bd = (item.match_score && item.match_score.breakdown) || {};
  const comps = [
    ["skill", "Skill", 40, "#22c55e"], ["education", "Education", 20, "#3b82f6"],
    ["year", "Year", 15, "#8b5cf6"], ["cgpa", "CGPA", 10, "#f59e0b"],
    ["interest", "Interest", 10, "#ef4444"], ["location", "Location", 5, "#06b6d4"],
  ];
  h += '<div class="score-section"><h4>Match Score Breakdown</h4><div class="score-bars">';
  comps.forEach(c => {
    const part = (bd[c[0]] && typeof bd[c[0]] === "object") ? bd[c[0]] : { score: 0, max: c[2], note: "" };
    const v = part.score || 0;
    const max = part.max || c[2];
    const pct = max > 0 ? Math.min((v / max) * 100, 100) : 0;
    const note = part.note || "";
    h += '<div class="score-row"><span class="score-label">' + c[1] + "</span>";
    h += '<div class="score-bar-container"><div class="score-bar-fill" style="width:' + pct + "%;background:" + c[3] + ';"></div></div>';
    h += '<span class="score-value">' + v + "/" + max + "</span>";
    if (note) h += '<span class="score-note">' + escapeHtml(note) + "</span>";
    h += "</div>";
  });
  h += "</div></div>";

  h += '<div class="explanation-section"><h4>Why this matches you</h4>';
  h += '<p class="fit-explanation">' + escapeHtml(item.fit_explanation || "Matches your profile based on skills and preferences.") + "</p></div>";

  const st = (item.eligibility_status || "UNKNOWN").toLowerCase().replace(/\s+/g, "_");
  const bmap = {
    eligible: '<span class="eligibility-badge eligible">ELIGIBLE</span>',
    possibly_eligible: '<span class="eligibility-badge possibly">POSSIBLY ELIGIBLE</span>',
    not_eligible: '<span class="eligibility-badge not-eligible">NOT ELIGIBLE</span>',
    unknown: '<span class="eligibility-badge unknown">UNKNOWN</span>',
  };
  h += '<div class="eligibility-section"><h4>Eligibility: ' + (bmap[st] || bmap.unknown) + "</h4>";
  h += '<p class="eligibility-reason">' + escapeHtml(item.eligibility_reason || "Unable to verify") + "</p></div>";

  h += '<div class="description-section"><h4>Description</h4>';
  h += '<p class="description-text">' + escapeHtml(item.description || "No description available.") + "</p></div>";

  h += '<div class="card-actions">';
  h += '<a href="' + escapeHtml(appUrl) + '" target="_blank" rel="noopener" class="btn-apply">Apply Now ↗</a>';
  if (item.source_url) {
    h += '<a href="' + escapeHtml(item.source_url) + '" target="_blank" rel="noopener" class="btn-source">Source ↗</a>';
  }
  h += "</div>";

  card.innerHTML = h;
  container.appendChild(card);
}