/* Meridian study planner.
 *
 * Fully client-side. Tasks, exam countdowns and focus-timer settings are kept in
 * localStorage under one versioned key and never sent anywhere. The same file
 * runs on the FastAPI site and on the static GitHub Pages copy.
 *
 * User text is only ever written with textContent, never innerHTML.
 */
(function () {
  "use strict";

  var KEY = "ev:planner:v1";
  var FORMAT = "engineverse-planner";
  var MAX_TASKS = 1000;
  var MAX_EXAMS = 100;
  var PRIORITIES = { high: 0, normal: 1, low: 2 };
  var PRIORITY_LABEL = { high: "High", normal: "Normal", low: "Low" };

  var root = document.querySelector("[data-planner]");
  if (!root) return;
  root.hidden = false;

  // ---------------------------------------------------------------- helpers
  function $(sel, scope) { return (scope || root).querySelector(sel); }
  function $all(sel, scope) { return Array.prototype.slice.call((scope || root).querySelectorAll(sel)); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function localIso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function today() { return localIso(new Date()); }
  function isIsoDate(s) {
    if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    var p = s.split("-").map(Number);
    var d = new Date(p[0], p[1] - 1, p[2]);
    return d.getFullYear() === p[0] && d.getMonth() === p[1] - 1 && d.getDate() === p[2];
  }
  function daysBetween(fromIso, toIso) {
    var a = fromIso.split("-").map(Number), b = toIso.split("-").map(Number);
    return Math.round((Date.UTC(b[0], b[1] - 1, b[2]) - Date.UTC(a[0], a[1] - 1, a[2])) / 86400000);
  }
  function formatDate(iso) {
    var p = iso.split("-").map(Number);
    try {
      return new Date(p[0], p[1] - 1, p[2]).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
    } catch (e) { return iso; }
  }
  function uid() {
    if (window.crypto && window.crypto.getRandomValues) {
      var a = new Uint32Array(2);
      window.crypto.getRandomValues(a);
      return a[0].toString(36) + a[1].toString(36);
    }
    return Date.now().toString(36) + Math.floor(Math.random() * 1e9).toString(36);
  }
  function clean(s, max) { return String(s == null ? "" : s).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, max); }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "className") n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    if (text != null) n.textContent = text;
    return n;
  }
  function toast(msg) {
    var ev = window.EV;
    if (ev && typeof ev.toast === "function") { ev.toast(msg); return; }
    var s = $("[data-planner-data-status]");
    if (s) s.textContent = msg;
  }

  // ---------------------------------------------------------------- storage
  var storageOk = true;
  function emptyState() {
    return { version: 1, tasks: [], exams: [], focus: { work: 25, brk: 5, sessions: {} } };
  }

  // Validate and normalise anything read from storage or an imported file.
  // Unknown fields are dropped; malformed entries are skipped, not fatal.
  function sanitize(raw) {
    var out = emptyState();
    if (!raw || typeof raw !== "object") return out;
    if (Array.isArray(raw.tasks)) {
      raw.tasks.slice(0, MAX_TASKS).forEach(function (t) {
        if (!t || typeof t !== "object") return;
        var title = clean(t.title, 120);
        if (!title) return;
        out.tasks.push({
          id: clean(t.id, 40) || uid(),
          title: title,
          subject: clean(t.subject, 60),
          due: isIsoDate(t.due) ? t.due : "",
          priority: Object.prototype.hasOwnProperty.call(PRIORITIES, t.priority) ? t.priority : "normal",
          done: t.done === true,
          created: typeof t.created === "number" ? t.created : Date.now()
        });
      });
    }
    if (Array.isArray(raw.exams)) {
      raw.exams.slice(0, MAX_EXAMS).forEach(function (x) {
        if (!x || typeof x !== "object") return;
        var name = clean(x.name, 80);
        if (!name || !isIsoDate(x.date)) return;
        out.exams.push({ id: clean(x.id, 40) || uid(), name: name, date: x.date });
      });
    }
    var f = raw.focus;
    if (f && typeof f === "object") {
      var w = Number(f.work), b = Number(f.brk);
      if (w >= 1 && w <= 180) out.focus.work = Math.round(w);
      if (b >= 1 && b <= 60) out.focus.brk = Math.round(b);
      if (f.sessions && typeof f.sessions === "object") {
        Object.keys(f.sessions).forEach(function (k) {
          var n = Number(f.sessions[k]);
          if (isIsoDate(k) && n > 0 && n < 1000) out.focus.sessions[k] = Math.floor(n);
        });
      }
    }
    // Ensure ids are unique so edit/delete target exactly one item.
    var seen = {};
    out.tasks.forEach(function (t) { if (seen[t.id]) t.id = uid(); seen[t.id] = 1; });
    return out;
  }

  function load() {
    try {
      var s = window.localStorage.getItem(KEY);
      return s ? sanitize(JSON.parse(s)) : emptyState();
    } catch (e) {
      storageOk = false;
      return emptyState();
    }
  }

  var state = load();

  function save() {
    // Keep only the last 60 days of focus counts.
    var cutoff = localIso(new Date(Date.now() - 60 * 86400000));
    Object.keys(state.focus.sessions).forEach(function (k) { if (k < cutoff) delete state.focus.sessions[k]; });
    try {
      window.localStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) {
      if (storageOk) toast("Could not save: this browser's storage is full or blocked.");
      storageOk = false;
    }
    $("[data-planner-storage-warning]").hidden = storageOk;
  }

  // Another tab changed the plan: reload it so tabs do not overwrite each other.
  window.addEventListener("storage", function (e) {
    if (e.key !== KEY) return;
    state = load();
    renderAll();
  });

  // ---------------------------------------------------------------- tasks
  var taskForm = $("[data-task-form]");
  var taskList = $("[data-task-list]");
  var filter = "all";
  var query = "";

  function bucket(t, now) {
    if (t.done) return "done";
    if (!t.due) return "upcoming";
    if (t.due < now) return "overdue";
    if (t.due === now) return "today";
    return "upcoming";
  }

  function showErr(name, msg) {
    var e = $("[data-err='" + name + "']", taskForm);
    var input = taskForm.elements[name];
    if (e) { e.textContent = msg || ""; e.hidden = !msg; }
    if (input) {
      if (msg) input.setAttribute("aria-invalid", "true");
      else input.removeAttribute("aria-invalid");
    }
  }

  function resetTaskForm() {
    taskForm.reset();
    taskForm.elements.id.value = "";
    $("[data-task-submit]").textContent = "Add task";
    $("[data-task-cancel]").hidden = true;
    showErr("title", ""); showErr("due", "");
  }

  taskForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var f = taskForm.elements;
    var title = clean(f.title.value, 120);
    var due = f.due.value;
    var ok = true;
    showErr("title", ""); showErr("due", "");
    if (!title) { showErr("title", "Give the task a short title."); ok = false; }
    if (due && !isIsoDate(due)) { showErr("due", "Use a valid date, or leave it empty."); ok = false; }
    if (!ok) { (title ? f.due : f.title).focus(); return; }
    var id = f.id.value;
    var data = {
      title: title,
      subject: clean(f.subject.value, 60),
      due: due,
      priority: Object.prototype.hasOwnProperty.call(PRIORITIES, f.priority.value) ? f.priority.value : "normal"
    };
    if (id) {
      var t = state.tasks.find(function (x) { return x.id === id; });
      if (t) Object.keys(data).forEach(function (k) { t[k] = data[k]; });
      announce("Task updated.");
    } else {
      if (state.tasks.length >= MAX_TASKS) { showErr("title", "The planner holds up to " + MAX_TASKS + " tasks. Remove some first."); return; }
      data.id = uid(); data.done = false; data.created = Date.now();
      state.tasks.push(data);
      announce("Task added.");
    }
    save();
    resetTaskForm();
    renderTasks();
    f.title.focus();
  });

  $("[data-task-cancel]").addEventListener("click", function () { resetTaskForm(); taskForm.elements.title.focus(); });

  function startEdit(t) {
    var f = taskForm.elements;
    f.id.value = t.id; f.title.value = t.title; f.subject.value = t.subject; f.due.value = t.due; f.priority.value = t.priority;
    $("[data-task-submit]").textContent = "Save changes";
    $("[data-task-cancel]").hidden = false;
    f.title.focus();
    if (taskForm.scrollIntoView) taskForm.scrollIntoView({ block: "nearest" });
  }

  function announce(msg) { var s = $("[data-task-status]"); s.textContent = ""; setTimeout(function () { s.textContent = msg; }, 30); }

  $all("[data-filter]").forEach(function (b) {
    b.addEventListener("click", function () { filter = b.getAttribute("data-filter"); renderTasks(); });
  });
  $("#task-search").addEventListener("input", function (e) { query = e.target.value.toLowerCase().trim(); renderTasks(); });
  $("[data-clear-done]").addEventListener("click", function () {
    var n = state.tasks.filter(function (t) { return t.done; }).length;
    if (!n || !window.confirm("Remove " + n + " completed task" + (n === 1 ? "" : "s") + "?")) return;
    state.tasks = state.tasks.filter(function (t) { return !t.done; });
    save(); renderTasks(); announce("Completed tasks removed.");
  });

  function renderTasks() {
    var now = today();
    var counts = { all: 0, today: 0, upcoming: 0, overdue: 0, done: 0 };
    state.tasks.forEach(function (t) {
      var b = bucket(t, now);
      counts[b]++;
      if (b !== "done") counts.all++;
    });
    $all("[data-count]").forEach(function (s) { s.textContent = counts[s.getAttribute("data-count")] || ""; });
    $all("[data-filter]").forEach(function (b) {
      var on = b.getAttribute("data-filter") === filter;
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.classList.toggle("accent", on);
    });

    var shown = state.tasks.filter(function (t) {
      var b = bucket(t, now);
      if (filter === "all" ? b === "done" : b !== filter) return false;
      if (query && (t.title + " " + t.subject).toLowerCase().indexOf(query) === -1) return false;
      return true;
    }).sort(function (a, b) {
      if (a.due !== b.due) return !a.due ? 1 : !b.due ? -1 : a.due < b.due ? -1 : 1;
      if (a.priority !== b.priority) return PRIORITIES[a.priority] - PRIORITIES[b.priority];
      return a.created - b.created;
    });

    taskList.textContent = "";
    shown.forEach(function (t) { taskList.appendChild(taskItem(t, now)); });

    var empty = $("[data-task-empty]");
    empty.hidden = shown.length > 0;
    if (!shown.length) {
      var msg;
      if (!state.tasks.length) msg = "No tasks yet. Add your first one above.";
      else if (query) msg = "No tasks match \u201c" + query + "\u201d.";
      else msg = {
        all: "Everything is done. Nice work.", today: "Nothing due today.", upcoming: "Nothing upcoming.",
        overdue: "Nothing overdue.", done: "No completed tasks yet."
      }[filter];
      $("[data-task-empty-text]").textContent = msg;
    }
    $("[data-task-foot]").hidden = counts.done === 0;

    var subjects = {};
    state.tasks.forEach(function (t) { if (t.subject) subjects[t.subject] = 1; });
    var dl = document.getElementById("planner-subjects");
    dl.textContent = "";
    Object.keys(subjects).sort().slice(0, 50).forEach(function (s) { dl.appendChild(el("option", { value: s })); });
  }

  function taskItem(t, now) {
    var b = bucket(t, now);
    var li = el("li", { className: "planner-item" + (t.done ? " is-done" : "") + (b === "overdue" ? " is-overdue" : "") });
    var cbId = "task-done-" + t.id;
    var cb = el("input", { type: "checkbox", id: cbId });
    cb.checked = t.done;
    cb.addEventListener("change", function () {
      t.done = cb.checked; save(); renderTasks();
      announce(t.done ? "Marked done: " + t.title : "Marked not done: " + t.title);
    });
    var body = el("div", { className: "planner-item-body" });
    body.appendChild(el("label", { "for": cbId, className: "planner-item-title" }, t.title));
    var meta = el("p", { className: "planner-item-meta" });
    if (t.subject) meta.appendChild(el("span", { className: "chip" }, t.subject));
    if (t.priority !== "normal") meta.appendChild(el("span", { className: "chip " + (t.priority === "high" ? "warn" : "") }, PRIORITY_LABEL[t.priority] + " priority"));
    if (t.due) {
      var d = daysBetween(now, t.due);
      var rel = t.done ? "" : d === 0 ? " (today)" : d === 1 ? " (tomorrow)" : d < 0 ? " (" + -d + " day" + (d === -1 ? "" : "s") + " overdue)" : " (in " + d + " days)";
      meta.appendChild(el("time", { datetime: t.due, className: b === "overdue" ? "planner-overdue" : "" }, "Due " + formatDate(t.due) + rel));
    }
    body.appendChild(meta);
    var actions = el("div", { className: "planner-item-actions" });
    var edit = el("button", { type: "button", className: "btn btn-ghost btn-sm" }, "Edit");
    edit.appendChild(el("span", { className: "sr-only" }, ": " + t.title));
    edit.addEventListener("click", function () { startEdit(t); });
    var del = el("button", { type: "button", className: "btn btn-ghost btn-sm" }, "Delete");
    del.appendChild(el("span", { className: "sr-only" }, ": " + t.title));
    del.addEventListener("click", function () {
      if (!window.confirm("Delete \u201c" + t.title + "\u201d?")) return;
      state.tasks = state.tasks.filter(function (x) { return x.id !== t.id; });
      if (taskForm.elements.id.value === t.id) resetTaskForm();
      save(); renderTasks(); announce("Task deleted.");
      taskForm.elements.title.focus();
    });
    actions.appendChild(edit); actions.appendChild(del);
    li.appendChild(cb); li.appendChild(body); li.appendChild(actions);
    return li;
  }

  // ---------------------------------------------------------------- exams
  var examForm = $("[data-exam-form]");
  examForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var name = clean(examForm.elements.name.value, 80);
    var date = examForm.elements.date.value;
    var err = $("[data-exam-err]");
    var msg = !name ? "Name the exam." : !isIsoDate(date) ? "Pick the exam date." :
      state.exams.length >= MAX_EXAMS ? "You can track up to " + MAX_EXAMS + " exams." : "";
    err.textContent = msg; err.hidden = !msg;
    if (msg) { (!name ? examForm.elements.name : examForm.elements.date).focus(); return; }
    state.exams.push({ id: uid(), name: name, date: date });
    save(); examForm.reset(); renderExams();
    examForm.elements.name.focus();
  });

  function renderExams() {
    var list = $("[data-exam-list]");
    var now = today();
    list.textContent = "";
    state.exams.slice().sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; }).forEach(function (x) {
      var d = daysBetween(now, x.date);
      var li = el("li", { className: "planner-exam" + (d < 0 ? " is-past" : "") });
      var n = el("span", { className: "planner-exam-days" }, d < 0 ? "Done" : d === 0 ? "Today" : String(d));
      if (d > 0) n.appendChild(el("small", null, d === 1 ? " day" : " days"));
      var info = el("div", { className: "planner-exam-info" });
      info.appendChild(el("strong", null, x.name));
      info.appendChild(el("time", { datetime: x.date }, formatDate(x.date)));
      var del = el("button", { type: "button", className: "btn btn-ghost btn-sm" }, "Remove");
      del.appendChild(el("span", { className: "sr-only" }, ": " + x.name));
      del.addEventListener("click", function () {
        state.exams = state.exams.filter(function (y) { return y.id !== x.id; });
        save(); renderExams();
        examForm.elements.name.focus();
      });
      li.appendChild(n); li.appendChild(info); li.appendChild(del);
      list.appendChild(li);
    });
    $("[data-exam-empty]").hidden = state.exams.length > 0;
  }

  // ---------------------------------------------------------------- focus timer
  // The timer stores an absolute end time, so it stays correct when the tab is
  // in the background and browsers throttle setInterval.
  var timer = { phase: "work", running: false, endAt: 0, remaining: state.focus.work * 60000, tick: null };
  var clock = $("[data-focus-clock]");

  function fmt(ms) {
    var s = Math.max(0, Math.ceil(ms / 1000));
    return pad(Math.floor(s / 60)) + ":" + pad(s % 60);
  }
  function phaseLength(p) { return (p === "work" ? state.focus.work : state.focus.brk) * 60000; }
  function focusAnnounce(msg) { var a = $("[data-focus-announce]"); a.textContent = ""; setTimeout(function () { a.textContent = msg; }, 30); }

  function renderTimer() {
    var left = timer.running ? timer.endAt - Date.now() : timer.remaining;
    clock.textContent = fmt(left);
    $("[data-focus-phase]").textContent = timer.phase === "work" ? "Focus" : "Break";
    $("[data-focus-start]").textContent = timer.running ? "Pause" : (timer.remaining < phaseLength(timer.phase) ? "Resume" : "Start");
    $("[data-focus-skip]").textContent = timer.phase === "work" ? "Skip to break" : "Skip to focus";
    root.classList.toggle("is-break", timer.phase === "brk");
    var n = state.focus.sessions[today()] || 0;
    $("[data-focus-count]").textContent = n + " focus session" + (n === 1 ? "" : "s") + " today";
  }

  function stopTick() { if (timer.tick) { clearInterval(timer.tick); timer.tick = null; } }

  function switchPhase(completed) {
    if (completed && timer.phase === "work") {
      var k = today();
      state.focus.sessions[k] = (state.focus.sessions[k] || 0) + 1;
      save();
    }
    timer.phase = timer.phase === "work" ? "brk" : "work";
    timer.remaining = phaseLength(timer.phase);
    timer.running = false;
    stopTick();
    renderTimer();
    focusAnnounce(completed
      ? (timer.phase === "brk" ? "Focus session complete. Time for a " + state.focus.brk + " minute break." : "Break over. Ready to focus.")
      : (timer.phase === "brk" ? "Skipped to break." : "Skipped to focus."));
    if (completed) toast(timer.phase === "brk" ? "Focus session complete. Take a break." : "Break over.");
  }

  function onTick() {
    if (timer.endAt - Date.now() <= 0) { switchPhase(true); return; }
    renderTimer();
  }

  $("[data-focus-start]").addEventListener("click", function () {
    if (timer.running) {
      timer.remaining = Math.max(0, timer.endAt - Date.now());
      timer.running = false; stopTick();
      focusAnnounce("Paused with " + fmt(timer.remaining) + " left.");
    } else {
      timer.endAt = Date.now() + timer.remaining;
      timer.running = true;
      stopTick(); timer.tick = setInterval(onTick, 500);
      focusAnnounce((timer.phase === "work" ? "Focus" : "Break") + " started.");
    }
    renderTimer();
  });
  $("[data-focus-reset]").addEventListener("click", function () {
    stopTick(); timer.running = false; timer.remaining = phaseLength(timer.phase);
    renderTimer(); focusAnnounce("Timer reset.");
  });
  $("[data-focus-skip]").addEventListener("click", function () { switchPhase(false); });

  var focusForm = $("[data-focus-form]");
  focusForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var w = Number(focusForm.elements.work.value), b = Number(focusForm.elements.brk.value);
    var err = $("[data-focus-err]");
    var msg = !(w >= 1 && w <= 180 && Math.round(w) === w) ? "Focus length must be a whole number from 1 to 180." :
      !(b >= 1 && b <= 60 && Math.round(b) === b) ? "Break length must be a whole number from 1 to 60." : "";
    err.textContent = msg; err.hidden = !msg;
    if (msg) return;
    state.focus.work = w; state.focus.brk = b; save();
    if (!timer.running) timer.remaining = phaseLength(timer.phase);
    renderTimer();
    toast("Timer settings saved.");
  });

  function renderFocusForm() {
    focusForm.elements.work.value = state.focus.work;
    focusForm.elements.brk.value = state.focus.brk;
  }

  // ---------------------------------------------------------------- import / export
  var dataStatus = $("[data-planner-data-status]");
  $("[data-planner-export]").addEventListener("click", function () {
    if (/EngineVerseAndroid\//.test(navigator.userAgent)) {
      dataStatus.textContent = "Saving files is not available inside the Meridian Android app. Use \u201cOpen in browser\u201d (top right) to save this file.";
      return;
    }
    var payload = { format: FORMAT, version: 1, exported_at: new Date().toISOString(),
      tasks: state.tasks, exams: state.exams, focus: state.focus };
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = el("a", { href: url, download: "engineverse-planner-" + today() + ".json" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    dataStatus.textContent = "Exported " + state.tasks.length + " tasks and " + state.exams.length + " exams.";
  });

  $("[data-planner-import]").addEventListener("change", function (e) {
    var file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { dataStatus.textContent = "That file is too large to be a planner export (limit 2 MB)."; return; }
    var reader = new FileReader();
    reader.onload = function () {
      var raw;
      try { raw = JSON.parse(String(reader.result)); } catch (err) { dataStatus.textContent = "That file is not valid JSON."; return; }
      if (!raw || raw.format !== FORMAT) { dataStatus.textContent = "That file is not an Meridian planner export."; return; }
      var incoming = sanitize(raw);
      if (!window.confirm("Replace your current planner (" + state.tasks.length + " tasks, " + state.exams.length +
        " exams) with the imported one (" + incoming.tasks.length + " tasks, " + incoming.exams.length + " exams)?")) return;
      state = incoming; save(); renderAll();
      dataStatus.textContent = "Imported " + incoming.tasks.length + " tasks and " + incoming.exams.length + " exams.";
    };
    reader.onerror = function () { dataStatus.textContent = "Could not read that file."; };
    reader.readAsText(file);
  });

  $("[data-planner-clear]").addEventListener("click", function () {
    if (!window.confirm("Delete every task, exam countdown and focus record from this browser? This cannot be undone. Export first if you want a copy.")) return;
    state = emptyState();
    try { window.localStorage.removeItem(KEY); } catch (err) { /* ignore */ }
    stopTick(); timer.phase = "work"; timer.running = false; timer.remaining = phaseLength("work");
    resetTaskForm(); renderAll();
    dataStatus.textContent = "Planner data deleted.";
  });

  // ---------------------------------------------------------------- boot
  function renderAll() {
    renderTasks(); renderExams(); renderFocusForm();
    if (!timer.running && timer.remaining > phaseLength(timer.phase)) timer.remaining = phaseLength(timer.phase);
    renderTimer();
    $("[data-planner-storage-warning]").hidden = storageOk;
  }

  // Re-render at midnight so "today" and overdue buckets stay right.
  var lastDay = today();
  setInterval(function () {
    if (today() !== lastDay) { lastDay = today(); renderTasks(); renderExams(); renderTimer(); }
  }, 60000);

  // Probe storage once so private-mode browsers get the warning up front.
  try { window.localStorage.setItem(KEY + ":probe", "1"); window.localStorage.removeItem(KEY + ":probe"); }
  catch (e) { storageOk = false; }

  renderAll();
})();
