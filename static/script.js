const searchInput = document.getElementById("problem-search");
const optionsList = document.getElementById("problem-options");
const selectedProblemEl = document.getElementById("selected-problem");
const selectedNumEl = document.getElementById("selected-problem-num");
const selectedTitleEl = document.getElementById("selected-problem-title");
const selectedDifficultyEl = document.getElementById("selected-problem-difficulty");
const solveBtn = document.getElementById("mark-solved-btn");
const problemStatementEl = document.getElementById("problem-statement");
const problemStatementTextEl = document.getElementById("problem-statement-text");
const problemExamplesEl = document.getElementById("problem-examples");
const detailsInput = document.getElementById("problem-details-input");
const languageSelect = document.getElementById("language-select");
const languageNote = document.getElementById("language-note");
const hintProgressEl = document.getElementById("hint-progress");
const hintBtn = document.getElementById("hint-btn");
const resetHintsBtn = document.getElementById("reset-hints-btn");
const submitBtn = document.getElementById("submit-btn");
const hintFeed = document.getElementById("hint-feed");
const codeInput = document.getElementById("code-input");

const LANGUAGE_PLACEHOLDERS = {
  python: "def solve():\n    # start writing your draft here\n    pass",
  javascript: "function solve() {\n  // start writing your draft here\n}",
  java: "class Solution {\n    // start writing your draft here\n}",
  cpp: "class Solution {\npublic:\n    // start writing your draft here\n};",
};

const CM_MODES = {
  python: "python",
  javascript: "javascript",
  java: "text/x-java",
  cpp: "text/x-c++src",
};

const editor = CodeMirror.fromTextArea(codeInput, {
  mode: CM_MODES.python,
  theme: "material-darker",
  lineNumbers: true,
  indentUnit: 4,
  tabSize: 4,
  indentWithTabs: false,
  smartIndent: false,
  extraKeys: {
    Tab: (cm) => cm.replaceSelection("    "),
    Enter: (cm) => cm.replaceSelection("\n"),
  },
  placeholder: LANGUAGE_PLACEHOLDERS.python,
});

let allProblems = [];
let problemDetails = {};
let activeIndex = -1;
let current = null; // { id, title, difficulty, trackedId, solved, details, hintsUsed }

const MAX_HINTS = 4;
const HINT_LABELS = {
  1: "Nudge",
  2: "Name the approach",
  3: "Apply it here",
  4: "Outline the steps",
};

function difficultyClass(difficulty) {
  return (difficulty || "").toLowerCase();
}

