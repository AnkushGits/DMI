(() => {
  let csrfToken = "";
  const generatedPasswords = new Set();
  let adminEmployeeOptionsCache = null;
  let adminAttendanceRecords = [];
  let adminAttendancePersonType = "student";
  let adminAssignmentRecords = [];

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body) headers.set("Content-Type", "application/json");
    if (csrfToken && options.method && options.method !== "GET") {
      headers.set("X-CSRF-Token", csrfToken);
    }

    const response = await fetch(`/api${path}`, {
      ...options,
      headers,
      credentials: "same-origin"
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const messages = {
        403: "You do not have permission to perform this action.",
        404: "The requested record was not found.",
        429: "Too many requests. Please try again shortly.",
        503: "Service temporarily unavailable. Please try again."
      };
      const message = response.status === 409
        ? result.error || "This action conflicts with an existing record."
        : response.status === 400
          ? result.error || "Please check the submitted information."
          : messages[response.status] || result.error || "The request could not be completed.";
      if (response.status === 401 && path !== "/auth/login") {
        const role = document.body.dataset.authRole;
        if (role) window.location.assign(`/${role}/login`);
      }
      throw new Error(message);
    }
    if (result.csrf_token) csrfToken = result.csrf_token;
    return result;
  }

  function attachDashboardNavigation() {
    const links = Array.from(document.querySelectorAll('aside nav a[href*="#"]'));
    const mobileToggle = document.querySelector("[data-mobile-nav-toggle]");
    const mobileBackdrop = document.querySelector("[data-mobile-nav-backdrop]");
    const sidebar = document.getElementById("dashboard-sidebar");
    const setMobileNavigation = (open) => {
      if (!sidebar || !mobileToggle || !mobileBackdrop) return;
      sidebar.classList.toggle("hidden", !open);
      if (open) sidebar.classList.add("fixed", "inset-y-0", "left-0", "z-40", "h-screen", "w-72", "shadow-2xl");
      else sidebar.classList.remove("fixed", "inset-y-0", "left-0", "z-40", "h-screen", "w-72", "shadow-2xl");
      mobileBackdrop.hidden = !open;
      mobileToggle.setAttribute("aria-expanded", String(open));
    };
    const activateCurrentSection = () => {
      const target = window.location.hash || "#overview";
      links.forEach((link) => {
        const linkHash = new URL(link.href, window.location.origin).hash || "#overview";
        const active = linkHash === target;
        link.classList.toggle("bg-brand-600", active);
        link.classList.toggle("font-semibold", active);
        link.classList.toggle("text-white", active);
        link.classList.toggle("text-slate-300", !active);
        link.setAttribute("aria-current", active ? "location" : "false");
      });
    };
    links.forEach((link) => {
      const targetHash = new URL(link.href, window.location.origin).hash;
      const id = targetHash.replace(/^#/, "");
      if (!id || !document.getElementById(id)) {
        link.setAttribute("aria-disabled", "true");
        link.classList.add("pointer-events-none", "opacity-50");
      }
      link.addEventListener("click", () => {
        const nextSectionId = new URL(link.href, window.location.origin).hash.replace(/^#/, "");
        const target = document.getElementById(nextSectionId);
        if (!target) return;
        target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
        setMobileNavigation(false);
      });
    });
    mobileToggle?.addEventListener("click", () => {
      setMobileNavigation(mobileToggle.getAttribute("aria-expanded") !== "true");
    });
    mobileBackdrop?.addEventListener("click", () => setMobileNavigation(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setMobileNavigation(false);
    });
    window.addEventListener("hashchange", activateCurrentSection);
    activateCurrentSection();
  }

  function setText(selector, value) {
    document.querySelectorAll(selector).forEach((element) => {
      element.textContent = value == null || value === "" ? "—" : value;
    });
  }

  function renderAnnouncements(items) {
    const list = document.querySelector("[data-announcements]");
    if (!list) return;
    list.replaceChildren();
    if (!items || !items.length) {
      const empty = document.createElement("li");
      empty.className = "rounded-2xl bg-slate-50 p-3 border border-slate-200";
      empty.textContent = "No announcements yet.";
      list.append(empty);
      return;
    }
    items.forEach((item) => {
      const entry = document.createElement("li");
      entry.className = "rounded-2xl bg-slate-50 p-3 border border-slate-200";
      entry.textContent = `${item.title}: ${item.body}`;
      list.append(entry);
    });
  }

  // --- Attendance form: create-or-update -----------------------------------

function attendanceFormState() {
    const form = document.querySelector('[data-admin-form="attendance"]');
    if (!form) return null;
    const personType = form.dataset.personType || "student";
    return {
      form,
      personType,
      personId: form.querySelector(`[data-person-id="${personType}"]`)?.value || "",
      courseId: form.querySelector('[data-person-id="course"]')?.value || "",
      date: form.elements.date.value
    };
  }

  function setAttendanceSubmitLabel(mode, label) {
    const button = document.querySelector('[data-admin-form="attendance"] [type="submit"]');
    if (button) button.textContent = label || (mode === "update" ? "Update Attendance" : "Save Attendance");
  }

  function announceExistingRecord(state, record) {
    const notice = state.form.querySelector("[data-attendance-existing]");
    if (!notice) return;
    notice.classList.remove("hidden");
    notice.textContent = record
      ? `Existing attendance found for ${state.date}. Current status: ${record.status}. Saving will update this record.`
      : "No attendance recorded yet for this person and date. Saving will create a new record.";
  }

  async function refreshAttendanceContext() {
    const state = attendanceFormState();
    if (!state) return;
    const existing = state.form.querySelector("[data-attendance-existing]");
    existing?.classList.add("hidden");
    if (!state.personId || !state.date) {
      setAttendanceSubmitLabel("create");
      return;
    }
    if (state.personType === "student" && !state.courseId) {
      setAttendanceSubmitLabel("create");
      return;
    }
    const params = new URLSearchParams({
      person_type: state.personType,
      person_id: state.personId,
      date: state.date
    });
    if (state.courseId) params.set("course_id", state.courseId);
    try {
      const result = await api(`/admin/attendance/lookup?${params}`);
      if (result.found) {
        state.form.dataset.recordId = result.record.id;
        state.form.elements.status.value = result.record.status;
        state.form.elements.remarks.value = result.record.remarks || "";
        setAttendanceSubmitLabel("update", "Update Attendance");
        announceExistingRecord(state, result.record);
      } else {
        delete state.form.dataset.recordId;
        setAttendanceSubmitLabel("create");
      }
    } catch {
      delete state.form.dataset.recordId;
      setAttendanceSubmitLabel("create");
    }
    await loadAttendanceReport(state);
  }

  async function loadAttendanceReport(state) {
    const panel = state.form.querySelector("[data-attendance-report]");
    if (!panel) return;
    if (!state.personId) {
      panel.classList.add("hidden");
      return;
    }
    const params = new URLSearchParams({ person_type: state.personType, person_id: state.personId });
    if (state.courseId) params.set("course_id", state.courseId);
    try {
      const { report } = await api(`/admin/attendance/report?${params}`);
      panel.classList.remove("hidden");
      panel.textContent = [
        `${report.full_name} (${report.code})`,
        `Total ${report.total} · Present ${report.present} · Absent ${report.absent} · Leave ${report.leave} · Late ${report.late}`,
        `Attendance: ${report.percentage}%`
      ].join(" — ");
    } catch {
      panel.classList.add("hidden");
    }
  }

  function attachAttendancePersonType() {
    const form = document.querySelector('[data-admin-form="attendance"]');
    if (!form) return;
    form.querySelectorAll("[data-person-type-option]").forEach((radio) => {
      radio.addEventListener("change", () => {
        if (!radio.checked) return;
        const personType = radio.value;
        form.dataset.personType = personType;
        form.querySelector('[data-person-search="student"]').classList.toggle("hidden", personType !== "student");
        form.querySelector('[data-person-search="employee"]').classList.toggle("hidden", personType !== "employee");
        form.querySelector("[data-course-field]").classList.toggle("hidden", personType !== "student");
        // 'half day' is an employee-only status in this institute.
        form.querySelectorAll("[data-employee-only]").forEach((option) => {
          option.hidden = personType !== "employee";
        });
        if (personType === "student" && form.elements.status.value === "half_day") {
          form.elements.status.value = "present";
        }
        clearSearchSelection(personType === "employee" ? "student" : "employee");
        clearSearchSelection("course");
        // The other person's record does not carry over, so drop any edit target
        // and return the button to its create label.
        delete form.dataset.recordId;
        setAttendanceSubmitLabel("create");
        form.querySelector("[data-attendance-report]")?.classList.add("hidden");
        announceExistingRecord(attendanceFormState(), null);
      });
    });
  }

  function renderRows(selector, rows, columns) {
    const body = document.querySelector(selector);
    if (!body) return;
    body.replaceChildren();
    if (!rows.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = columns.length;
      cell.className = "px-4 py-3 text-slate-500";
      cell.textContent = "No records available.";
      row.append(cell);
      body.append(row);
      return;
    }
    rows.forEach((record) => {
      const row = document.createElement("tr");
      row.className = "border-t border-slate-100";
      columns.forEach((column) => {
        const cell = document.createElement("td");
        cell.className = "px-4 py-3";
        const value = column(record);
        if (value instanceof Node) cell.append(value);
        else cell.textContent = value == null || value === "" ? "—" : value;
        row.append(cell);
      });
      body.append(row);
    });
  }

  // --- Universal database-backed search / autocomplete ---------------------
  //
  // One component, reused everywhere a person or course must be picked. It never
  // loads a full list into the browser: every keystroke schedules a debounced
  // request to a limited, parameterized endpoint.
  const SEARCH_DEBOUNCE_MS = 300;

  const SEARCH_ENDPOINTS = {
    student: "/admin/search/students",
    "fee-student": "/admin/search/students",
    "result-student": "/admin/search/students",
    employee: "/admin/search/employees",
    course: "/admin/search/courses",
    "assignment-course": "/admin/search/courses"
  };

  const SEARCH_LABELS = {
    student: (item) => [
      item.full_name,
      item.student_id,
      item.course_name || item.email || item.phone || ""
    ],
    "fee-student": (item) => [
      item.full_name,
      item.student_id,
      item.course_name || item.email || item.phone || ""
    ],
    "result-student": (item) => [
      item.full_name,
      item.student_id,
      item.course_name || item.email || item.phone || ""
    ],
    employee: (item) => [
      item.full_name,
      item.employee_id,
      [item.designation, item.department].filter(Boolean).join(" · ") || item.email || ""
    ],
    course: (item) => [item.name, item.course_code, ""],
    "assignment-course": (item) => [item.name, item.course_code, ""]
  };

  const SEARCH_CODE_FIELD = {
    student: "student_id", "fee-student": "student_id", "result-student": "student_id",
    employee: "employee_id", course: "course_code", "assignment-course": "course_code"
  };

  function searchWidgetElements(key) {
    return {
      input: document.querySelector(`[data-person-search-input="${key}"]`),
      results: document.querySelector(`[data-person-search-results="${key}"]`),
      selected: document.querySelector(`[data-person-selected="${key}"]`),
      hidden: document.querySelector(`[data-person-id="${key}"]`)
    };
  }

  function renderSearchSelection(key, item) {
    const parts = searchWidgetElements(key);
    if (!parts.selected || !parts.hidden) return;
    parts.hidden.value = item.id;
    parts.input.classList.add("hidden");
    parts.selected.classList.remove("hidden");
    const [name, code, meta] = SEARCH_LABELS[key](item);
    const nameEl = parts.selected.querySelector("[data-selected-name]");
    const codeEl = parts.selected.querySelector("[data-selected-code]");
    const metaEl = parts.selected.querySelector("[data-selected-meta]");
    if (nameEl) nameEl.textContent = name || "";
    if (codeEl) codeEl.textContent = code ? `ID: ${code}` : "";
    if (metaEl) metaEl.textContent = meta || "";
    parts.results?.classList.add("hidden");
    document.dispatchEvent(new CustomEvent("person:selected", { detail: { key, item } }));
  }

  function clearSearchSelection(key) {
    const parts = searchWidgetElements(key);
    if (!parts.selected || !parts.hidden) return;
    parts.hidden.value = "";
    parts.selected.classList.add("hidden");
    parts.input?.classList.remove("hidden");
    if (parts.input) parts.input.value = "";
    parts.results?.classList.add("hidden");
    document.dispatchEvent(new CustomEvent("person:selected", { detail: { key, item: null } }));
  }

  function setSearchSelection(key, item) {
    if (item) renderSearchSelection(key, item);
    else clearSearchSelection(key);
  }

  async function runSearch(key, term) {
    const parts = searchWidgetElements(key);
    if (!parts.input || !parts.results) return;
    const endpoint = SEARCH_ENDPOINTS[key];
    if (!endpoint) return;
    // Tag this request so a slower earlier one cannot overwrite newer results.
    const requestId = Number(parts.input.dataset.requestId || 0) + 1;
    parts.input.dataset.requestId = String(requestId);
    parts.results.replaceChildren();
    try {
      const payload = await api(`${endpoint}?q=${encodeURIComponent(term)}`);
      if (parts.input.dataset.requestId !== String(requestId)) return;
      const items = payload.students || payload.employees || payload.courses || [];
      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "px-3 py-2 text-xs text-slate-500";
        empty.textContent = "No matching records.";
        parts.results.append(empty);
      } else {
        items.forEach((item) => {
          const [name, code, meta] = SEARCH_LABELS[key](item);
          const option = document.createElement("li");
          option.role = "option";
          option.className = "cursor-pointer border-b border-slate-100 px-3 py-2 text-xs last:border-0 hover:bg-brand-50";
          const nameEl = document.createElement("p");
          nameEl.className = "font-semibold text-slate-900";
          nameEl.textContent = name || "";
          const codeEl = document.createElement("p");
          codeEl.className = "text-slate-600";
          codeEl.textContent = code || "";
          const metaEl = document.createElement("p");
          metaEl.className = "text-slate-500";
          metaEl.textContent = meta || "";
          option.append(nameEl, codeEl, metaEl);
          option.addEventListener("click", () => renderSearchSelection(key, item));
          parts.results.append(option);
        });
      }
      parts.results.classList.remove("hidden");
    } catch (error) {
      parts.results.replaceChildren();
      const failed = document.createElement("li");
      failed.className = "px-3 py-2 text-xs text-red-600";
      failed.textContent = error.message;
      parts.results.append(failed);
      parts.results.classList.remove("hidden");
    }
  }

  function attachPersonSearch(key) {
    const parts = searchWidgetElements(key);
    if (!parts.input || parts.input.dataset.searchBound) return;
    parts.input.dataset.searchBound = "true";
    let timer;
    parts.input.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => runSearch(key, parts.input.value.trim()), SEARCH_DEBOUNCE_MS);
    });
    parts.input.addEventListener("focus", () => runSearch(key, parts.input.value.trim()));
    document.querySelector(`[data-person-change="${key}"]`)?.addEventListener("click", () => {
      clearSearchSelection(key);
      searchWidgetElements(key).input?.focus();
    });
  }

  function attachPersonSearches() {
    Object.keys(SEARCH_ENDPOINTS).forEach(attachPersonSearch);
  }

  function resourceLink(value) {
    try {
      const target = new URL(value);
      if (!["https:", "http:"].includes(target.protocol)) return "Resource unavailable";
      const link = document.createElement("a");
      link.href = target.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = "font-semibold text-brand-700 underline";
      link.textContent = "Open material";
      return link;
    } catch {
      return "Resource unavailable";
    }
  }

  function assignmentStatus(dueDate) {
    if (!dueDate) return "Pending";
    const due = new Date(`${String(dueDate).slice(0, 10)}T00:00:00`);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return due < today ? "Overdue" : "Pending";
  }

  function assignmentDetailsButton(assignment) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "font-semibold text-brand-700 underline";
    button.textContent = "View Details";
    button.addEventListener("click", () => {
      const { overlay, panel } = makeModal(assignment.title, assignment.description || "No description provided.");
      const details = document.createElement("p");
      details.className = "mt-4 text-sm text-slate-600";
      details.textContent = `Course: ${assignment.course_name || "—"} · Due: ${assignment.due_date || "No due date"} · Status: ${assignmentStatus(assignment.due_date)}`;
      panel.append(details);
      if (assignment.attachment) {
        const link = resourceLink(assignment.attachment);
        if (link instanceof HTMLAnchorElement) {
          link.textContent = "Open attachment";
          link.classList.add("mt-4", "inline-block");
          panel.append(link);
        }
      }
      const close = document.createElement("button");
      close.type = "button";
      close.className = "mt-5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-bold text-white";
      close.textContent = "Close";
      close.addEventListener("click", () => overlay.remove());
      panel.append(close);
    });
    return button;
  }

  function setStatus(form, message, isError = true) {
    const status = form.querySelector("[data-login-status], [data-form-status]");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("text-red-600", isError);
    status.classList.toggle("text-brand-700", !isError);
  }

  function passwordError(password) {
    if (password.length < 8 || password.length > 128) return "Password must be between 8 and 128 characters.";
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      return "Password must contain at least one letter and one number.";
    }
    return "";
  }

  function makeModal(title, description) {
    const overlay = document.createElement("div");
    overlay.className = "fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/60 p-4";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", title);
    const panel = document.createElement("section");
    panel.className = "w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl";
    const heading = document.createElement("h2");
    heading.className = "font-heading text-2xl font-extrabold text-slate-900";
    heading.textContent = title;
    const intro = document.createElement("p");
    intro.className = "mt-2 text-sm text-slate-600";
    intro.textContent = description;
    panel.append(heading, intro);
    overlay.append(panel);
    document.body.append(overlay);
    return { overlay, panel };
  }

  function showCredentialModal({ name, loginId, password, role, title }) {
    const { overlay, panel } = makeModal(title || "Account created successfully", "Save these credentials securely. The password cannot be retrieved later.");
    const details = document.createElement("dl");
    details.className = "mt-5 grid gap-3 rounded-xl bg-slate-50 p-4 text-sm";
    [[`${role} name`, name], ["Login ID", loginId], ["Temporary password", password], ["Role", role]].forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "grid grid-cols-[10rem_1fr] gap-2";
      const term = document.createElement("dt");
      term.className = "font-semibold text-slate-500";
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.className = "break-all font-semibold text-slate-900";
      detail.textContent = value;
      row.append(term, detail);
      details.append(row);
    });
    const status = document.createElement("p");
    status.className = "min-h-5 text-sm";
    status.setAttribute("role", "status");
    const actions = document.createElement("div");
    actions.className = "mt-5 flex flex-wrap gap-2";
    const copyButton = (label, value) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "rounded-lg border border-brand-600 px-3 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50";
      button.textContent = label;
      button.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(value);
          status.textContent = `${label.replace("Copy ", "")} copied.`;
          status.className = "min-h-5 text-sm text-brand-700";
        } catch {
          status.textContent = "Clipboard access failed. Select and copy the credential manually.";
          status.className = "min-h-5 text-sm text-red-600";
        }
      });
      return button;
    };
    const print = document.createElement("button");
    print.type = "button";
    print.className = "rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50";
    print.textContent = "Print Credentials";
    print.addEventListener("click", () => {
      let printStyle = document.getElementById("credential-print-style");
      if (!printStyle) {
        printStyle = document.createElement("style");
        printStyle.id = "credential-print-style";
        printStyle.textContent = "@media print { body * { visibility: hidden !important; } body > div[role='dialog'], body > div[role='dialog'] * { visibility: visible !important; } body > div[role='dialog'] { position: absolute !important; inset: 0 !important; background: white !important; } body > div[role='dialog'] button, body > div[role='dialog'] [role='status'] { display: none !important; } }";
        document.head.append(printStyle);
      }
      window.print();
    });
    const close = document.createElement("button");
    close.type = "button";
    close.className = "ml-auto rounded-lg bg-brand-600 px-4 py-2 text-sm font-bold text-white hover:bg-brand-700";
    close.textContent = "Done";
    close.addEventListener("click", () => overlay.remove());
    actions.append(copyButton("Copy Login ID", loginId), copyButton("Copy Password", password), print, close);
    panel.append(details, status, actions);
  }

  function showPasswordChange(required = false) {
    const { overlay, panel } = makeModal(
      required ? "Change your temporary password" : "Change password",
      required
        ? "A password change is required before you can use the portal."
        : "Use at least 8 characters, including at least one letter and one number. Forgot your password? Contact the institute administrator."
    );
    const form = document.createElement("form");
    form.className = "mt-5 grid gap-3";
    const inputs = [
      ["current_password", "Current password"],
      ["new_password", "New password"],
      ["confirm_password", "Confirm new password"]
    ];
    inputs.forEach(([name, label]) => {
      const input = document.createElement("input");
      input.name = name;
      input.type = "password";
      input.autocomplete = name === "current_password" ? "current-password" : "new-password";
      input.required = true;
      input.minLength = name === "current_password" ? 1 : 8;
      input.maxLength = 128;
      input.placeholder = label;
      input.setAttribute("aria-label", label);
      input.className = "rounded-lg border-slate-300 text-sm";
      form.append(input);
    });
    const status = document.createElement("p");
    status.className = "min-h-5 text-sm";
    status.setAttribute("role", "status");
    const actions = document.createElement("div");
    actions.className = "flex justify-end gap-2";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "rounded-lg bg-brand-600 px-4 py-2 text-sm font-bold text-white hover:bg-brand-700";
    submit.textContent = "Save password";
    actions.append(submit);
    if (!required) {
      const close = document.createElement("button");
      close.type = "button";
      close.className = "rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold";
      close.textContent = "Cancel";
      close.addEventListener("click", () => overlay.remove());
      actions.prepend(close);
    }
    form.append(status, actions);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const current = form.elements.current_password.value;
      const password = form.elements.new_password.value;
      const confirmation = form.elements.confirm_password.value;
      const invalid = passwordError(password);
      if (invalid) {
        status.textContent = invalid;
        status.className = "min-h-5 text-sm text-red-600";
        return;
      }
      if (password !== confirmation) {
        status.textContent = "Passwords do not match.";
        status.className = "min-h-5 text-sm text-red-600";
        return;
      }
      submit.disabled = true;
      status.textContent = "Saving password…";
      status.className = "min-h-5 text-sm text-slate-600";
      try {
        await api("/auth/change-password", {
          method: "POST",
          body: JSON.stringify({ current_password: current, new_password: password, confirm_password: confirmation })
        });
        overlay.remove();
        if (required) {
          await loadDashboard();
        } else {
          const dashboardStatus = document.querySelector("[data-dashboard-status]");
          if (dashboardStatus) dashboardStatus.textContent = "Password changed successfully.";
        }
      } catch (error) {
        status.textContent = error.message;
        status.className = "min-h-5 text-sm text-red-600";
        submit.disabled = false;
      }
    });
    panel.append(form);
    form.elements.current_password.focus();
  }

  function attachPasswordChangeButtons() {
    document.querySelectorAll("[data-password-security]").forEach((button) => {
      button.addEventListener("click", () => showPasswordChange(false));
    });
  }

  function attachProfileForms() {
    document.querySelectorAll("[data-profile-form]").forEach((form) => {
      const fields = ["phone", "email", "address"];
      const editButton = form.querySelector("[data-profile-edit]");
      const cancelButton = form.querySelector("[data-profile-cancel]");
      const saveButton = form.querySelector('[type="submit"]');
      const setEditing = (editing) => {
        fields.forEach((field) => { form.elements[field].disabled = !editing; });
        editButton.hidden = editing;
        cancelButton.hidden = !editing;
        saveButton.hidden = !editing;
      };
      editButton?.addEventListener("click", () => setEditing(true));
      cancelButton?.addEventListener("click", () => {
        const original = JSON.parse(form.dataset.profileOriginal || "{}");
        fields.forEach((field) => { form.elements[field].value = original[field] || ""; });
        setEditing(false);
        setStatus(form, "Changes discarded.", false);
      });
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        saveButton.disabled = true;
        setStatus(form, "Saving profile…", false);
        const values = Object.fromEntries(new FormData(form).entries());
        try {
          await api("/portal/profile", { method: "PUT", body: JSON.stringify(values) });
          const { profile } = await api("/portal/profile");
          fields.forEach((field) => {
            form.elements[field].value = profile[field] || "";
          });
          form.dataset.profileOriginal = JSON.stringify(profile);
          setText("[data-user-phone]", profile.phone);
          setText("[data-user-email]", profile.email);
          setEditing(false);
          setStatus(form, "Profile updated successfully.", false);
        } catch (error) {
          setStatus(form, error.message);
        } finally {
          saveButton.disabled = false;
        }
      });
      setEditing(false);
    });
  }

  async function attachLogin() {
    const form = document.querySelector("form[data-auth-role]");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      button.disabled = true;
      setStatus(form, "Signing in…", false);
      try {
        const result = await api("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            identifier: form.elements.identifier.value.trim(),
            password: form.elements.password.value,
            role: form.dataset.authRole
          })
        });
        csrfToken = result.csrf_token;
        const target = {
          admin: "/admin/dashboard",
          student: "/student/dashboard",
          employee: "/employee/dashboard"
        }[result.user.role];
        window.location.assign(target);
      } catch (error) {
        setStatus(form, error.message);
      } finally {
        button.disabled = false;
      }
    });
  }

  async function attachLogout() {
    document.querySelectorAll("[data-logout]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await api("/auth/logout", { method: "POST", body: "{}" });
        } catch (error) {
          button.disabled = false;
          const status = document.querySelector("[data-dashboard-status]");
          if (status) status.textContent = error.message;
          return;
        }
        window.location.assign("/");
      });
    });
  }

  async function loadDashboard() {
    const body = document.body;
    const expectedRole = body.dataset.authRole;
    if (!expectedRole) return;
    const loginPage = {
      admin: "/admin/login",
      student: "/student/login",
      employee: "/employee/login"
    }[expectedRole];
    try {
      const session = await api("/auth/me");
      if (session.user.role !== expectedRole) {
        window.location.assign({
          admin: "/admin/dashboard",
          student: "/student/dashboard",
          employee: "/employee/dashboard"
        }[session.user.role]);
        return;
      }
      setText("[data-user-name]", session.user.profile?.full_name);
      setText("[data-user-role]", expectedRole[0].toUpperCase() + expectedRole.slice(1));
      setText("[data-user-phone]", session.user.profile?.phone);
      setText("[data-user-email]", session.user.profile?.email);
      setText("[data-account-id]", session.user.profile?.account_id || session.user.login_id);
      if (session.user.must_change_password) {
        showPasswordChange(true);
        return;
      }

      const data = await api(expectedRole === "admin" ? "/admin/dashboard" : "/portal/overview");
      const profileForm = document.querySelector("[data-profile-form]");
      if (profileForm && data.profile) {
        ["phone", "email", "address"].forEach((field) => {
          profileForm.elements[field].value = data.profile[field] || "";
        });
        profileForm.dataset.profileOriginal = JSON.stringify(data.profile);
      }
      if (expectedRole === "student") {
        const courseName = data.course?.name || "Not assigned";
        setText("[data-course-name]", courseName);
        setText("[data-course-duration]", data.course?.duration_months ? `${data.course.duration_months} months` : "");
        setText("[data-course-instructor]", data.course?.instructor_name);
        setText("[data-course-start-date]", data.course?.start_date);
        setText("[data-admission-date]", data.profile.admission_date);
        setText("[data-account-status]", data.profile.status);
        setText("[data-attendance-percent]", data.attendance.percentage);
        setText("[data-attendance-summary]", `Present: ${data.attendance.present} / ${data.attendance.total} classes`);
        setText("[data-assignment-count]", data.assignment_count);
        setText("[data-fees-due]", `₹${Number(data.fees.due || 0).toLocaleString("en-IN")}`);
        setText("[data-fees-status]", data.fees.due ? "Amount remaining" : "No outstanding balance");
        renderAnnouncements(data.announcements);
        const [attendance, assignments, materials, fees, results] = await Promise.all([
          api("/portal/attendance"),
          api("/portal/assignments"),
          api("/portal/materials"),
          api("/portal/fees"),
          api("/portal/results")
        ]);
        renderRows("[data-student-attendance]", attendance.attendance, [
          (item) => item.attendance_date, (item) => item.course_name, (item) => item.status, (item) => item.remarks
        ]);
        renderRows("[data-student-assignments]", assignments.assignments, [
          (item) => item.title,
          (item) => item.course_name,
          (item) => item.due_date,
          (item) => assignmentStatus(item.due_date),
          (item) => assignmentDetailsButton(item)
        ]);
        renderRows("[data-student-materials]", materials.materials, [
          (item) => item.title,
          (item) => item.course_name,
          (item) => resourceLink(item.file_url)
        ]);
        const money = (value) => `₹${Number(value || 0).toLocaleString("en-IN")}`;
        renderRows("[data-student-fees]", fees.fees, [
          (item) => item.course_name, (item) => money(item.amount), (item) => money(item.paid_amount),
          (item) => money(item.due_amount), (item) => item.payment_status
        ]);
        renderRows("[data-student-results]", results.results, [
          (item) => item.subject, (item) => item.course_name, (item) => item.marks, (item) => item.grade
        ]);
      } else if (expectedRole === "employee") {
        setText("[data-user-designation]", data.profile.designation);
        setText("[data-account-status]", data.profile.status);
        setText("[data-assigned-students]", data.assigned_students);
        setText("[data-assigned-courses]", data.assigned_courses);
        setText("[data-assignment-count]", data.assignments);
        setText("[data-announcement-count]", data.announcements.length);
        renderAnnouncements(data.announcements);
        await loadEmployeeWorkspace();
      }
      const status = document.querySelector("[data-dashboard-status]");
      if (status) status.textContent = "";
    } catch (error) {
      if (/Authentication|required|session/i.test(error.message)) {
        window.location.assign(loginPage);
        return;
      }
      const status = document.querySelector("[data-dashboard-status]");
      if (status) status.textContent = error.message;
      else if (error.message.includes("not authorized")) window.location.assign(loginPage);
    }
  }

  async function loadEmployeeStudents() {
    const params = new URLSearchParams({
      search: document.querySelector("[data-employee-student-search]")?.value || "",
      course_id: document.querySelector("[data-employee-course-filter]")?.value || ""
    });
    const { students } = await api(`/portal/students?${params}`);
    renderRows("[data-employee-students]", students, [
      (item) => item.student_id, (item) => item.full_name, (item) => item.course_name, (item) => item.phone,
      (item) => item.status, (item) => `${item.attendance_percentage}% (${item.attendance_present}/${item.attendance_total})`
    ]);
  }

  function attachEmployeeStudentFilters() {
    const search = document.querySelector("[data-employee-student-search]");
    const course = document.querySelector("[data-employee-course-filter]");
    let timer;
    search?.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => loadEmployeeStudents().catch(showDashboardError), 250);
    });
    course?.addEventListener("change", () => loadEmployeeStudents().catch(showDashboardError));
  }

  async function loadEmployeeWorkspace() {
    const [courses, assignments, materials, announcements, attendance] = await Promise.all([
      api("/portal/courses"),
      api("/portal/assignments"),
      api("/portal/materials"),
      api("/portal/announcements"),
      api("/portal/attendance")
    ]);
    document.querySelectorAll("[data-portal-courses]").forEach((select) => {
      const optional = select.name === "course_id" && select.closest('[data-portal-form="announcements"]');
      const selected = select.value;
      select.replaceChildren();
      if (optional) select.add(new Option("All assigned courses", ""));
      else select.add(new Option("Select course", ""));
      courses.courses.forEach((course) => select.add(new Option(course.name, course.id)));
      select.value = selected;
    });
    const courseFilter = document.querySelector("[data-employee-course-filter]");
    if (courseFilter) {
      const selected = courseFilter.value;
      courseFilter.replaceChildren(new Option("All assigned courses", ""));
      courses.courses.forEach((item) => courseFilter.add(new Option(item.name, item.id)));
      courseFilter.value = selected;
    }
    await loadEmployeeStudents();
    renderRows("[data-employee-attendance]", attendance.attendance, [
      (item) => item.attendance_date, (item) => item.status, (item) => item.remarks
    ]);
    renderRows("[data-employee-assignment-list]", assignments.assignments, [
      (item) => item.title, (item) => item.course_name, (item) => item.due_date
    ]);
    renderRows("[data-employee-material-list]", materials.materials, [
      (item) => item.title, (item) => item.course_name, (item) => resourceLink(item.file_url)
    ]);
    renderAnnouncements(announcements.announcements);
    const employeeAnnouncements = document.querySelector("[data-employee-announcement-list]");
    if (employeeAnnouncements) {
      employeeAnnouncements.replaceChildren();
      announcements.announcements.forEach((announcement) => {
        const item = document.createElement("li");
        item.className = "rounded-2xl bg-slate-50 p-3 border border-slate-200";
        item.textContent = `${announcement.title}: ${announcement.body}`;
        employeeAnnouncements.append(item);
      });
      if (!announcements.announcements.length) {
        const item = document.createElement("li");
        item.className = "rounded-2xl bg-slate-50 p-3 border border-slate-200";
        item.textContent = "No announcements yet.";
        employeeAnnouncements.append(item);
      }
    }
  }

  async function loadAdminDashboard() {
    if (document.body.dataset.authRole !== "admin") return;
    const stats = await api("/admin/dashboard");
    Object.entries(stats.stats).forEach(([key, value]) => setText(`[data-admin-stat="${key}"]`, value));
    await Promise.all([
      loadAdminStudents(),
      loadAdminEmployees(),
      loadAdminCourses(),
      loadAdminOperations()
    ]);
  }

  async function loadAdminStudents() {
    const list = document.querySelector("[data-admin-students]");
    if (!list) return;
    const params = new URLSearchParams({
      search: document.querySelector('[data-admin-search="students"]')?.value || "",
      status: document.querySelector('[data-admin-status-filter="students"]')?.value || "",
      course_id: document.querySelector('[data-admin-course-filter="students"]')?.value || ""
    });
    const { students } = await api(`/admin/students?${params}`);
    list.replaceChildren();
    students.forEach((student) => {
      const row = document.createElement("tr");
      row.className = "border-t border-slate-100";
      [student.student_id, student.full_name, student.course_name || "—", student.phone || "—", student.status].forEach((value) => {
        const cell = document.createElement("td");
        cell.className = "px-4 py-3";
        cell.textContent = value;
        row.append(cell);
      });
      const actions = document.createElement("td");
      actions.className = "px-4 py-3";
      actions.append(
        actionButton("Edit", "edit-student", student.id),
        actionButton(student.status === "active" ? "Deactivate" : "Activate", "toggle-student", student.id),
        actionButton("Reset password", "reset-student", student.id),
        actionButton("Permanently delete", "delete-student", student.id)
      );
      row.append(actions);
      list.append(row);
    });
  }

  async function loadAdminEmployees() {
    const list = document.querySelector("[data-admin-employees]");
    if (!list) return;
    const params = new URLSearchParams({
      search: document.querySelector('[data-admin-search="employees"]')?.value || "",
      status: document.querySelector('[data-admin-status-filter="employees"]')?.value || "",
      course_id: document.querySelector('[data-admin-course-filter="employees"]')?.value || ""
    });
    const { employees } = await api(`/admin/employees?${params}`);
    if (!adminEmployeeOptionsCache) {
      adminEmployeeOptionsCache = (await api("/admin/employees?status=active")).employees;
    }
    document.querySelectorAll("[data-employee-options]").forEach((select) => {
      const current = select.value;
      select.replaceChildren(new Option("Assign instructor (optional)", ""));
      adminEmployeeOptionsCache.forEach((employee) => {
        select.add(new Option(`${employee.employee_id} — ${employee.full_name}`, employee.id));
      });
      select.value = current;
    });
    list.replaceChildren();
    employees.forEach((employee) => {
      const row = document.createElement("tr");
      row.className = "border-t border-slate-100";
      [employee.employee_id, employee.full_name, employee.designation || "—", employee.phone || "—", employee.status].forEach((value) => {
        const cell = document.createElement("td");
        cell.className = "px-4 py-3";
        cell.textContent = value;
        row.append(cell);
      });
      const actions = document.createElement("td");
      actions.className = "px-4 py-3";
      actions.append(
        actionButton("Edit", "edit-employee", employee.id),
        actionButton(employee.status === "active" ? "Deactivate" : "Activate", "toggle-employee", employee.id),
        actionButton("Reset password", "reset-employee", employee.id),
        actionButton("Permanently delete", "delete-employee", employee.id)
      );
      row.append(actions);
      list.append(row);
    });
  }

  async function loadAdminCourses() {
    const selects = document.querySelectorAll("[data-course-options]");
    const { courses } = await api("/admin/courses");
    document.querySelectorAll("[data-admin-course-filter]").forEach((select) => {
      const current = select.value;
      select.replaceChildren(new Option("All courses", ""));
      courses.forEach((course) => {
        select.add(new Option(course.name, course.id));
      });
      select.value = current;
    });
    document.querySelectorAll('[data-attendance-filter="course_id"]').forEach((select) => {
      const current = select.value;
      select.replaceChildren(new Option("All courses", ""));
      courses.forEach((course) => select.add(new Option(course.name, course.id)));
      select.value = current;
    });
    selects.forEach((select) => {
      const current = select.multiple
        ? Array.from(select.selectedOptions, (option) => option.value)
        : select.value;
      select.replaceChildren();
      if (!select.multiple) select.add(new Option("Select course", ""));
      courses.filter((course) => course.status === "active").forEach((course) => {
        const option = new Option(course.name, course.id);
        if (select.multiple) option.selected = current.includes(String(course.id));
        select.add(option);
      });
      if (!select.multiple) select.value = current;
    });
    const list = document.querySelector("[data-admin-courses]");
    if (!list) return;
    list.replaceChildren();
    courses.forEach((course) => {
      const row = document.createElement("tr");
      row.className = "border-t border-slate-100";
      [course.course_code, course.name, `₹${Number(course.fee).toLocaleString("en-IN")}`, course.status].forEach((value) => {
        const cell = document.createElement("td");
        cell.className = "px-4 py-3";
        cell.textContent = value;
        row.append(cell);
      });
      const actions = document.createElement("td");
      actions.className = "px-4 py-3";
      actions.append(
        actionButton("Edit", "edit-course", course.id),
        actionButton(course.status === "active" ? "Deactivate" : "Activate", "toggle-course", course.id)
      );
      row.append(actions);
      list.append(row);
    });
  }

  async function loadAdminOperations() {
    const attendanceFilters = new URLSearchParams({
      person_type: document.querySelector("[data-attendance-filter='person_type']")?.value || "student",
      course_id: document.querySelector("[data-attendance-filter='course_id']")?.value || "",
      date_from: document.querySelector("[data-attendance-filter='date_from']")?.value || "",
      date_to: document.querySelector("[data-attendance-filter='date_to']")?.value || "",
      status: document.querySelector("[data-attendance-filter='status']")?.value || "",
      search: document.querySelector("[data-attendance-filter='search']")?.value || ""
    });
    const assignmentFilters = new URLSearchParams({
      course_id: document.querySelector("[data-assignment-filter='course_id']")?.value || "",
      status: document.querySelector("[data-assignment-filter='status']")?.value || "",
      search: document.querySelector("[data-assignment-filter='search']")?.value || ""
    });
    const [attendance, assignments, materials, fees, results, announcements] = await Promise.all([
      api(`/admin/attendance?${attendanceFilters}`),
      api(`/admin/assignments?${assignmentFilters}`),
      api("/admin/materials"),
      api("/admin/fees"),
      api("/admin/results"),
      api("/admin/announcements")
    ]);
    adminAttendanceRecords = attendance.attendance;
    adminAttendancePersonType = attendance.person_type;
    adminAssignmentRecords = assignments.assignments;
    const money = (value) => `₹${Number(value || 0).toLocaleString("en-IN")}`;
    const attendanceRows = attendance.attendance.map((item) => [
      item.attendance_date,
      item.person_type === "employee"
        ? `${item.employee_id} — ${item.full_name}`
        : `${item.student_id} — ${item.full_name}`,
      item.course_name, item.employee_name, item.status, item.remarks,
      (() => {
        const actions = document.createElement("div");
        actions.append(
          actionButton("Edit", "edit-attendance", item.id),
          actionButton("Delete", "delete-attendance", item.id)
        );
        return actions;
      })()
    ]);
    renderRows("[data-admin-attendance]", attendanceRows, Array.from({ length: 7 }, (_, index) => (row) => row[index]));
    document.querySelectorAll("[data-attendance-filter]").forEach((control) => {
      if (control.dataset.filterBound) return;
      control.dataset.filterBound = "true";
      control.addEventListener(control.type === "search" ? "input" : "change", () => {
        if (control.type === "search") {
          window.clearTimeout(control.searchTimer);
          control.searchTimer = window.setTimeout(() => loadAdminOperations().catch(showDashboardError), 250);
        } else {
          loadAdminOperations().catch(showDashboardError);
        }
      });
    });
    document.querySelectorAll("[data-assignment-filter]").forEach((control) => {
      if (control.dataset.filterBound) return;
      control.dataset.filterBound = "true";
      control.addEventListener(control.type === "search" ? "input" : "change", () => {
        if (control.type === "search") {
          window.clearTimeout(control.searchTimer);
          control.searchTimer = window.setTimeout(() => loadAdminOperations().catch(showDashboardError), 250);
        } else {
          loadAdminOperations().catch(showDashboardError);
        }
      });
    });
    renderRows("[data-admin-assignments]", assignments.assignments, [
      (item) => item.title, (item) => item.course_name, (item) => item.due_date,
      (item) => item.status, (item) => item.created_by_login,
      (() => (item) => {
        const actions = document.createElement("div");
        actions.append(
          actionButton("View", "view-assignment", item.id),
          actionButton("Edit", "edit-assignment", item.id),
          actionButton("Delete", "delete-assignment", item.id)
        );
        return actions;
      })()
    ]);
    renderRows("[data-admin-materials]", materials.materials, [
      (item) => item.title, (item) => item.course_name, (item) => item.description,
      (item) => item.created_at, (item) => resourceLink(item.file_url)
    ]);
    renderRows("[data-admin-fees]", fees.fees, [
      (item) => `${item.student_id} — ${item.full_name}`, (item) => item.course_name,
      (item) => money(item.amount), (item) => money(item.paid_amount), (item) => money(item.due_amount),
      (item) => item.payment_date, (item) => item.payment_status
    ]);
    renderRows("[data-admin-results]", results.results, [
      (item) => `${item.student_number} — ${item.full_name}`, (item) => item.course_name,
      (item) => item.subject, (item) => item.marks, (item) => item.grade, (item) => item.exam_date
    ]);
    renderRows("[data-admin-announcements]", announcements.announcements, [
      (item) => item.title, (item) => item.audience, (item) => item.course_name,
      (item) => item.published_at, (item) => item.body
    ]);
  }

  function showDashboardError(error) {
    const status = document.querySelector("[data-dashboard-status]");
    if (status) status.textContent = error.message;
  }

  function actionButton(label, action, id) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.adminAction = action;
    button.dataset.id = String(id);
    button.className = "mr-2 mb-1 whitespace-nowrap text-xs font-semibold text-brand-700 underline";
    button.textContent = label;
    return button;
  }

  function attachPortalForms() {
    document.querySelectorAll("[data-portal-form]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]');
        button.disabled = true;
        try {
          const values = Object.fromEntries(new FormData(form).entries());
          if (values.course_id) {
            values.course_id = Number(values.course_id);
          } else if ("course_id" in values) {
            values.course_id = null;
          }
          if (values.attachment === "") delete values.attachment;
          if (values.due_date === "") delete values.due_date;
          await api(`/portal/${form.dataset.portalForm}`, {
            method: "POST",
            body: JSON.stringify(values)
          });
          form.reset();
          setStatus(form, "Saved successfully.", false);
          await loadEmployeeWorkspace();
        } catch (error) {
          setStatus(form, error.message);
        } finally {
          button.disabled = false;
        }
      });
    });
  }

  function attachAdminForms() {
    const searchTimers = new Map();
    document.querySelectorAll("[data-admin-search]").forEach((input) => {
      input.addEventListener("input", () => {
        const kind = input.dataset.adminSearch;
        window.clearTimeout(searchTimers.get(kind));
        searchTimers.set(kind, window.setTimeout(() => {
          const reload = kind === "students" ? loadAdminStudents : loadAdminEmployees;
          reload().catch((error) => {
            const status = document.querySelector("[data-dashboard-status]");
            if (status) status.textContent = error.message;
          });
        }, 250));
      });
    });
    document.querySelectorAll("[data-admin-status-filter]").forEach((select) => {
      select.addEventListener("change", () => {
        const reload = select.dataset.adminStatusFilter === "students" ? loadAdminStudents : loadAdminEmployees;
        reload().catch((error) => {
          const status = document.querySelector("[data-dashboard-status]");
          if (status) status.textContent = error.message;
        });
      });
    });
    document.querySelectorAll("[data-admin-course-filter]").forEach((select) => {
      select.addEventListener("change", () => {
        const reload = select.dataset.adminCourseFilter === "students" ? loadAdminStudents : loadAdminEmployees;
        reload().catch((error) => {
          const status = document.querySelector("[data-dashboard-status]");
          if (status) status.textContent = error.message;
        });
      });
    });

    document.querySelectorAll("[data-toggle-form]").forEach((button) => {
      button.addEventListener("click", () => {
        const form = document.getElementById(button.getAttribute("aria-controls"));
        if (!form) return;
        form.hidden = !form.hidden;
        button.setAttribute("aria-expanded", String(!form.hidden));
        if (!form.dataset.recordId) {
          form.elements.password.required = !form.hidden;
          form.elements.confirm_password.required = !form.hidden;
          if (!form.hidden) {
            form.elements.password.value = "";
            form.elements.confirm_password.value = "";
          }
        }
        if (!form.hidden) form.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    document.querySelectorAll("[data-admin-form]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]');
        button.disabled = true;
        try {
          const values = Object.fromEntries(new FormData(form).entries());
          const type = form.dataset.adminForm;
          // These hidden inputs have unique names so FormData never collapses
          // two of them into one; map them onto the API's field names here.
          if (type === "attendance") {
            values.person_id = form.dataset.personType === "employee"
              ? values.employee_person_id
              : values.student_person_id;
            values.course_id = values.attendance_course_id || "";
          }
          if (type === "assignments") {
            values.course_id = values.assignment_course_id || "";
          }
          if (values.course_id) values.course_id = Number(values.course_id);
          else if ("course_id" in values) values.course_id = null;
          if (values.employee_id) values.employee_id = Number(values.employee_id);
          else if ("employee_id" in values) values.employee_id = null;
          if (values.student_id) values.student_id = Number(values.student_id);
          if (values.person_id) values.person_id = Number(values.person_id);
          if (form.dataset.adminForm === "employees") {
            values.course_ids = Array.from(form.elements.course_ids.selectedOptions, (option) => Number(option.value));
          }
          if (form.dataset.adminForm === "attendance") {
            const personType = form.dataset.personType || "student";
            const personId = Number(values.person_id);
            if (!personId) throw new Error("Search and select a person before saving attendance.");
            if (personType === "student" && !values.course_id) throw new Error("Select a course for student attendance.");
            if (!values.date) throw new Error("Choose a date for attendance.");
            values.person_type = personType;
            if (values.person_type === "student") values.student_id = values.person_id;
            delete values.employee_person_id;
            delete values.student_person_id;
            delete values.attendance_course_id;
          }
          if (values.password !== values.confirm_password) {
            throw new Error("Passwords do not match.");
          }
          if (!form.dataset.recordId && ["students", "employees"].includes(form.dataset.adminForm)) {
            const invalid = passwordError(values.password || "");
            if (invalid) throw new Error(invalid);
          }
          if (values.password === "") delete values.password;
          if (values.confirm_password === "") delete values.confirm_password;
          if (values.fee !== undefined) values.fee = Number(values.fee);
          if (values.amount !== undefined) values.amount = Number(values.amount);
          if (values.paid_amount !== undefined) values.paid_amount = Number(values.paid_amount);
          if (values.marks !== undefined) values.marks = values.marks === "" ? null : Number(values.marks);
          if (values.duration_months !== undefined) {
            values.duration_months = values.duration_months ? Number(values.duration_months) : null;
          }
          const editingId = form.dataset.recordId;
          const label = type === "students" ? "student" : type === "employees" ? "employee" :
            type === "attendance" ? "attendance" : type === "assignments" ? "assignment" : "course";
          const originalLabel = button.textContent;
          button.dataset.attendanceLabel = originalLabel;
          // Guard against double-click and network retries.
          button.textContent = "Saving…";
          setStatus(form, editingId ? "Saving changes…" : `Creating ${label}…`, false);
          const result = await api(`/admin/${type}${editingId ? `/${editingId}` : ""}`, {
            method: editingId ? "PUT" : "POST",
            body: JSON.stringify(values)
          });
          const account = result.student || result.employee;
          const message = account ? `${account.full_name} created successfully.` :
            result.course_id ? `Course created successfully (ID ${result.course_id}).` :
              (type === "attendance" || type === "assignments") && result.message ? result.message :
                editingId ? "Updated successfully." : "Saved successfully.";
          form.reset();
          delete form.dataset.recordId;
          const attendanceSubmit = form.querySelector('[type="submit"]');
          if (type === "attendance") {
            attendanceSubmit.textContent = "Save Attendance";
            clearSearchSelection(form.dataset.personType || "student");
            clearSearchSelection("course");
            await refreshAttendanceContext().catch(() => {});
          } else {
            button.textContent = originalLabel;
            if (type === "assignments") {
              clearSearchSelection("assignment-course");
              const reset = form.querySelector('[data-admin-form="assignments"] [data-person-search-input]');
              if (reset) reset.value = "";
            }
          }
          if (form.elements.password) {
            form.elements.password.required = true;
            form.elements.confirm_password.required = true;
          }
          setStatus(form, message, false);
          if (account) {
            if (result.employee) adminEmployeeOptionsCache = null;
            showCredentialModal({
              name: account.full_name,
              loginId: account.login_id,
              password: account.temporary_password,
              role: result.student ? "Student" : "Employee"
            });
          }
          try {
            await loadAdminDashboard();
          } catch (error) {
            const dashboardStatus = document.querySelector("[data-dashboard-status]");
            if (dashboardStatus) dashboardStatus.textContent = `Saved successfully, but the lists could not be refreshed: ${error.message}`;
          }
        } catch (error) {
          button.textContent = button.dataset.attendanceLabel || button.textContent;
          setStatus(form, error.message);
        } finally {
          button.disabled = false;
        }
      });
    });

    // Any change to person / course / date re-checks for an existing record, so
    // the button switches to "Update" before the admin ever saves.
    const attendanceForm = document.querySelector('[data-admin-form="attendance"]');
    if (attendanceForm) {
      ["student", "employee", "course"].forEach((key) => {
        document.addEventListener("person:selected", (event) => {
          if (event.detail.key !== key) return;
          refreshAttendanceContext().catch(showDashboardError);
        });
      });
      attendanceForm.elements.date.addEventListener("change", () => {
        refreshAttendanceContext().catch(showDashboardError);
      });
      attendanceForm.elements.status.addEventListener("change", () => {
        attendanceForm.querySelector("[data-attendance-existing]")?.classList.remove("hidden");
      });
    }

    document.querySelector('[data-admin-form="attendance"]')?.addEventListener("reset", () => {
      delete document.querySelector('[data-admin-form="attendance"]').dataset.recordId;
      window.setTimeout(() => {
        setAttendanceSubmitLabel("create");
        document.querySelector('[data-admin-form="attendance"] [data-attendance-report]')?.classList.add("hidden");
      });
    });

    document.querySelectorAll("[data-generate-password]").forEach((button) => {
      button.addEventListener("click", () => {
        const form = button.closest("form");
        if (!form) return;
        const words = ["Amber", "Anchor", "Apple", "Apricot", "Archer", "Aspen", "Atlas", "Autumn", "Bamboo", "Beacon", "Berry", "Birch", "Blossom", "Breeze", "Cactus", "Canyon", "Cedar", "Charger", "Cherry", "Clover", "Cloud", "Comet", "Coral", "Cosmos", "Cricket", "Daisy", "Delta", "Dolphin", "Dragon", "Eagle", "Echo", "Ember", "Falcon", "Fern", "Flame", "Flute", "Forest", "Galaxy", "Garden", "Glacier", "Harbor", "Hazel", "Horizon", "Island", "Jasmine", "Jupiter", "Kestrel", "Lagoon", "Lantern", "Laurel", "Lemon", "Lotus", "Maple", "Marble", "Mango", "Meadow", "Meteor", "Midnight", "Mint", "Mountain", "Nectar", "Nova", "Ocean", "Olive", "Orchid", "Otter", "Pebble", "Pine", "Planet", "Prairie", "Quartz", "Quill", "Rain", "Raven", "Redwood", "River", "Robin", "Rocket", "Saffron", "Sailboat", "Sapphire", "Sequoia", "Silver", "Snow", "Solar", "Sparrow", "Spring", "Starling", "Summit", "Sunrise", "Thunder", "Tiger", "Topaz", "Tulip", "Velvet", "Violet", "Willow", "Winter", "Wren", "Zephyr"];
        const symbols = ["@", "#", "$", "%", "!"];
        const random = new Uint32Array(5);
        let generated;
        do {
          if (!window.crypto?.getRandomValues) {
            setStatus(form, "Secure password generation is unavailable in this browser.");
            return;
          }
          window.crypto.getRandomValues(random);
          generated = `${words[random[0] % words.length]}${symbols[random[1] % symbols.length]}${String((random[2] % 9000) + 1000)}${words[random[3] % words.length]}${words[random[4] % words.length]}`;
        } while (generatedPasswords.has(generated));
        generatedPasswords.add(generated);
        form.elements.password.value = generated;
        form.elements.confirm_password.value = generated;
        const status = form.querySelector("[data-form-status]");
        if (status) {
          status.textContent = "Temporary password generated.";
          status.classList.remove("text-red-600");
          status.classList.add("text-brand-700");
        }
      });
    });

    document.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-admin-action]");
        if (!button) return;
        const { adminAction: action, id } = button.dataset;
        const status = document.querySelector("[data-dashboard-status]");
        button.disabled = true;
        try {
          if (action === "edit-attendance") {
            const record = adminAttendanceRecords.find((item) => String(item.id) === id);
            if (!record) throw new Error("Attendance record not found.");
            const form = document.querySelector('[data-admin-form="attendance"]');
            const personType = record.person_type || adminAttendancePersonType || "student";
            // Switch the selector so the right person panel is visible.
            const radio = form.querySelector(`[data-person-type-option][value="${personType}"]`);
            if (radio && !radio.checked) {
              radio.checked = true;
              radio.dispatchEvent(new Event("change", { bubbles: true }));
            }
            if (personType === "employee") {
              setSearchSelection("employee", {
                id: record.person_id,
                employee_id: record.employee_id,
                full_name: record.full_name,
                designation: record.designation
              });
            } else {
              setSearchSelection("student", {
                id: record.person_id,
                student_id: record.student_id,
                full_name: record.full_name,
                course_name: record.course_name
              });
              if (record.course_id) {
                setSearchSelection("course", {
                  id: record.course_id,
                  name: record.course_name,
                  course_code: ""
                });
              }
            }
            form.elements.date.value = String(record.attendance_date).slice(0, 10);
            form.elements.status.value = record.status;
            form.elements.remarks.value = record.remarks || "";
            form.dataset.recordId = id;
            setAttendanceSubmitLabel("update", "Update Attendance");
            announceExistingRecord(attendanceFormState(), record);
            loadAttendanceReport(attendanceFormState()).catch(() => {});
            setStatus(form, "Editing attendance. Save to apply changes.", false);
            form.scrollIntoView({ behavior: "smooth", block: "center" });
          } else if (action === "delete-attendance") {
            const record = adminAttendanceRecords.find((item) => String(item.id) === id);
            const label = record?.person_type === "employee" ? "employee" : "student";
            const who = record ? record.full_name : "this person";
            const when = record ? String(record.attendance_date).slice(0, 10) : "";
            const current = record ? record.status : "";
            const confirmed = window.confirm(
              `Delete attendance?\n\n${who}\nDate: ${when}\nStatus: ${current}\n\nThis action cannot be undone.`
            );
            if (!confirmed) return;
            await api(`/admin/attendance/${id}`, {
              method: "DELETE",
              body: JSON.stringify({ person_type: record?.person_type || "student" })
            });
            await loadAdminDashboard();
            if (status) status.textContent = "Attendance record deleted.";
          } else if (action === "view-assignment" || action === "edit-assignment" || action === "delete-assignment") {
            const record = adminAssignmentRecords.find((item) => String(item.id) === id);
            if (!record) throw new Error("Assignment not found.");
            if (action === "view-assignment") {
              const { panel } = makeModal(record.title, record.description || "No description provided.");
              panel.querySelector("p").textContent =
                `${record.course_name} · Due ${record.due_date || "not set"} · ${record.status}`;
            } else if (action === "delete-assignment") {
              if (!window.confirm(`Delete assignment "${record.title}"? This cannot be undone.`)) return;
              await api(`/admin/assignments/${id}`, { method: "DELETE", body: "{}" });
              await loadAdminOperations().catch(showDashboardError);
              if (status) status.textContent = "Assignment deleted.";
            } else {
              const form = document.querySelector('[data-admin-form="assignments"]');
              form.hidden = false;
              form.elements.title.value = record.title;
              form.elements.description.value = record.description || "";
              form.elements.due_date.value = record.due_date ? String(record.due_date).slice(0, 10) : "";
              form.elements.resource_url.value = record.resource_url || record.attachment || "";
              form.elements.status.value = record.status;
              setSearchSelection("assignment-course", {
                id: record.course_id,
                name: record.course_name,
                course_code: ""
              });
              form.dataset.recordId = id;
              form.querySelector('[type="submit"]').textContent = "Update Assignment";
              setStatus(form, "Editing assignment. Save to apply changes.", false);
              form.scrollIntoView({ behavior: "smooth", block: "center" });
            }
          } else if (action.startsWith("edit-")) {
            const kind = action.replace("edit-", "");
            const record = kind === "course"
              ? (await api("/admin/courses")).courses.find((course) => String(course.id) === id)
              : (await api(`/admin/${kind === "student" ? "students" : "employees"}/${id}`))[kind];
            if (!record) throw new Error(`${kind} not found.`);
            const form = document.querySelector(`[data-admin-form="${kind === "course" ? "courses" : `${kind}s`}"]`);
            if (form.hidden) {
              form.hidden = false;
              document.querySelector(`[data-toggle-form="${kind}s"]`)?.setAttribute("aria-expanded", "true");
            }
            if (form.elements.password) {
              form.elements.password.required = false;
              form.elements.confirm_password.required = false;
              form.elements.password.value = "";
              form.elements.confirm_password.value = "";
            }
            Object.entries(record).forEach(([key, value]) => {
              const control = form.elements.namedItem(key);
              if (!control) return;
              if (control instanceof HTMLSelectElement && control.multiple) {
                const selectedValues = Array.isArray(value) ? value : [];
                Array.from(control.options).forEach((option) => { option.selected = selectedValues.includes(Number(option.value)); });
              } else control.value = value == null ? "" : value;
            });
            form.dataset.recordId = id;
            form.scrollIntoView({ behavior: "smooth", block: "center" });
            setStatus(form, "Editing record. Save to apply changes.", false);
          } else if (action.startsWith("delete-")) {
            const kind = action.replace("delete-", "");
            const label = kind === "student" ? "student" : "employee";
            if (!window.confirm(`Permanently delete this ${label} and all associated records? This cannot be undone.`)) return;
            if (window.prompt('Type DELETE to confirm permanent deletion.') !== "DELETE") return;
            if (status) status.textContent = `Deleting ${label}…`;
            await api(`/admin/${kind}s/${id}`, {
              method: "DELETE",
              body: JSON.stringify({ confirmation: "DELETE" })
            });
            if (kind === "employee") adminEmployeeOptionsCache = null;
            await loadAdminDashboard();
            if (status) status.textContent = `${label[0].toUpperCase()}${label.slice(1)} and associated records permanently deleted.`;
          } else if (action.startsWith("toggle-")) {
            const kind = action.replace("toggle-", "");
            const endpoint = kind === "course" ? "courses" : `${kind}s`;
            const collection = kind === "course" ? "courses" : `${kind}s`;
            const records = await api(`/admin/${endpoint}`);
            const record = records[collection].find((item) => String(item.id) === id);
            if (!record) throw new Error(`${kind} not found.`);
            await api(`/admin/${endpoint}/${id}`, {
              method: "PUT",
              body: JSON.stringify({ status: record.status === "active" ? "inactive" : "active" })
            });
            if (kind === "employee") adminEmployeeOptionsCache = null;
            await Promise.all([loadAdminStudents(), loadAdminEmployees(), loadAdminCourses()]);
          } else if (action.startsWith("reset-")) {
            const kind = action.replace("reset-", "");
            if (status) status.textContent = "Resetting password…";
            const details = await api(`/admin/${kind}s/${id}`);
            const result = await api(`/admin/${kind}s/${id}/reset-password`, { method: "POST", body: "{}" });
            const account = details[kind];
            showCredentialModal({
              name: account.full_name,
              loginId: account[`${kind}_id`],
              password: result.temporary_password,
              role: kind === "student" ? "Student" : "Employee",
              title: "Password reset successfully"
            });
          }
        } catch (error) {
          if (status) status.textContent = error.message;
        } finally {
          button.disabled = false;
        }
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    await attachLogin();
    await attachLogout();
    attachDashboardNavigation();
    attachPasswordChangeButtons();
    attachProfileForms();
    const dashboardRole = document.body.dataset.authRole;
    if (dashboardRole) {
      await loadDashboard();
      if (dashboardRole === "employee") {
        attachEmployeeStudentFilters();
        attachPortalForms();
      }
      if (dashboardRole === "admin") {
        try {
          await loadAdminDashboard();
          attachAdminForms();
          attachPersonSearches();
          attachAttendancePersonType();
        } catch (error) {
          const status = document.querySelector("[data-dashboard-status]");
          if (status) status.textContent = error.message;
        }
      }
    }
  });
})();
