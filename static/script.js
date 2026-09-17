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
const hintLevelSelect = document.getElementById("hint-level");
const hintBtn = document.getElementById("hint-btn");
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
let current = null; // { id, title, difficulty, trackedId, solved, details }

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
  const created = await createRes.json();
  return { id: created.id, title, difficulty, status: "in_progress" };
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

  hintBtn.disabled = false;

  const tracked = await findOrCreateTracked(p.title, p.difficulty);
  const solved = tracked.status === "solved";

  current = { id: p.id, title: p.title, difficulty: p.difficulty, trackedId: tracked.id, solved, details };
  loadDraftForCurrent();
  updateSubmitAvailability();
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
    <div class="hint-card-meta"><span>${isError ? "Error" : "Hint level " + level}</span></div>
    <p></p>
  `;
  card.querySelector("p").innerHTML = renderInline(text);
  hintFeed.appendChild(card);
  hintFeed.scrollTop = hintFeed.scrollHeight;
}

async function getHint() {
  if (!current) return;

  const problemText = detailsInput.value.trim()
    ? detailsInput.value.trim()
    : current.details
    ? `LeetCode-style #${current.id}: ${current.title} (${current.difficulty})\n${current.details.description}`
    : `LeetCode #${current.id}: ${current.title} (${current.difficulty})`;
  const code = editor.getValue();
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

function formatArgs(args, params) {
  return args
    .map((a, i) => `${(params && params[i]) || "arg" + i}=${JSON.stringify(a)}`)
    .join(", ");
}

function buildSubmitContext(problemTitle, code, data) {
  const lines = data.results.map(
    (r) => `${r.passed ? "PASS" : "FAIL"} expected=${JSON.stringify(r.expected)} actual=${JSON.stringify(r.actual)}${r.error ? " error=" + r.error : ""}`
  );
  return `Problem: ${problemTitle}\n\nCode:\n${code}\n\nTest results:\n${lines.join("\n")}\n\nMy explanation to you: ${data.explanation}`;
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
    <div class="submit-explanation"></div>
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
    card.querySelector(".submit-explanation").innerHTML = renderInline(data.explanation);
    wireFollowup(card, buildSubmitContext(problemTitle, code, data));
  }
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
