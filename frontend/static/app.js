const state = { token: null, user: null, branches: [], roles: [], permissionCatalog: [] };

function hasPerm(key) {
  return !!(state.user && state.user.permissions && state.user.permissions.includes(key));
}
function hasAnyPerm(keys) {
  return keys.some(hasPerm);
}

function flash(msg, kind, targetId) {
  const el = document.getElementById(targetId || "flash");
  el.innerHTML = `<div class="flash ${kind}">${msg}</div>`;
  setTimeout(() => { el.innerHTML = ""; }, 6000);
}

async function api(path, opts = {}) {
  opts.headers = opts.headers || {};
  if (state.token) opts.headers["Authorization"] = `Bearer ${state.token}`;
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

async function login() {
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  try {
    const tok = await api("/api/auth/login", { method: "POST", body });
    state.token = tok.access_token;
    localStorage.setItem("dsa_token", state.token);
    await afterLogin();
  } catch (e) {
    flash(e.message, "err", "login-flash");
  }
}

const ADMIN_SECTION_PERMS = ["MANAGE_USERS", "MANAGE_ROLES", "MANAGE_BRANCHES", "MANAGE_DSAS", "MANAGE_DTLS"];

async function afterLogin() {
  state.user = await api("/api/auth/me");
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-screen").classList.remove("hidden");
  document.getElementById("userbox").innerHTML =
    `${state.user.full_name} (${state.user.role_name}) <button class="secondary" id="logout-btn">Sign out</button>`;
  document.getElementById("logout-btn").onclick = logout;

  document.querySelector('nav button[data-tab="admin"]').classList.toggle("hidden", !hasAnyPerm(ADMIN_SECTION_PERMS));
  document.querySelectorAll("#admin-subnav button").forEach(b => {
    b.classList.toggle("hidden", !hasPerm(b.dataset.perm));
  });

  await loadBranches();
  await refreshUploads();
  await refreshRuns();
}

function logout() {
  localStorage.removeItem("dsa_token");
  location.reload();
}

async function loadBranches() {
  try {
    state.branches = await api("/api/admin/branches");
  } catch (e) {
    state.branches = []; // requires MANAGE_BRANCHES; that's fine, selects just stay empty otherwise
  }
  const selects = ["bm-branch-select", "run-branch-select", "exc-branch-select", "user-form-branch", "dsa-form-branch", "admin-dtl-branch"];
  for (const id of selects) {
    const sel = document.getElementById(id);
    if (!sel) continue;
    sel.innerHTML = '<option value="">(none / all)</option>' + state.branches.map(b => `<option value="${b.id}">${b.name}</option>`).join("");
  }
}

function branchName(id) {
  const b = state.branches.find(x => x.id === id);
  return b ? b.name : (id ?? "-");
}

const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];

function populatePeriodSelects(monthSelId, yearSelId) {
  const monthSel = document.getElementById(monthSelId);
  const yearSel = document.getElementById(yearSelId);
  const now = new Date();
  monthSel.innerHTML = MONTH_NAMES.map((name, i) => `<option value="${i + 1}">${name}</option>`).join("");
  monthSel.value = now.getMonth() + 1;
  const years = [];
  for (let y = now.getFullYear() - 1; y <= now.getFullYear() + 1; y++) years.push(y);
  yearSel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join("");
  yearSel.value = now.getFullYear();
}

// ---- Uploads ----
async function refreshUploads() {
  const uploads = await api("/api/uploads");
  const tbody = document.querySelector("#uploads-table tbody");
  tbody.innerHTML = uploads.map(u => `
    <tr data-id="${u.id}" class="upload-row" style="cursor:pointer">
      <td>${u.id}</td><td>${u.upload_type}</td><td>${u.branch_id ?? "-"}</td>
      <td>${u.period_year ? `${MONTH_NAMES[u.period_month - 1].slice(0,3)} ${u.period_year}` : "-"}</td>
      <td>${u.original_filename}</td>
      <td><span class="status-pill status-${u.status}">${u.status}</span></td>
      <td>${u.rows_accepted}/${u.total_rows}</td><td>${u.rows_rejected}</td><td>${u.warning_rows}</td>
      <td>${new Date(u.uploaded_at).toLocaleString()}</td>
    </tr>`).join("");
  tbody.querySelectorAll(".upload-row").forEach(row => {
    row.onclick = () => showUploadDetail(row.dataset.id);
  });
}

