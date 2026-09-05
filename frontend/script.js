// NOTE: Backend URL is hardcoded to http://localhost:8000/discover. Update for deployment.
const BACKEND_URL = "http://localhost:8000/discover";

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

    // 1. Reset UI States
    validationError.classList.add("hidden");
    errorState.classList.add("hidden");
    resultsSection.classList.add("hidden");
    emptyState.classList.add("hidden");
    resultsContainer.innerHTML = "";

    // 2. Read and Validate Inputs
    const name = document.getElementById("name").value.trim();
    const degree = document.getElementById("degree").value.trim() || "B.Tech";
    const department = document.getElementById("department").value.trim() || "Computer Science";
    const year = parseInt(document.getElementById("year").value, 10);
    const cgpaRaw = document.getElementById("cgpa").value.trim();
    const cgpa = parseFloat(cgpaRaw);
    const skillsRaw = document.getElementById("skills").value.trim();
    const interestsRaw = document.getElementById("interests").value.trim();
    const location = document.getElementById("location").value.trim() || "Remote";

    if (!name || !skillsRaw || isNaN(cgpa) || cgpa < 0 || cgpa > 10) {
      validationError.textContent = "Please fill in Name, valid CGPA (0.0 to 10.0), and at least one Skill.";
      validationError.classList.remove("hidden");
      return;
    }

    const skills = skillsRaw.split(",").map((s) => s.trim()).filter(Boolean);
    const interests = interestsRaw ? interestsRaw.split(",").map((i) => i.trim()).filter(Boolean) : [];

    const studentProfile = {
      user_id: "usr_" + Math.random().toString(36).substring(2, 9),
      name: name,
      degree: degree,
      department: department,
      year: year,
      cgpa: cgpa,
      skills: skills,
      interests: interests,
      location: location,
    };

    // 3. Show Loading State
    loadingState.classList.remove("hidden");
    submitBtn.disabled = true;
    submitBtn.querySelector("span").textContent = "Searching...";

    try {
      // 4. Send Request to FastAPI Backend
      const response = await fetch(BACKEND_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(studentProfile),
      });

      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      console.log("[ScoutAI Debug] Raw backend response:", data);
      const opportunities = data.results || [];

      // 5. Render Results
      if (opportunities.length === 0) {
        emptyState.classList.remove("hidden");
      } else {
        resultsCount.textContent = `${opportunities.length} found`;
        renderOpportunities(opportunities, resultsContainer);
        resultsSection.classList.remove("hidden");
      }
    } catch (err) {
      // 6. Error Handling
      errorMessage.textContent = `Couldn't reach ScoutAI backend — make sure the server is running at ${BACKEND_URL}. Details: ${err.message}`;
      errorState.classList.remove("hidden");
    } finally {
      loadingState.classList.add("hidden");
      submitBtn.disabled = false;
      submitBtn.querySelector("span").textContent = "Find Opportunities";
    }
  });

  function renderOpportunities(items, container) {
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "opportunity-card";

      const totalScore = item.match_score?.total_score ?? 0;
      let scoreBadgeClass = "score-low";
      if (totalScore >= 90) scoreBadgeClass = "score-high";
      else if (totalScore >= 70) scoreBadgeClass = "score-medium";

      const typeClass = item.type === "competition" ? "type-competition" : "type-internship";
      const appUrl = item.application_url || item.source_url || "#";

      card.innerHTML = `
        <div class="card-top">
          <div class="opp-title-group">
            <h3>${escapeHtml(item.title || "Opportunity")}</h3>
            <span class="organization">${escapeHtml(item.organization || "Independent")}</span>
          </div>
          <div class="badges">
            <span class="badge ${typeClass}">${escapeHtml(item.type || "Opportunity")}</span>
            <span class="badge ${scoreBadgeClass}">${totalScore}% Match</span>
          </div>
        </div>

        <div class="opp-details">
          <span class="detail-item">📍 ${escapeHtml(item.location || "Remote")}</span>
          ${item.stipend_or_prize ? `<span class="detail-item">💰 ${escapeHtml(item.stipend_or_prize)}</span>` : ""}
          ${item.deadline ? `<span class="detail-item">⏳ Deadline: ${escapeHtml(item.deadline)}</span>` : ""}
        </div>

        <div class="explanation-box">
          <strong>Why it fits:</strong> ${escapeHtml(item.fit_explanation || "Strong skill and profile alignment.")}
        </div>

        <div class="card-actions">
          <a href="${escapeHtml(appUrl)}" target="_blank" rel="noopener noreferrer" class="btn-apply">
            Apply Now ↗
          </a>
        </div>
      `;

      container.appendChild(card);
    });
  }

  function escapeHtml(str) {
    if (typeof str !== "string") return str;
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
