const hintBtn = document.getElementById("hint-btn");
const hintOutput = document.getElementById("hint-output");
const hintText = document.getElementById("hint-text");
const addForm = document.getElementById("add-problem-form");
const problemList = document.getElementById("problem-list");

async function getHint() {
  const problem = document.getElementById("problem-input").value;
  const code = document.getElementById("code-input").value;
  const hintLevel = document.getElementById("hint-level").value;

  if (!problem.trim()) {
    alert("Paste the problem statement first.");
    return;
  }

  hintBtn.disabled = true;
  hintBtn.textContent = "Thinking...";

  try {
    const res = await fetch("/api/hint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem, code, hint_level: hintLevel }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    hintText.textContent = data.hint;
    hintOutput.hidden = false;
  } catch (err) {
    hintText.textContent = "Error getting hint: " + err.message;
    hintOutput.hidden = false;
  } finally {
    hintBtn.disabled = false;
    hintBtn.textContent = "Get Hint";
  }
}

async function loadProblems() {
  const res = await fetch("/api/problems");
  const problems = await res.json();
  problemList.innerHTML = "";

  problems.forEach((p) => {
    const li = document.createElement("li");
    li.className = "problem-item" + (p.status === "solved" ? " solved" : "");
    li.innerHTML = `
      <span>${p.title} <small>(${p.difficulty})</small></span>
      ${p.status !== "solved" ? `<button data-id="${p.id}" class="solve-btn">Solved</button>` : "✓"}
    `;
    problemList.appendChild(li);
  });

  document.querySelectorAll(".solve-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/problems/${btn.dataset.id}/solve`, { method: "POST" });
      loadProblems();
    });
  });
}

addForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = document.getElementById("new-title").value;
  const difficulty = document.getElementById("new-difficulty").value;

  await fetch("/api/problems", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, difficulty }),
  });

  document.getElementById("new-title").value = "";
  loadProblems();
});

hintBtn.addEventListener("click", getHint);

loadProblems();