async function showUploadDetail(id) {
  const u = await api(`/api/uploads/${id}`);
  const el = document.getElementById("upload-detail");
  if (!u.errors || u.errors.length === 0) {
    el.innerHTML = `<p><b>Upload #${u.id}</b>: no errors or warnings.</p>`;
    return;
  }
  el.innerHTML = `<p><b>Upload #${u.id} issues</b> (${u.errors.length}):</p><table><thead><tr><th>Row</th><th>Severity</th><th>Column</th><th>Message</th></tr></thead><tbody>` +
    u.errors.map(e => `<tr><td>${e.row_number || "(file/sheet)"}</td><td class="severity-${e.severity}">${e.severity}</td><td>${e.column_name ?? ""}</td><td>${e.message}</td></tr>`).join("") +
    `</tbody></table>`;
}

function submitSummary(u) {
  const parts = [`${u.rows_accepted} accepted (${u.rows_created} new, ${u.rows_updated} updated${u.rows_unchanged ? `, ${u.rows_unchanged} unchanged` : ""})`, `${u.rows_rejected} rejected`];
  if (u.warning_rows) parts.push(`${u.warning_rows} warning(s)`);
  return `Upload #${u.id}: ${u.status} - ${parts.join(", ")}`;
}

async function uploadBranchManagerFile() {
  const fileInput = document.getElementById("bm-file");
  if (!fileInput.files.length) return flash("Choose a file first", "err");
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  fd.append("period_month", document.getElementById("bm-period-month").value);
  fd.append("period_year", document.getElementById("bm-period-year").value);
  const branchId = document.getElementById("bm-branch-select").value;
  if (branchId) fd.append("branch_id", branchId);
  try {
    const u = await api("/api/uploads/branch-manager", { method: "POST", body: fd });
    flash(submitSummary(u), u.status === "FAILED" || u.rows_rejected > 0 ? "err" : "ok");
    await refreshUploads();
    showUploadDetail(u.id);
  } catch (e) { flash(e.message, "err"); }
}

async function uploadBusinessManagerFile() {
  const fileInput = document.getElementById("bz-file");
  if (!fileInput.files.length) return flash("Choose a file first", "err");
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  fd.append("period_month", document.getElementById("bz-period-month").value);
  fd.append("period_year", document.getElementById("bz-period-year").value);
  try {
    const u = await api("/api/uploads/business-manager", { method: "POST", body: fd });
    flash(submitSummary(u), u.status === "FAILED" || u.rows_rejected > 0 ? "err" : "ok");
    await refreshUploads();
    showUploadDetail(u.id);
  } catch (e) { flash(e.message, "err"); }
}

// ---- Commission Runs ----
async function refreshRuns() {
  const runs = await api("/api/commission/runs");
  const tbody = document.querySelector("#runs-table tbody");
  tbody.innerHTML = runs.map(r => {
    const actions = [];
    if (r.status === "DRAFT") actions.push(`<button class="secondary" onclick="calcRun(${r.id})">Calculate</button>`);
    if (hasPerm("REVIEW_COMMISSION_RUN") && r.status === "DRAFT") actions.push(`<button class="secondary" onclick="reviewRun(${r.id})">Review</button>`);
    if (hasPerm("LOCK_COMMISSION_RUN") && r.status === "REVIEWED") actions.push(`<button onclick="lockRun(${r.id})">Lock</button>`);
    if (hasPerm("MARK_RUN_PAID") && r.status === "LOCKED") actions.push(`<button class="secondary" onclick="markPaidRun(${r.id})">Mark Paid</button>`);
    actions.push(`<button class="secondary" onclick="downloadRun(${r.id})">Download</button>`);
    return `<tr><td>${r.id}</td><td>${r.run_type}</td><td>${r.branch_id ?? "-"}</td><td>${r.period}</td>
      <td><span class="status-pill status-${r.status}">${r.status}</span></td><td>${actions.join(" ")}</td></tr>`;
  }).join("");
}