function draftKey(problemId, language) {
  return `leetcoach_draft_${problemId}_${language}`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderInline(str) {
  return escapeHtml(str)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

async function loadProblems() {
  const [problemsRes, detailsRes] = await Promise.all([
    fetch("/static/problems.json"),
    fetch("/static/problem_details.json"),
  ]);
  allProblems = await problemsRes.json();
  problemDetails = await detailsRes.json();
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
  return createRes.json();
}

function renderProblemStatement(details) {
  if (!details) {
    problemStatementEl.hidden = true;
    return;
  }
  problemStatementTextEl.innerHTML = renderInline(details.description);
  problemExamplesEl.innerHTML = "";
  (details.examples || []).forEach((ex, i) => {
    const div = document.createElement("div");
    div.className = "problem-example";
    div.innerHTML = `<span class="ex-label">Example ${i + 1}</span><code>${escapeHtml(ex.input)}</code> → <code>${escapeHtml(ex.output)}</code>${ex.explanation ? `<br><span style="color:var(--muted)">${renderInline(ex.explanation)}</span>` : ""}`;
    problemExamplesEl.appendChild(div);
  });
  problemStatementEl.hidden = false;
}

function loadDraftForCurrent() {
  const lang = languageSelect.value;
  editor.setOption("mode", CM_MODES[lang] || "python");
  editor.setOption("placeholder", LANGUAGE_PLACEHOLDERS[lang] || "");

  const saved = localStorage.getItem(draftKey(current.id, lang));
  if (saved !== null) {
    editor.setValue(saved);
  } else if (lang === "python" && current.details) {
    editor.setValue(current.details.starterCode);
  } else {
    editor.setValue("");
  }
}

function updateSubmitAvailability() {
  const langOk = languageSelect.value === "python";
  submitBtn.disabled = !current;
  languageNote.hidden = langOk;
}

async function selectProblem(p) {
  searchInput.value = "";
  optionsList.hidden = true;

  selectedNumEl.textContent = `#${p.id}`;
  selectedTitleEl.textContent = p.title;
  selectedDifficultyEl.textContent = p.difficulty;
  selectedDifficultyEl.className = `badge ${difficultyClass(p.difficulty)}`;
  selectedProblemEl.hidden = false;

  const details = problemDetails[String(p.id)] || null;
  renderProblemStatement(details);

  hintBtn.disabled = true;
  resetFeed();

  const tracked = await findOrCreateTracked(p.title, p.difficulty);
  const full = await (await fetch(`/api/problems/${tracked.id}`)).json();
  const solved = full.status === "solved";

  current = {
    id: p.id,
    title: p.title,
    difficulty: p.difficulty,
    trackedId: tracked.id,
    solved,
    details,
    hintsUsed: (full.hints || []).length,
  };
  if (!details && full.statement) detailsInput.value = full.statement;
  (full.hints || []).forEach((text, i) => appendHintCard({ level: i + 1, text }));
  loadDraftForCurrent();
  updateSubmitAvailability();
  updateSolveButton();
  updateHintButton();
}

function resetFeed() {
  hintFeed.innerHTML =
    '<p class="hint-feed-empty">Write some code, then unlock hints one at a time or hit Submit to run it against test cases.</p>';
  detailsInput.value = "";
}

function updateHintButton() {
  if (!current) return;
  const next = current.hintsUsed + 1;
  hintProgressEl.hidden = false;
  hintProgressEl.textContent = `${current.hintsUsed}/${MAX_HINTS} hints used`;
  if (next > MAX_HINTS) {
    hintBtn.disabled = true;
    hintBtn.textContent = "All hints used";
    resetHintsBtn.hidden = false;
  } else {
    hintBtn.disabled = false;
    hintBtn.textContent = `Hint ${next}: ${HINT_LABELS[next]}`;
    resetHintsBtn.hidden = true;
  }
}

async function resetHints() {
  if (!current) return;
  const problem = current;
  resetHintsBtn.disabled = true;
  try {
    await fetch(`/api/problems/${problem.trackedId}/hints/reset`, { method: "POST" });
    if (problem === current) {
      current.hintsUsed = 0;
      hintFeed.querySelectorAll(".hint-card").forEach((card) => card.remove());
      if (!hintFeed.querySelector(".hint-card, .submit-card")) resetFeed();
      updateHintButton();
    }
  } finally {
    resetHintsBtn.disabled = false;
  }
}

resetHintsBtn.addEventListener("click", resetHints);

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

languageSelect.addEventListener("change", () => {
  if (current) {
    loadDraftForCurrent();
  } else {
    editor.setOption("mode", CM_MODES[languageSelect.value] || "python");
    editor.setOption("placeholder", LANGUAGE_PLACEHOLDERS[languageSelect.value] || "");
  }
  updateSubmitAvailability();
});

editor.on("change", () => {
  if (current) localStorage.setItem(draftKey(current.id, languageSelect.value), editor.getValue());
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
    <div class="hint-card-meta"><span>${isError ? "Error" : `Hint ${level} · ${HINT_LABELS[level] || ""}`}</span></div>
    <p></p>
  `;
  card.querySelector("p").innerHTML = renderInline(text);
  hintFeed.appendChild(card);
  hintFeed.scrollTop = hintFeed.scrollHeight;
}

async function getHint() {
  if (!current || current.hintsUsed >= MAX_HINTS) return;

  const statement = detailsInput.value.trim()
    ? detailsInput.value.trim()
    : current.details
    ? `LeetCode-style #${current.id}: ${current.title} (${current.difficulty})\n${current.details.description}`
    : `LeetCode #${current.id}: ${current.title} (${current.difficulty})`;
  const code = editor.getValue();
  const level = current.hintsUsed + 1;
  const problem = current;

  hintBtn.disabled = true;
  hintBtn.textContent = "Thinking...";

  try {
    const res = await fetch(`/api/problems/${problem.trackedId}/hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ statement, code, level }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    problem.hintsUsed = data.hints_used;
    if (problem === current) appendHintCard({ level: data.level, text: data.hint });
  } catch (err) {
    if (problem === current) appendHintCard({ text: "Couldn't get a hint: " + err.message, isError: true });
  } finally {
    if (problem === current) updateHintButton();
  }
}

function formatArgs(args, params) {
  return args
    .map((a, i) => `${(params && params[i]) || "arg" + i}=${JSON.stringify(a)}`)
    .join(", ");
}

const DIAGNOSIS_LABELS = {
  bug: "Bug",
  edge_case: "Edge case",
  approach: "Try this",
};

function diagnosisToText(diagnosis) {
  const noteLines = (diagnosis.notes || []).map(
    (n) => `${DIAGNOSIS_LABELS[n.type] || "Note"}: ${n.text}`
  );
  return `Likely cause: ${diagnosis.root_cause}\n${noteLines.join("\n")}`;
}

function buildSubmitContext(problemTitle, code, data) {
  const lines = data.results.map(
    (r) => `${r.passed ? "PASS" : "FAIL"} expected=${JSON.stringify(r.expected)} actual=${JSON.stringify(r.actual)}${r.error ? " error=" + r.error : ""}`
  );
  return `Problem: ${problemTitle}\n\nCode:\n${code}\n\nTest results:\n${lines.join("\n")}\n\nMy diagnosis to you:\n${diagnosisToText(data.diagnosis)}`;
}

function appendFollowupMessage(container, role, text) {
  const msg = document.createElement("div");
  msg.className = `followup-msg ${role}`;
  msg.innerHTML = renderInline(text);
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

function wireFollowup(card, contextText) {
  const toggle = card.querySelector(".followup-toggle");
  const chat = card.querySelector(".followup-chat");
  const messagesEl = card.querySelector(".followup-messages");
  const input = card.querySelector(".followup-input");
  const sendBtn = card.querySelector(".followup-send");
  const history = [];

  toggle.addEventListener("click", () => {
    chat.hidden = !chat.hidden;
    toggle.textContent = chat.hidden ? "Ask a follow-up ↓" : "Hide follow-up ↑";
  });

  async function send() {
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    sendBtn.disabled = true;
    appendFollowupMessage(messagesEl, "user", question);
    history.push({ role: "user", content: question });

    try {
      const res = await fetch("/api/followup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ context: contextText, history: history.slice(0, -1), question }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      appendFollowupMessage(messagesEl, "assistant", data.reply);
      history.push({ role: "assistant", content: data.reply });
    } catch (err) {
      appendFollowupMessage(messagesEl, "assistant", "Error: " + err.message);
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });
}

function appendSubmitCard(problemTitle, code, data) {
  clearEmptyFeedNotice();
  const params = current.details ? current.details.params : null;

  const card = document.createElement("div");
  card.className = "submit-card " + (data.all_passed ? "passed" : "failed");

  const passCount = data.results.filter((r) => r.passed).length;
  const verdictText = data.all_passed
    ? `✓ Correct — ${passCount}/${data.results.length} tests passed`
    : `❌ ${passCount}/${data.results.length} tests passed`;

  const testsHtml = data.results
    .map((r) => {
      const detail = `${formatArgs(r.args, params)} → expected ${JSON.stringify(r.expected)}, got ${r.error ? "error: " + escapeHtml(r.error) : JSON.stringify(r.actual)}`;
      return `<div class="test-result ${r.passed ? "pass" : "fail"}"><span class="test-status">${r.passed ? "✓" : "✗"}</span><span class="test-detail">${escapeHtml(detail).replace(/&quot;/g, '"')}</span></div>`;
    })
    .join("");

  const explanationBlock = data.all_passed
    ? ""
    : `
    <div class="diagnosis"></div>
    <button class="followup-toggle">Ask a follow-up ↓</button>
    <div class="followup-chat" hidden>
      <div class="followup-messages"></div>
      <div class="followup-input-row">
        <input type="text" class="followup-input" placeholder="Ask about this feedback..." />
        <button class="followup-send">Send</button>
      </div>
    </div>
  `;

  card.innerHTML = `
    <span class="submit-verdict">${verdictText}</span>
    <div class="test-results">${testsHtml}</div>
    ${explanationBlock}
  `;

  hintFeed.appendChild(card);
  hintFeed.scrollTop = hintFeed.scrollHeight;

  if (!data.all_passed) {
    renderDiagnosis(card.querySelector(".diagnosis"), data.diagnosis);
    wireFollowup(card, buildSubmitContext(problemTitle, code, data));
  }
}

function renderDiagnosis(container, diagnosis) {
  if (!diagnosis) return;
  const rootRow = document.createElement("div");
  rootRow.className = "diagnosis-root";
  rootRow.innerHTML = `<span class="diagnosis-root-label">Likely cause</span>${renderInline(diagnosis.root_cause || "")}`;
  container.appendChild(rootRow);

  (diagnosis.notes || []).forEach((note) => {
    const type = ["bug", "edge_case", "approach"].includes(note.type) ? note.type : "bug";
    const row = document.createElement("div");
    row.className = `diagnosis-note diagnosis-${type.replace("_", "-")}`;
    row.innerHTML = `
      <span class="diagnosis-tag">${DIAGNOSIS_LABELS[type]}</span>
      <span class="diagnosis-arrow">&#8594;</span>
      <span class="diagnosis-text">${renderInline(note.text)}</span>
    `;
    container.appendChild(row);
  });
}

async function submitCode() {
  if (!current) return;

  const code = editor.getValue();
  submitBtn.disabled = true;
  submitBtn.textContent = "Running...";

  try {
    const res = await fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem_id: current.id, language: languageSelect.value, code }),
    });
    const data = await res.json();
    if (data.error) {
      appendHintCard({ text: data.error, isError: true });
    } else {
      appendSubmitCard(current.title, code, data);
    }
  } catch (err) {
    appendHintCard({ text: "Couldn't submit: " + err.message, isError: true });
  } finally {
    submitBtn.disabled = !current;
    submitBtn.textContent = "Submit";
  }
}

hintBtn.addEventListener("click", getHint);
submitBtn.addEventListener("click", submitCode);

loadProblems();
