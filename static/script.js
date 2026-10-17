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
const ladder = document.getElementById("hint-ladder");
const paneScroll = document.getElementById("pane-scroll");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const hintBtn = document.getElementById("hint-btn");
const submitBtn = document.getElementById("submit-btn");
const hintFeed = document.getElementById("hint-feed");
const codeInput = document.getElementById("code-input");

// ---------- Intro splash ----------
(function runSplash() {
  const splash = document.getElementById("splash");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finish = () => {
    splash.classList.add("done");
    document.body.classList.remove("is-loading");
    setTimeout(() => splash.remove(), 600);
  };
  if (reduce) return finish();
  const t = setTimeout(finish, 1900);
  splash.addEventListener("click", () => { clearTimeout(t); finish(); });
})();

// ---------- Anonymous per-browser id, so progress is yours ----------
function getClientId() {
  let id = null;
  try { id = localStorage.getItem("leetcoach_client_id"); } catch (e) {}
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
    try { localStorage.setItem("leetcoach_client_id", id); } catch (e) {}
  }
  return id;
}
const CLIENT_ID = getClientId();

function api(url, options = {}) {
  const headers = Object.assign({ "X-Client-Id": CLIENT_ID }, options.headers || {});
  if (options.body) headers["Content-Type"] = "application/json";
  return fetch(url, Object.assign({}, options, { headers }));
}