async function createRun() {
  const run_type = document.getElementById("run-type").value;
  const branch_id = document.getElementById("run-branch-select").value || null;
  const period = document.getElementById("run-period").value.trim();
  if (!period.match(/^\d{4}-\d{2}$/)) return flash("Period must be in YYYY-MM format", "err");
  if (run_type === "BRANCH" && !branch_id) return flash("Branch is required for a BRANCH run", "err");
  try {
    const r = await api("/api/commission/runs", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_type, branch_id: branch_id ? Number(branch_id) : null, period }),
    });
    flash(`Run #${r.id} created (${r.status})`, "ok");
    await refreshRuns();
  } catch (e) { flash(e.message, "err"); }
}

async function calcRun(id) {
  try { await api(`/api/commission/runs/${id}/calculate`, { method: "POST" }); flash(`Run #${id} calculated`, "ok"); await refreshRuns(); }
  catch (e) { flash(e.message, "err"); }
}
async function reviewRun(id) {
  try { await api(`/api/commission/runs/${id}/review`, { method: "POST" }); flash(`Run #${id} marked REVIEWED`, "ok"); await refreshRuns(); }
  catch (e) { flash(e.message, "err"); }
}
async function lockRun(id) {
  if (!confirm(`Lock run #${id}? Locked runs can never be recalculated - corrections must go through adjustments on a later run.`)) return;
  try { await api(`/api/commission/runs/${id}/lock`, { method: "POST" }); flash(`Run #${id} LOCKED`, "ok"); await refreshRuns(); }
  catch (e) { flash(e.message, "err"); }
}
async function markPaidRun(id) {
  try { await api(`/api/commission/runs/${id}/mark-paid`, { method: "POST" }); flash(`Run #${id} marked PAID`, "ok"); await refreshRuns(); }
  catch (e) { flash(e.message, "err"); }
}
function downloadRun(id) {
  fetch(`/api/reports/commission/${id}`, { headers: { Authorization: `Bearer ${state.token}` } })
    .then(res => res.blob()).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `commission_run_${id}.xlsx`; a.click();
    });
}

// ---- Exceptions ----
async function loadExceptions() {
  const period = document.getElementById("exc-period").value.trim() || "";
  const branch_id = document.getElementById("exc-branch-select").value;
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  if (branch_id) params.set("branch_id", branch_id);
  const rows = await api(`/api/exceptions?${params.toString()}`);
  const tbody = document.querySelector("#exceptions-table tbody");
  tbody.innerHTML = rows.map(r => `<tr>
    <td class="match-${r.match_status}">${r.match_status}</td><td>${r.branch_name ?? ""}</td><td>${r.client_name ?? ""}</td>
    <td>${r.client_account_no_branch ?? ""}</td><td>${r.client_account_no_business ?? ""}</td>
    <td>${r.dsa_code ?? ""} ${r.dsa_name ?? ""}</td><td>${r.loan_type ?? ""}</td><td>${r.disbursement_date ?? ""}</td>
    <td>${r.notes ?? ""}</td></tr>`).join("");
}
function downloadExceptions() {
  const period = document.getElementById("exc-period").value.trim();
  if (!period) return flash("Enter a period first", "err");
  const branch_id = document.getElementById("exc-branch-select").value;
  const params = new URLSearchParams({ period });
  if (branch_id) params.set("branch_id", branch_id);
  fetch(`/api/reports/exceptions?${params.toString()}`, { headers: { Authorization: `Bearer ${state.token}` } })
    .then(res => res.blob()).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `exceptions_${period}.xlsx`; a.click();
    });
}

// ---- Admin: sub-navigation ----
function switchAdminSection(name) {
  document.querySelectorAll("#admin-subnav button").forEach(b => b.classList.toggle("active", b.dataset.adminSection === name));
  document.querySelectorAll(".admin-section").forEach(s => s.classList.toggle("hidden", s.id !== `admin-section-${name}`));
  if (name === "users") refreshUsers();
  if (name === "roles") refreshRoles();
  if (name === "branches") refreshAdminBranches();
  if (name === "dsas") refreshDsas();
  if (name === "dtls") refreshDtls();
}

