const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

let latestAnswer = "";
let latestMultiAnswer = "";
let indexedDocuments = Number(localStorage.getItem("documentCount") || 0);
let indexedChunks = Number(localStorage.getItem("chunkCount") || 0);

function updateCounters(documents = indexedDocuments, chunks = indexedChunks) {
  indexedDocuments = documents;
  indexedChunks = chunks;
  localStorage.setItem("documentCount", String(documents));
  localStorage.setItem("chunkCount", String(chunks));
  $("#document-count").textContent = documents;
  $("#chunk-count").textContent = chunks;
}
updateCounters();

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 3200);
}

function showNotice(element, message, isError = false) {
  element.textContent = message;
  element.classList.remove("hidden", "error");
  if (isError) element.classList.add("error");
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || {});
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}

function switchView(viewId) {
  $$(".view").forEach((view) => view.classList.toggle("active-view", view.id === viewId));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === viewId));
}
$$(".nav-item").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.view)));

const savedTheme = localStorage.getItem("theme") || "dark";
document.documentElement.dataset.theme = savedTheme;
function refreshThemeButton() {
  $("#theme-toggle").textContent = document.documentElement.dataset.theme === "dark" ? "☀ Light" : "☾ Dark";
}
refreshThemeButton();
$("#theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("theme", next);
  refreshThemeButton();
});

