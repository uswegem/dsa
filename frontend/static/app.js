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
    flash(`<strong>Sign-in failed.</strong> ${e.message}`, "err", "login-flash");
  }
}

const ADMIN_SECTION_PERMS = ["MANAGE_USERS", "MANAGE_ROLES", "MANAGE_BRANCHES", "MANAGE_DSAS", "MANAGE_DTLS"];

const PAGE_META = {
  uploads: { crumb: "Commission · Data intake", title: "Uploads" },
  runs: { crumb: "Commission · Payouts", title: "Commission Runs" },
  exceptions: { crumb: "Commission · Review", title: "Exceptions" },
  admin: {
    users: { crumb: "Administration", title: "Users" },
    roles: { crumb: "Administration", title: "Roles" },
    branches: { crumb: "Administration", title: "Branches" },
    dsas: { crumb: "Administration", title: "DSAs" },
    dtls: { crumb: "Administration", title: "DTLs" },
  },
};

function setPageHeader(crumb, title) {
  document.getElementById("page-crumb").textContent = crumb;
  document.getElementById("page-title").textContent = title;
}

function initials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0] || "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

async function afterLogin() {
  state.user = await api("/api/auth/me");
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-screen").classList.remove("hidden");

  await loadBranches();

  const branchLabel = state.user.branch_id ? branchName(state.user.branch_id) : null;
  document.getElementById("userbox").innerHTML = `
    <div class="topbar-identity">
      <div class="name">${state.user.full_name}</div>
      <div class="subtitle">${state.user.role_name}${branchLabel ? " · " + branchLabel : ""}</div>
    </div>
    <div class="avatar-chip">${initials(state.user.full_name)}</div>
    <button id="logout-btn">Sign out</button>`;
  document.getElementById("logout-btn").onclick = logout;
  document.getElementById("page-scope").textContent = branchLabel || "All branches";
  document.getElementById("sidebar-today").textContent = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });

  document.getElementById("admin-nav-group").classList.toggle("hidden", !hasAnyPerm(ADMIN_SECTION_PERMS));
  document.querySelectorAll("#admin-subnav button").forEach(b => {
    b.classList.toggle("hidden", !hasPerm(b.dataset.perm));
  });

  await refreshUploads();
  await refreshRuns();
  refreshSidebarExceptionsPill();
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

function wireFileDrop(triggerId, inputId, nameId) {
  const trigger = document.getElementById(triggerId);
  const input = document.getElementById(inputId);
  const nameEl = document.getElementById(nameId);
  trigger.onclick = () => input.click();
  input.addEventListener("change", () => {
    nameEl.textContent = input.files.length ? input.files[0].name : "No file chosen";
  });
}

function countClass(n, positiveClass) {
  return n > 0 ? positiveClass : "count-zero";
}

// ---- Uploads ----
async function refreshUploads() {
  const uploads = await api("/api/uploads");
  const pill = document.getElementById("pill-uploads");
  pill.textContent = uploads.length || "";
  pill.dataset.count = uploads.length;

  const tbody = document.querySelector("#uploads-table tbody");
  tbody.innerHTML = uploads.map(u => `
    <tr data-id="${u.id}" class="clickable">
      <td class="id-col">${u.id}</td><td class="strong">${u.upload_type}</td><td>${u.branch_id ? branchName(u.branch_id) : "-"}</td>
      <td class="num">${u.period_year ? `${MONTH_NAMES[u.period_month - 1].slice(0,3)} ${u.period_year}` : "-"}</td>
      <td>${u.original_filename}</td>
      <td><span class="status-pill status-${u.status}">${u.status}</span></td>
      <td class="num">${u.rows_accepted}</td>
      <td class="num ${countClass(u.rows_rejected, "count-positive")}">${u.rows_rejected}</td>
      <td class="num ${countClass(u.warning_rows, "count-warning")}">${u.warning_rows}</td>
      <td class="muted" style="white-space:nowrap">${new Date(u.uploaded_at).toLocaleString()}</td>
    </tr>`).join("");
  tbody.querySelectorAll("tr[data-id]").forEach(row => {
    row.onclick = () => showUploadDetail(row.dataset.id);
  });
  document.getElementById("uploads-foot").textContent =
    uploads.length ? "click a row for accepted, rejected and warning detail" : "No uploads yet.";
}