function firstVisibleAdminSection() {
  const btn = Array.from(document.querySelectorAll("#admin-subnav button")).find(b => !b.classList.contains("hidden"));
  return btn ? btn.dataset.adminSection : null;
}

// ---- Admin: Users ----
async function refreshUsers() {
  if (state.roles.length === 0) await refreshRoles();
  const roleSel = document.getElementById("user-form-role");
  roleSel.innerHTML = state.roles.map(r => `<option value="${r.id}">${r.name}</option>`).join("");

  const users = await api("/api/admin/users");
  document.querySelector("#admin-users-table tbody").innerHTML =
    users.map(u => `<tr><td>${u.id}</td><td>${u.email}</td><td>${u.full_name}</td><td>${u.role_name}</td><td>${u.branch_id ? branchName(u.branch_id) : ""}</td></tr>`).join("");
}

async function createUser() {
  const email = document.getElementById("user-form-email").value.trim();
  const full_name = document.getElementById("user-form-name").value.trim();
  const password = document.getElementById("user-form-password").value;
  const role_id = Number(document.getElementById("user-form-role").value);
  const branch_id = document.getElementById("user-form-branch").value || null;
  if (!email || !full_name || !password || !role_id) return flash("Email, name, password, and role are required", "err");
  try {
    await api("/api/admin/users", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, full_name, password, role_id, branch_id: branch_id ? Number(branch_id) : null }),
    });
    flash("User created", "ok");
    document.getElementById("user-form").classList.add("hidden");
    ["user-form-email", "user-form-name", "user-form-password"].forEach(id => document.getElementById(id).value = "");
    await refreshUsers();
  } catch (e) { flash(e.message, "err"); }
}

// ---- Admin: Roles ----
async function loadPermissionCatalog() {
  if (state.permissionCatalog.length) return;
  state.permissionCatalog = await api("/api/admin/permissions");
}

async function refreshRoles() {
  state.roles = await api("/api/admin/roles");
  document.querySelector("#admin-roles-table tbody").innerHTML = state.roles.map(r => {
    const perms = r.permissions.slice(0, 4).map(p => `<span class="pill">${p}</span>`).join("");
    const more = r.permissions.length > 4 ? `<span class="pill">+${r.permissions.length - 4} more</span>` : "";
    const actions = [`<button class="link" onclick="openRoleForm(${r.id})">Edit</button>`];
    if (!r.is_system_role) actions.push(`<button class="link" onclick="deleteRole(${r.id})">Delete</button>`);
    return `<tr><td>${r.name}</td><td>${r.description ?? ""}</td><td>${perms}${more} (${r.permission_count})</td>
      <td>${r.is_system_role ? "Yes" : "No"}</td><td>${actions.join(" ")}</td></tr>`;
  }).join("");
}

async function openRoleForm(roleId) {
  await loadPermissionCatalog();
  const grid = document.getElementById("role-form-permissions");
  grid.innerHTML = state.permissionCatalog.map(p => `
    <label><input type="checkbox" value="${p.key}" />
      <span><span class="perm-key">${p.key}</span><span class="perm-desc">${p.description ?? ""}</span></span>
    </label>`).join("");

  const role = roleId ? state.roles.find(r => r.id === roleId) : null;
  document.getElementById("role-form-id").value = role ? role.id : "";
  document.getElementById("role-form-name").value = role ? role.name : "";
  document.getElementById("role-form-description").value = role ? (role.description ?? "") : "";
  if (role) {
    const set = new Set(role.permissions);
    grid.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = set.has(cb.value); });
  }
  document.getElementById("role-form").classList.remove("hidden");
}