function setFileName(input, target) {
  const file = input.files[0];
  target.textContent = file ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB` : "No file selected";
}
$("#left-file").addEventListener("change", () => setFileName($("#left-file"), $("#left-file-name")));
$("#right-file").addEventListener("change", () => setFileName($("#right-file"), $("#right-file-name")));
$("#multi-file-input").addEventListener("change", () => {
  const files = Array.from($("#multi-file-input").files);
  $("#multi-file-label").textContent = files.length ? `${files.length} file(s): ${files.map((f) => f.name).join(", ")}` : "No files selected";
});

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#file-input").files[0];
  if (!file) return showToast("Choose a file first.");
  const status = $("#upload-status");
  showNotice(status, `Uploading ${file.name}...`);
  const body = new FormData();
  body.append("file", file);
  const caption = $("#caption-checkbox").checked;
  try {
    const data = await parseResponse(await fetch(`/upload?caption_images=${caption}&index_document=true`, { method: "POST", body }));
    showNotice(status, "Upload and indexing completed.");
    $("#upload-result").innerHTML = `<strong>${data.filename}</strong><br>${data.total_documents} extracted unit(s) · ${data.indexed_chunks} indexed chunk(s)`;
    $("#upload-result").classList.remove("hidden");
    updateCounters(indexedDocuments + 1, indexedChunks + data.indexed_chunks);
  } catch (error) { showNotice(status, error.message, true); }
});

function appendMessage(role, text, sources = []) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  const sourceHtml = sources.length ? `<div class="sources"><strong>Sources</strong>${sources.map((s, i) => `<div>${i + 1}. ${s.metadata?.source || "indexed document"}${s.metadata?.page !== undefined ? ` · page ${s.metadata.page}` : ""}</div>`).join("")}</div>` : "";
  wrapper.innerHTML = role === "user"
    ? `<div class="message-body"></div><div class="avatar">YOU</div>`
    : `<div class="avatar">AI</div><div class="message-body"></div>`;
  wrapper.querySelector(".message-body").textContent = text;
  if (sourceHtml) wrapper.querySelector(".message-body").insertAdjacentHTML("beforeend", sourceHtml);
  $("#chat-messages").appendChild(wrapper);
  $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight;
}

function appendMultiMessage(role, text, sources = []) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  wrapper.innerHTML = role === "user"
    ? `<div class="message-body"></div><div class="avatar">YOU</div>`
    : `<div class="avatar">AI</div><div class="message-body"></div>`;
  const body = wrapper.querySelector(".message-body");
  body.textContent = text;
  if (sources.length) {
    const sourceBox = document.createElement("div");
    sourceBox.className = "sources";
    sourceBox.innerHTML = `<strong>Sources</strong>${sources.map((source, index) => {
      const name = escapeHtml(source.metadata?.source || "indexed document");
      const page = source.metadata?.page !== undefined ? ` · page ${escapeHtml(source.metadata.page)}` : "";
      return `<div>${index + 1}. ${name}${page}</div>`;
    }).join("")}`;
    body.appendChild(sourceBox);
  }
  $("#multi-messages").appendChild(wrapper);
  $("#multi-messages").scrollTop = $("#multi-messages").scrollHeight;
}

async function askQuestion(question, target = "chat") {
  const isMulti = target === "multi";
  const endpoint = isMulti ? "/ask-multiple" : "/ask";
  if (isMulti) appendMultiMessage("user", question);
  else appendMessage("user", question);

  try {
    const data = await parseResponse(await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, k: isMulti ? 8 : 4, use_hybrid: true }),
    }));
    if (isMulti) {
      latestMultiAnswer = data.answer;
      $("#download-multi-answer").disabled = false;
      appendMultiMessage("assistant", data.answer, data.sources || []);
    } else {
      latestAnswer = data.answer;
      $("#download-answer").disabled = false;
      appendMessage("assistant", data.answer, data.sources || []);
    }
  } catch (error) {
    if (isMulti) appendMultiMessage("assistant", `Error: ${error.message}`);
    else appendMessage("assistant", `Error: ${error.message}`);
  }
}

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#chat-input");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  await askQuestion(question);
});
$$("[data-question]").forEach((button) => button.addEventListener("click", () => askQuestion(button.dataset.question)));
$("#clear-chat").addEventListener("click", () => {
  $("#chat-messages").innerHTML = "";
  latestAnswer = "";
  $("#download-answer").disabled = true;
});
$("#new-chat-button").addEventListener("click", () => $("#clear-chat").click());
function downloadText(text, prefix) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${prefix}-${new Date().toISOString().slice(0, 10)}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

$("#download-answer").addEventListener("click", () => {
  if (latestAnswer) downloadText(latestAnswer, "document-portal-answer");
});

$("#compare-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const left = $("#left-file").files[0];
  const right = $("#right-file").files[0];
  if (!left || !right) return showToast("Choose both documents.");
  const status = $("#compare-status");
  showNotice(status, "Comparing documents...");
  const body = new FormData();
  body.append("left", left); body.append("right", right);
  try {
    const data = await parseResponse(await fetch("/compare", { method: "POST", body }));
    showNotice(status, "Comparison complete.");
    const renderList = (title, values) => `<div class="list-block"><h3>${title}</h3>${values.length ? `<ul>${values.map((v) => `<li>${escapeHtml(v)}</li>`).join("")}</ul>` : `<p class="muted">None detected.</p>`}</div>`;
    $("#compare-result").innerHTML = `<div class="comparison-grid"><div class="stat"><span>Similarity</span><strong>${data.similarity_percent}%</strong></div><div class="stat"><span>Document 1 units</span><strong>${data.left_document_count}</strong></div><div class="stat"><span>Document 2 units</span><strong>${data.right_document_count}</strong></div></div>${renderList("Shared content", data.shared_lines)}${renderList("Only in document one", data.only_in_left)}${renderList("Only in document two", data.only_in_right)}`;
    $("#compare-result").classList.remove("hidden");
  } catch (error) { showNotice(status, error.message, true); }
});

$("#multi-upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = Array.from($("#multi-file-input").files);
  if (!files.length) return showToast("Choose at least one file.");
  const status = $("#multi-upload-status");
  showNotice(status, `Uploading ${files.length} documents...`);
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  try {
    const data = await parseResponse(await fetch("/upload-multiple", { method: "POST", body }));
    showNotice(status, "All documents uploaded and indexed.");
    $("#multi-upload-result").innerHTML = `<strong>${data.successful_files.length} file(s) indexed</strong><br>${data.indexed_chunks} chunks added${data.failed_files.length ? `<br>${data.failed_files.length} failed` : ""}`;
    $("#multi-upload-result").classList.remove("hidden");
    updateCounters(indexedDocuments + data.successful_files.length, indexedChunks + data.indexed_chunks);
  } catch (error) { showNotice(status, error.message, true); }
});
$("#multi-chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#multi-chat-input");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  await askQuestion(question, "multi");
});

$("#clear-multi-chat").addEventListener("click", () => {
  $("#multi-messages").innerHTML = '<div class="message assistant-message"><div class="avatar">AI</div><div class="message-body">Upload several documents, then ask a question that combines information across them.</div></div>';
  latestMultiAnswer = "";
  $("#download-multi-answer").disabled = true;
});

$("#download-multi-answer").addEventListener("click", () => {
  if (!latestMultiAnswer) return;
  downloadText(latestMultiAnswer, "document-portal-multi-answer");
});

function escapeHtml(value) {
  const div = document.createElement("div"); div.textContent = String(value); return div.innerHTML;
}

$("#reset-index").addEventListener("click", async () => {
  const confirmed = window.confirm("Remove every indexed document and clear both chat areas?");
  if (!confirmed) return;
  const button = $("#reset-index");
  button.disabled = true;
  button.textContent = "Clearing...";
  try {
    const data = await parseResponse(await fetch("/index/reset", { method: "POST" }));
    updateCounters(0, 0);
    $("#file-input").value = "";
    $("#multi-file-input").value = "";
    $("#upload-result").classList.add("hidden");
    $("#multi-upload-result").classList.add("hidden");
    $("#upload-status").classList.add("hidden");
    $("#multi-upload-status").classList.add("hidden");
    $("#clear-chat").click();
    $("#clear-multi-chat").click();
    showToast(data.message || "Indexed documents cleared.");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "↻ Refresh documents";
  }
});

async function loadUsers() {
  const table = $("#users-table");
  if (!table) return;
  try {
    const data = await parseResponse(await fetch("/admin/users"));
    table.innerHTML = data.users.map((user) => `<div class="user-row"><div><strong>${escapeHtml(user.email)}</strong><small>${escapeHtml(user.role)}</small></div><span>${user.active ? "Active" : "Disabled"}</span><button class="secondary-button user-toggle" data-email="${escapeHtml(user.email)}" data-active="${user.active ? "false" : "true"}" type="button">${user.active ? "Disable" : "Enable"}</button></div>`).join("");
    $$(".user-toggle").forEach((button) => button.addEventListener("click", async () => {
      const body = new FormData();
      body.append("email", button.dataset.email);
      body.append("active", button.dataset.active);
      await parseResponse(await fetch("/admin/users/status", { method: "POST", body }));
      await loadUsers();
    }));
  } catch (error) {
    table.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

if ($("#add-user-form")) {
  $("#add-user-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = $("#user-status");
    const body = new FormData();
    body.append("email", $("#new-user-email").value.trim());
    body.append("role", $("#new-user-role").value);
    try {
      const data = await parseResponse(await fetch("/admin/users", { method: "POST", body }));
      showNotice(status, `${data.user.email} added.`);
      event.target.reset();
      await loadUsers();
    } catch (error) {
      showNotice(status, error.message, true);
    }
  });
  $("#refresh-users").addEventListener("click", loadUsers);
  loadUsers();
}

async function loadEvaluation() {
  try {
    const data = await parseResponse(await fetch("/evaluation/status"));
    $("#eval-case-count").textContent = data.test_cases.length;
    $("#evaluation-cases").innerHTML = data.test_cases.map((item, index) => `<div class="eval-row"><span>${String(index + 1).padStart(2, "0")}</span><div>${escapeHtml(item.question)}</div><small>${escapeHtml(item.focus)}</small></div>`).join("");
  } catch (error) { $("#evaluation-cases").innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`; }
}
$("#refresh-eval").addEventListener("click", loadEvaluation);
loadEvaluation();