const HINT_NAMES = { 1: "Nudge", 2: "Pattern", 3: "Approach", 4: "Pseudocode" };
let hintLevel = 1;
let chatHistory = [];

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
    .replace(/```[a-z]*\n?([\s\S]*?)```/g, '<code style="display:block;padding:8px 10px;margin:4px 0">$1</code>')
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
  const res = await api("/api/problems");
  const tracked = await res.json();
  const existing = tracked.find((t) => t.title === title);
  if (existing) return existing;

  const createRes = await api("/api/problems", {
    method: "POST",
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
  setHintLevel(1);
  ladder.querySelectorAll(".rung").forEach((r) => r.classList.remove("used"));

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
  await api(`/api/problems/${current.trackedId}/solve`, { method: "POST" });
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

function scrollFeed() {
  requestAnimationFrame(() => {
    paneScroll.scrollTop = paneScroll.scrollHeight;
    if (window.matchMedia("(max-width: 900px)").matches) {
      const last = hintFeed.lastElementChild;
      if (last) last.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
}

function setHintLevel(level) {
  hintLevel = Math.max(1, Math.min(4, level));
  ladder.querySelectorAll(".rung").forEach((r) => {
    const on = Number(r.dataset.level) === hintLevel;
    r.classList.toggle("active", on);
    r.setAttribute("aria-checked", String(on));
  });
}

ladder.addEventListener("click", (e) => {
  const rung = e.target.closest(".rung");
  if (rung) setHintLevel(Number(rung.dataset.level));
});

function appendHintCard({ level, text, isError }) {
  clearEmptyFeedNotice();
  const card = document.createElement("div");
  card.className = "hint-card" + (isError ? " error" : "");
  card.innerHTML = `
    <div class="hint-card-meta"><span>${isError ? "Something went wrong" : `Hint ${level} · ${HINT_NAMES[level]}`}</span></div>
    <p></p>
  `;
  card.querySelector("p").innerHTML = renderInline(text);
  hintFeed.appendChild(card);
  scrollFeed();
}

function currentProblemText() {
  if (detailsInput.value.trim()) return detailsInput.value.trim();
  if (!current) return "";
  return current.details
    ? `LeetCode-style #${current.id}: ${current.title} (${current.difficulty})\n${current.details.description}`
    : `LeetCode #${current.id}: ${current.title} (${current.difficulty})`;
}

async function getHint() {
  if (!current) return;

  const problemText = currentProblemText();
  const code = editor.getValue();
  const level = hintLevel;

  hintBtn.disabled = true;
  hintBtn.textContent = "Thinking...";

  try {
    const res = await api("/api/hint", {
      method: "POST",
      body: JSON.stringify({ problem: problemText, code, hint_level: level }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    appendHintCard({ level: data.hint_level, text: data.hint });
    chatHistory.push({ role: "user", content: `Give me a level ${data.hint_level} hint.` });
    chatHistory.push({ role: "assistant", content: data.hint });
    const rung = ladder.querySelector(`.rung[data-level="${data.hint_level}"]`);
    if (rung) rung.classList.add("used");
    setHintLevel(data.hint_level + 1); // next click goes one level deeper

    if (current.trackedId) {
      api(`/api/problems/${current.trackedId}/hint_used`, { method: "POST" }).catch(() => {});
    }
  } catch (err) {
    appendHintCard({ text: "Couldn't get a hint: " + err.message, isError: true });
  } finally {
    hintBtn.disabled = false;
    hintBtn.textContent = "Get hint";
  }
}

function formatArgs(args, params) {
  return args
    .map((a, i) => `${(params && params[i]) || "arg" + i}=${JSON.stringify(a)}`)
    .join(", ");
}

// ---------- Chat with the coach (available from the start) ----------

function appendMessage(role, text) {
  clearEmptyFeedNotice();
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  msg.innerHTML = renderInline(text);
  hintFeed.appendChild(msg);
  scrollFeed();
  return msg;
}

function showTyping() {
  clearEmptyFeedNotice();
  const el = document.createElement("div");
  el.className = "msg assistant";
  el.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
  hintFeed.appendChild(el);
  scrollFeed();
  return el;
}

async function askCoach(question) {
  question = question.trim();
  if (!question) return;
  appendMessage("user", question);
  chatInput.value = "";
  chatSend.disabled = true;
  const typing = showTyping();

  try {
    const res = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        question,
        problem: currentProblemText(),
        code: editor.getValue(),
        history: chatHistory,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    typing.remove();
    appendMessage("assistant", data.reply);
    chatHistory.push({ role: "user", content: question });
    chatHistory.push({ role: "assistant", content: data.reply });
    chatHistory = chatHistory.slice(-12);
  } catch (err) {
    typing.remove();
    appendHintCard({ text: "Couldn't reach the coach: " + err.message, isError: true });
  } finally {
    chatSend.disabled = false;
    chatInput.focus();
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  askCoach(chatInput.value);
});

document.getElementById("starter-chips").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip) askCoach(chip.dataset.q);
});

function appendSubmitCard(problemTitle, code, data) {
  clearEmptyFeedNotice();
  const params = current.details ? current.details.params : null;

  const card = document.createElement("div");
  card.className = "submit-card " + (data.all_passed ? "passed" : "failed");

  const passCount = data.results.filter((r) => r.passed).length;
  const verdictText = data.all_passed
    ? `✓ Accepted · ${passCount}/${data.results.length} tests passed`
    : `✗ ${passCount}/${data.results.length} tests passed`;

  const testsHtml = data.results
    .map((r) => {
      const detail = `${formatArgs(r.args, params)} → expected ${JSON.stringify(r.expected)}, got ${r.error ? "error: " + escapeHtml(r.error) : JSON.stringify(r.actual)}`;
      return `<div class="test-result ${r.passed ? "pass" : "fail"}"><span class="test-status">${r.passed ? "✓" : "✗"}</span><span class="test-detail">${escapeHtml(detail).replace(/&quot;/g, '"')}</span></div>`;
    })
    .join("");

  const explanationBlock = data.all_passed ? "" : `<div class="submit-explanation"></div>`;

  card.innerHTML = `
    <span class="submit-verdict">${verdictText}</span>
    <div class="test-results">${testsHtml}</div>
    ${explanationBlock}
  `;

  hintFeed.appendChild(card);
  scrollFeed();

  if (!data.all_passed) {
    card.querySelector(".submit-explanation").innerHTML =
      renderInline(data.explanation) + '<span class="ask-more">Questions about this? Ask the coach below.</span>';
    const failing = data.results.filter((r) => !r.passed)
      .map((r) => `expected ${JSON.stringify(r.expected)}, got ${r.error || JSON.stringify(r.actual)}`).join("; ");
    chatHistory.push({ role: "user", content: `I submitted my code for ${problemTitle}. Failing tests: ${failing}` });
    chatHistory.push({ role: "assistant", content: data.explanation });
  } else if (!current.solved) {
    current.solved = true;
    api(`/api/problems/${current.trackedId}/solve`, { method: "POST" }).catch(() => {});
    updateSolveButton();
  }
}

async function submitCode() {
  if (!current) return;

  const code = editor.getValue();
  submitBtn.disabled = true;
  submitBtn.textContent = "Running...";

  try {
    const res = await api("/api/submit", {
      method: "POST",
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