async function saveRole() {
  const id = document.getElementById("role-form-id").value;
  const name = document.getElementById("role-form-name").value.trim();
  const description = document.getElementById("role-form-description").value.trim() || null;
  const permission_keys = Array.from(document.querySelectorAll("#role-form-permissions input:checked")).map(cb => cb.value);
  if (!name) return flash("Role name is required", "err");
  try {
    if (id) {
      await api(`/api/admin/roles/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description, permission_keys }),
      });
      flash("Role updated", "ok");
    } else {
      await api("/api/admin/roles", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description, permission_keys }),
      });
      flash("Role created", "ok");
    }
    document.getElementById("role-form").classList.add("hidden");
    await refreshRoles();
  } catch (e) { flash(e.message, "err"); }
}

async function deleteRole(id) {
  if (!confirm("Delete this role? Users must be reassigned first.")) return;
  try {
    await api(`/api/admin/roles/${id}`, { method: "DELETE" });
    flash("Role deleted", "ok");
    await refreshRoles();
  } catch (e) { flash(e.message, "err"); }
}

// ---- Admin: Branches ----
async function refreshAdminBranches() {
  const branches = await api("/api/admin/branches");
  document.querySelector("#admin-branches-table tbody").innerHTML =
    branches.map(b => `<tr><td>${b.id}</td><td>${b.name}</td><td>${b.code ?? ""}</td></tr>`).join("");
}

async function createBranch() {
  const name = document.getElementById("admin-branch-name").value.trim();
  const code = document.getElementById("admin-branch-code").value.trim() || null;
  if (!name) return flash("Branch name required", "err");
  try {
    await api("/api/admin/branches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, code }) });
    flash("Branch created", "ok");
    document.getElementById("branch-form").classList.add("hidden");
    document.getElementById("admin-branch-name").value = "";
    document.getElementById("admin-branch-code").value = "";
    await loadBranches();
    await refreshAdminBranches();
  } catch (e) { flash(e.message, "err"); }
}

// ---- Admin: DTLs ----
async function refreshDtls() {
  const dtls = await api("/api/admin/dtls");
  document.querySelector("#admin-dtls-table tbody").innerHTML =
    dtls.map(d => `<tr><td>${d.dtl_code}</td><td>${d.dtl_name}</td><td>${d.branch_id ? branchName(d.branch_id) : ""}</td></tr>`).join("");
}

async function createDtl() {
  const dtl_code = document.getElementById("admin-dtl-code").value.trim();
  const dtl_name = document.getElementById("admin-dtl-name").value.trim();
  const branch_id = document.getElementById("admin-dtl-branch").value || null;
  if (!dtl_code || !dtl_name) return flash("DTL code and name required", "err");
  try {
    await api("/api/admin/dtls", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dtl_code, dtl_name, branch_id: branch_id ? Number(branch_id) : null }),
    });
    flash("DTL created", "ok");
    document.getElementById("dtl-form").classList.add("hidden");
    document.getElementById("admin-dtl-code").value = "";
    document.getElementById("admin-dtl-name").value = "";
    await refreshDtls();
  } catch (e) { flash(e.message, "err"); }
}

// ---- Admin: DSAs ----
async function refreshDsas() {
  const dsas = await api("/api/admin/dsas");
  document.querySelector("#admin-dsas-table tbody").innerHTML = dsas.map(d => `
    <tr><td>${d.dsa_code}</td><td>${d.dsa_name}</td><td>${d.branch_id ? branchName(d.branch_id) : ""}</td>
      <td>${d.current_dtl_name ? `${d.current_dtl_code} - ${d.current_dtl_name}` : "(unassigned)"}</td>
      <td><button class="link" onclick='openDsaForm(${JSON.stringify(d).replace(/'/g, "&apos;")})'>Edit</button></td>
    </tr>`).join("");
}

async function dsaFormLoadDtls(branchId, selectedDtlId) {
  const dtlSel = document.getElementById("dsa-form-dtl");
  if (!branchId) { dtlSel.innerHTML = '<option value="">(select a branch first)</option>'; return; }
  const dtls = await api(`/api/admin/dtls?branch_id=${branchId}`);
  dtlSel.innerHTML = '<option value="">(unassigned)</option>' + dtls.map(d => `<option value="${d.id}">${d.dtl_code} - ${d.dtl_name}</option>`).join("");
  if (selectedDtlId) dtlSel.value = selectedDtlId;
}

async function openDsaForm(dsa) {
  document.getElementById("dsa-form-id").value = dsa ? dsa.id : "";
  document.getElementById("dsa-form-code").value = dsa ? dsa.dsa_code : "";
  document.getElementById("dsa-form-name").value = dsa ? dsa.dsa_name : "";
  document.getElementById("dsa-form-account").value = dsa ? (dsa.dsa_account_no ?? "") : "";
  document.getElementById("dsa-form-branch").value = dsa ? (dsa.branch_id ?? "") : "";
  await dsaFormLoadDtls(dsa ? dsa.branch_id : null, dsa ? dsa.current_dtl_id : null);
  document.getElementById("dsa-form").classList.remove("hidden");
}

async function saveDsa() {
  const id = document.getElementById("dsa-form-id").value;
  const dsa_code = document.getElementById("dsa-form-code").value.trim();
  const dsa_name = document.getElementById("dsa-form-name").value.trim();
  const dsa_account_no = document.getElementById("dsa-form-account").value.trim() || null;
  const branch_id = document.getElementById("dsa-form-branch").value || null;
  const dtl_id = document.getElementById("dsa-form-dtl").value || null;
  if (!dsa_code || !dsa_name) return flash("DSA code and name are required", "err");
  const payload = {
    dsa_name, dsa_account_no,
    branch_id: branch_id ? Number(branch_id) : null,
    dtl_id: dtl_id ? Number(dtl_id) : null,
  };
  try {
    if (id) {
      await api(`/api/admin/dsas/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      flash("DSA updated", "ok");
    } else {
      await api("/api/admin/dsas", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dsa_code, ...payload }),
      });
      flash("DSA created", "ok");
    }
    document.getElementById("dsa-form").classList.add("hidden");
    await refreshDsas();
  } catch (e) { flash(e.message, "err"); }
}