async function showUploadDetail(id) {
  const u = await api(`/api/uploads/${id}`);
  renderUploadDetail(u, "rejected");
}

function exportRowsCsv(rows, filename) {
  const header = ["Row", "Severity", "Column", "Message"];
  const csvRows = [header, ...rows.map(e => [e.row_number ?? "", e.severity, e.column_name ?? "", (e.message || "").replace(/"/g, '""')])];
  const csv = csvRows.map(r => r.map(v => `"${v}"`).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function renderUploadDetail(u, activeTabKey) {
  const el = document.getElementById("upload-detail");
  const errors = u.errors || [];
  const rejected = errors.filter(e => e.severity === "ERROR");
  const warnings = errors.filter(e => e.severity === "WARNING");
  const periodLabel = u.period_year ? `${MONTH_NAMES[u.period_month - 1].slice(0, 3)} ${u.period_year}` : "-";

  const tabs = [
    { key: "rejected", label: `Rejected rows (${rejected.length})`, rows: rejected },
    { key: "warnings", label: `Warnings (${warnings.length})`, rows: warnings },
    { key: "accepted", label: `Accepted (${u.rows_accepted})`, rows: null },
  ];
  const active = tabs.find(t => t.key === activeTabKey) || tabs[0];

  let bodyHtml;
  if (active.key === "accepted") {
    bodyHtml = `<div style="padding:22px; color:#7A756A; font-size:13.5px;">Accepted rows aren't listed individually here - see the Accepted count above; they're stored in the branch/business records this upload updated.</div>`;
  } else if (active.rows.length === 0) {
    bodyHtml = `<div style="padding:22px; color:#7A756A; font-size:13.5px;">None.</div>`;
  } else {
    bodyHtml = `<div class="table-wrap"><table style="min-width:760px; margin-top:12px">
      <thead><tr><th>Row</th><th>Severity</th><th>Column</th><th>Message</th></tr></thead>
      <tbody>${active.rows.map(e => `<tr>
        <td class="id-col">${e.row_number || "(file/sheet)"}</td>
        <td><span class="badge severity-${e.severity}">${e.severity}</span></td>
        <td>${e.column_name ?? ""}</td>
        <td class="muted">${e.message}</td>
      </tr>`).join("")}</tbody>
    </table></div>`;
  }

  el.innerHTML = `
    <div class="panel" style="margin-top:20px">
      <div class="panel-head" style="border-bottom:2px solid rgba(20,19,16,0.4); align-items:flex-start;">
        <div>
          <div style="font-size:11px; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; color:#7A756A">Upload #${u.id} · ${u.upload_type} · ${periodLabel}</div>
          <h2 style="font-size:20px; margin-top:5px">${u.original_filename}</h2>
        </div>
        <button class="secondary" id="upload-detail-close">Close</button>
      </div>
      <div class="stat-strip">
        <div class="stat-cell"><div class="stat-label">Rows read</div><div class="stat-figure">${u.total_rows}</div></div>
        <div class="stat-cell success"><div class="stat-label">Accepted</div><div class="stat-figure">${u.rows_accepted}</div></div>
        <div class="stat-cell error"><div class="stat-label">Rejected</div><div class="stat-figure">${u.rows_rejected}</div></div>
        <div class="stat-cell warn"><div class="stat-label">Warnings</div><div class="stat-figure">${u.warning_rows}</div></div>
      </div>
      <div class="tabstrip">${tabs.map(t => `<button data-tab-key="${t.key}" class="${t.key === active.key ? "active" : ""}">${t.label}</button>`).join("")}</div>
      ${bodyHtml}
      <div class="panel-foot">
        <div>Rejected rows are not stored. Correct the sheet and re-upload - the period upserts, it will not duplicate.</div>
        <button class="secondary" id="upload-detail-export">Download rejected rows (.csv)</button>
      </div>
    </div>`;

  el.querySelectorAll("[data-tab-key]").forEach(btn => { btn.onclick = () => renderUploadDetail(u, btn.dataset.tabKey); });
  document.getElementById("upload-detail-close").onclick = () => { el.innerHTML = ""; };
  document.getElementById("upload-detail-export").onclick = () => exportRowsCsv(rejected, `upload_${u.id}_rejected_rows.csv`);
}

function submitSummary(u) {
  const parts = [`${u.rows_accepted} accepted (${u.rows_created} new, ${u.rows_updated} updated${u.rows_unchanged ? `, ${u.rows_unchanged} unchanged` : ""})`, `${u.rows_rejected} rejected`];
  if (u.warning_rows) parts.push(`${u.warning_rows} warning(s)`);
  return `Upload #${u.id}: ${u.status} - ${parts.join(", ")}`;
}

async function uploadBranchManagerFile() {
  const fileInput = document.getElementById("bm-file");
  if (!fileInput.files.length) return flash("Select an .xlsx or .xls file before uploading.", "err");
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
  if (!fileInput.files.length) return flash("Select an .xlsx or .xls file before uploading.", "err");
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
    if (r.status === "DRAFT") actions.push(`<button class="link" onclick="calcRun(${r.id})">Calculate</button>`);
    if (hasPerm("REVIEW_COMMISSION_RUN") && r.status === "DRAFT") actions.push(`<button class="link" onclick="reviewRun(${r.id})">Mark reviewed</button>`);
    if (hasPerm("LOCK_COMMISSION_RUN") && r.status === "REVIEWED") actions.push(`<button class="link" onclick="lockRun(${r.id})">Lock run</button>`);
    if (hasPerm("MARK_RUN_PAID") && r.status === "LOCKED") actions.push(`<button class="link" onclick="markPaidRun(${r.id})">Mark paid</button>`);
    actions.push(`<button class="link" onclick="downloadRun(${r.id})">Export .xlsx</button>`);
    return `<tr>
      <td class="id-col">${r.id}</td><td class="strong">${r.run_type}</td><td>${r.branch_id ? branchName(r.branch_id) : "All branches"}</td>
      <td class="num">${r.period}</td>
      <td><span class="status-pill status-${r.status}">${r.status}</span></td>
      <td><div class="action-links">${actions.join('<span class="sep">·</span>')}</div></td>
    </tr>`;
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
async function refreshSidebarExceptionsPill() {
  try {
    const rows = await api("/api/exceptions");
    const pill = document.getElementById("pill-exceptions");
    pill.textContent = rows.length || "";
    pill.dataset.count = rows.length;
  } catch (e) {}
}

async function loadExceptions() {
  const period = document.getElementById("exc-period").value.trim() || "";
  const branch_id = document.getElementById("exc-branch-select").value;
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  if (branch_id) params.set("branch_id", branch_id);
  const rows = await api(`/api/exceptions?${params.toString()}`);

  const counts = { UNMATCHED_IN_BUSINESS_FILE: 0, UNMATCHED_IN_BRANCH_FILE: 0, DUPLICATE: 0, MATCHED_WITH_WARNING: 0 };
  rows.forEach(r => { if (counts[r.match_status] !== undefined) counts[r.match_status]++; });
  document.getElementById("stat-unmatched-biz").textContent = counts.UNMATCHED_IN_BUSINESS_FILE;
  document.getElementById("stat-unmatched-branch").textContent = counts.UNMATCHED_IN_BRANCH_FILE;
  document.getElementById("stat-duplicates").textContent = counts.DUPLICATE;
  document.getElementById("stat-warnings").textContent = counts.MATCHED_WITH_WARNING;

  const tbody = document.querySelector("#exceptions-table tbody");
  tbody.innerHTML = rows.map(r => `<tr>
    <td><span class="badge match-${r.match_status}">${r.match_status}</span></td><td>${r.branch_name ?? ""}</td><td>${r.client_name ?? ""}</td>
    <td class="num ${r.client_account_no_branch ? "" : "count-positive"}">${r.client_account_no_branch ?? "—"}</td>
    <td class="num ${r.client_account_no_business ? "" : "count-positive"}">${r.client_account_no_business ?? "—"}</td>
    <td>${r.dsa_code ?? ""} ${r.dsa_name ?? ""}</td><td>${r.loan_type ?? ""}</td><td class="num" style="white-space:nowrap">${r.disbursement_date ?? ""}</td>
    <td class="muted">${r.notes ?? ""}</td></tr>`).join("");
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
  const meta = PAGE_META.admin[name];
  if (meta) setPageHeader(meta.crumb, meta.title);
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
    users.map(u => `<tr><td class="id-col">${u.id}</td><td>${u.email}</td><td class="strong">${u.full_name}</td>
      <td><span class="status-pill role-badge">${u.role_name}</span></td><td>${u.branch_id ? branchName(u.branch_id) : ""}</td></tr>`).join("");
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
    const chips = r.permissions.map(p => `<span class="perm-chip">${p}</span>`).join("");
    const actions = [`<button class="link" onclick="openRoleForm(${r.id})">Edit</button>`];
    if (!r.is_system_role) actions.push(`<button class="link" onclick="deleteRole(${r.id})">Delete</button>`);
    return `<tr><td class="strong" style="white-space:nowrap">${r.name}</td><td class="muted">${r.description ?? ""}</td>
      <td><div class="chip-row">${chips}</div></td>
      <td>${r.is_system_role ? "Yes" : "No"}</td><td style="white-space:nowrap">${actions.join(" ")}</td></tr>`;
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
    branches.map(b => `<tr><td class="id-col">${b.id}</td><td class="strong">${b.name}</td><td class="mono">${b.code ?? ""}</td></tr>`).join("");
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
    dtls.map(d => `<tr><td class="mono">${d.dtl_code}</td><td class="strong">${d.dtl_name}</td><td>${d.branch_id ? branchName(d.branch_id) : ""}</td></tr>`).join("");
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
    <tr><td class="mono">${d.dsa_code}</td><td class="strong">${d.dsa_name}</td><td>${d.branch_id ? branchName(d.branch_id) : ""}</td>
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
  document.querySelectorAll("#top-nav button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("hidden", t.id !== `tab-${name}`));
  if (name === "admin") {
    const first = firstVisibleAdminSection();
    if (first) switchAdminSection(first);
  } else {
    document.querySelectorAll("#admin-subnav button").forEach(b => b.classList.remove("active"));
    const meta = PAGE_META[name];
    if (meta) setPageHeader(meta.crumb, meta.title);
  }
}

document.getElementById("login-btn").onclick = login;
document.getElementById("login-password").addEventListener("keydown", e => { if (e.key === "Enter") login(); });
document.querySelectorAll("#top-nav button").forEach(b => b.onclick = () => switchTab(b.dataset.tab));
document.getElementById("bm-upload-btn").onclick = uploadBranchManagerFile;
document.getElementById("bz-upload-btn").onclick = uploadBusinessManagerFile;
document.getElementById("refresh-uploads").onclick = refreshUploads;
document.getElementById("create-run-btn").onclick = createRun;
document.getElementById("refresh-runs").onclick = refreshRuns;
document.getElementById("exc-load-btn").onclick = loadExceptions;
document.getElementById("exc-download-btn").onclick = downloadExceptions;

document.querySelectorAll("#admin-subnav button").forEach(b => b.onclick = () => { switchTab("admin"); switchAdminSection(b.dataset.adminSection); });

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

wireFileDrop("bm-file-trigger", "bm-file", "bm-file-name");
wireFileDrop("bz-file-trigger", "bz-file", "bz-file-name");

populatePeriodSelects("bm-period-month", "bm-period-year");
populatePeriodSelects("bz-period-month", "bz-period-year");

(function initLoginStats() {
  const now = new Date();
  const el = document.getElementById("login-stat-period");
  if (el) el.textContent = `${MONTH_NAMES[now.getMonth()]} ${now.getFullYear()}`;
})();

const saved = localStorage.getItem("dsa_token");
if (saved) { state.token = saved; afterLogin().catch(() => logout()); }
