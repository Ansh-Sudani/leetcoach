const searchInput = document.getElementById("problem-search");
const optionsList = document.getElementById("problem-options");
const selectedProblemEl = document.getElementById("selected-problem");
const selectedNumEl = document.getElementById("selected-problem-num");
const selectedTitleEl = document.getElementById("selected-problem-title");
const selectedDifficultyEl = document.getElementById("selected-problem-difficulty");
const solveBtn = document.getElementById("mark-solved-btn");
const detailsInput = document.getElementById("problem-details");
const hintLevelSelect = document.getElementById("hint-level");
const hintBtn = document.getElementById("hint-btn");
const hintFeed = document.getElementById("hint-feed");
const codeInput = document.getElementById("code-input");

let allProblems = [];
let activeIndex = -1;
let current = null; // { id (leetcode number), title, difficulty, trackedId, solved }

function difficultyClass(difficulty) {
  return (difficulty || "").toLowerCase();
}

function draftKey(problemId) {
  return `leetcoach_draft_${problemId}`;
}

async function loadProblems() {
  const res = await fetch("/static/problems.json");
  allProblems = await res.json();
}

function renderOptions(matches) {
  optionsList.innerHTML = "";

  if (matches.length === 0) {
    optionsList.innerHTML = `<li class="combobox-empty">No problems match.</li>`;
    optionsList.hidden = false;
    return;
  }

  matches.slice(0, 40).forEach((p, i) => {
    const li = document.createElement("li");
    li.className = "combobox-option" + (i === activeIndex ? " active" : "");
    li.dataset.id = p.id;
    li.innerHTML = `<span class="opt-num">#${p.id}</span><span class="opt-title">${p.title}</span><span class="badge ${difficultyClass(p.difficulty)}">${p.difficulty}</span>`;
    li.addEventListener("mousedown", (e) => {
      e.preventDefault();
      selectProblem(p);
    });
    optionsList.appendChild(li);
  });

  optionsList.hidden = false;
}

function filterProblems(query) {
  const q = query.trim().toLowerCase();
  if (!q) return allProblems;
  return allProblems.filter(
    (p) => String(p.id).includes(q) || p.title.toLowerCase().includes(q)
  );
}

searchInput.addEventListener("input", () => {
  activeIndex = -1;
  renderOptions(filterProblems(searchInput.value));
});

searchInput.addEventListener("focus", () => {
  renderOptions(filterProblems(searchInput.value));
});

searchInput.addEventListener("keydown", (e) => {
  const items = optionsList.querySelectorAll(".combobox-option");
  if (e.key === "ArrowDown") {
    e.preventDefault();
    activeIndex = Math.min(activeIndex + 1, items.length - 1);
    renderOptions(filterProblems(searchInput.value));
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    activeIndex = Math.max(activeIndex - 1, 0);
    renderOptions(filterProblems(searchInput.value));
  } else if (e.key === "Enter") {
    e.preventDefault();
    const match = filterProblems(searchInput.value)[activeIndex] || filterProblems(searchInput.value)[0];
    if (match) selectProblem(match);
  } else if (e.key === "Escape") {
    optionsList.hidden = true;
  }
});

document.addEventListener("click", (e) => {
  if (!document.getElementById("problem-combobox").contains(e.target)) {
    optionsList.hidden = true;
  }
});

async function findOrCreateTracked(title, difficulty) {
  const res = await fetch("/api/problems");
  const tracked = await res.json();
  const existing = tracked.find((t) => t.title === title);
  if (existing) return existing;

  const createRes = await fetch("/api/problems", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, difficulty }),
  });
  const created = await createRes.json();
  return { id: created.id, title, difficulty, status: "in_progress" };
}

async function selectProblem(p) {
  searchInput.value = "";
  optionsList.hidden = true;

  selectedNumEl.textContent = `#${p.id}`;
  selectedTitleEl.textContent = p.title;
  selectedDifficultyEl.textContent = p.difficulty;
  selectedDifficultyEl.className = `badge ${difficultyClass(p.difficulty)}`;
  selectedProblemEl.hidden = false;

  codeInput.value = localStorage.getItem(draftKey(p.id)) || "";
  hintBtn.disabled = false;

  const tracked = await findOrCreateTracked(p.title, p.difficulty);
  const solved = tracked.status === "solved";

  current = { id: p.id, title: p.title, difficulty: p.difficulty, trackedId: tracked.id, solved };
  updateSolveButton();
}

function updateSolveButton() {
  solveBtn.hidden = false;
  if (current.solved) {
    solveBtn.textContent = "Solved ✓";
    solveBtn.classList.add("solved");
  } else {
    solveBtn.textContent = "Mark Solved";
    solveBtn.classList.remove("solved");
  }
}

solveBtn.addEventListener("click", async () => {
  if (!current || current.solved) return;
  await fetch(`/api/problems/${current.trackedId}/solve`, { method: "POST" });
  current.solved = true;
  updateSolveButton();
});

codeInput.addEventListener("input", () => {
  if (current) localStorage.setItem(draftKey(current.id), codeInput.value);
});

codeInput.addEventListener("keydown", (e) => {
  if (e.key === "Tab") {
    e.preventDefault();
    const start = codeInput.selectionStart;
    const end = codeInput.selectionEnd;
    codeInput.value = codeInput.value.slice(0, start) + "    " + codeInput.value.slice(end);
    codeInput.selectionStart = codeInput.selectionEnd = start + 4;
  }
});

function clearEmptyFeedNotice() {
  const empty = hintFeed.querySelector(".hint-feed-empty");
  if (empty) empty.remove();
}

function appendHintCard({ level, text, isError }) {
  clearEmptyFeedNotice();
  const card = document.createElement("div");
  card.className = "hint-card" + (isError ? " error" : "");
  card.innerHTML = `
    <div class="hint-card-meta"><span>${isError ? "Error" : "Hint level " + level}</span></div>
    <p></p>
  `;
  card.querySelector("p").textContent = text;
  hintFeed.appendChild(card);
  hintFeed.scrollTop = hintFeed.scrollHeight;
}

async function getHint() {
  if (!current) return;

  const problemText = detailsInput.value.trim()
    ? detailsInput.value.trim()
    : `LeetCode #${current.id}: ${current.title} (${current.difficulty})`;
  const code = codeInput.value;
  const hintLevel = hintLevelSelect.value;

  hintBtn.disabled = true;
  hintBtn.textContent = "Thinking...";

  try {
    const res = await fetch("/api/hint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem: problemText, code, hint_level: hintLevel }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    appendHintCard({ level: data.hint_level, text: data.hint });

    if (current.trackedId) {
      fetch(`/api/problems/${current.trackedId}/hint_used`, { method: "POST" }).catch(() => {});
    }
  } catch (err) {
    appendHintCard({ text: "Couldn't get a hint: " + err.message, isError: true });
  } finally {
    hintBtn.disabled = false;
    hintBtn.textContent = "Get Hint";
  }
}

hintBtn.addEventListener("click", getHint);

loadProblems();