// ---- Tabs & wiring ----
function switchTab(name) {
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("hidden", t.id !== `tab-${name}`));
  if (name === "admin") {
    const first = firstVisibleAdminSection();
    if (first) switchAdminSection(first);
  }
}

document.getElementById("login-btn").onclick = login;
document.getElementById("login-password").addEventListener("keydown", e => { if (e.key === "Enter") login(); });
document.querySelectorAll("nav button").forEach(b => b.onclick = () => switchTab(b.dataset.tab));
document.getElementById("bm-upload-btn").onclick = uploadBranchManagerFile;
document.getElementById("bz-upload-btn").onclick = uploadBusinessManagerFile;
document.getElementById("refresh-uploads").onclick = refreshUploads;
document.getElementById("create-run-btn").onclick = createRun;
document.getElementById("refresh-runs").onclick = refreshRuns;
document.getElementById("exc-load-btn").onclick = loadExceptions;
document.getElementById("exc-download-btn").onclick = downloadExceptions;

document.querySelectorAll("#admin-subnav button").forEach(b => b.onclick = () => switchAdminSection(b.dataset.adminSection));

document.getElementById("toggle-user-form").onclick = () => document.getElementById("user-form").classList.toggle("hidden");
document.getElementById("user-form-save").onclick = createUser;

document.getElementById("toggle-role-form").onclick = () => openRoleForm(null);
document.getElementById("role-form-save").onclick = saveRole;
document.getElementById("role-form-cancel").onclick = () => document.getElementById("role-form").classList.add("hidden");

document.getElementById("toggle-branch-form").onclick = () => document.getElementById("branch-form").classList.toggle("hidden");
document.getElementById("admin-create-branch").onclick = createBranch;

document.getElementById("toggle-dtl-form").onclick = () => document.getElementById("dtl-form").classList.toggle("hidden");
document.getElementById("admin-create-dtl").onclick = createDtl;

document.getElementById("toggle-dsa-form").onclick = () => openDsaForm(null);
document.getElementById("dsa-form-save").onclick = saveDsa;
document.getElementById("dsa-form-cancel").onclick = () => document.getElementById("dsa-form").classList.add("hidden");
document.getElementById("dsa-form-branch").onchange = (e) => dsaFormLoadDtls(e.target.value || null, null);

populatePeriodSelects("bm-period-month", "bm-period-year");
populatePeriodSelects("bz-period-month", "bz-period-year");

const saved = localStorage.getItem("dsa_token");
if (saved) { state.token = saved; afterLogin().catch(() => logout()); }
