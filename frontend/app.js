"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("hook-form");
  const fields = {
    name: $("name"), description: $("description"), trigger: $("trigger"), matcher: $("matcher"),
    command: $("command"), prompt: $("prompt"), timeout: $("timeout"), enabled: $("enabled"),
  };
  let triggers = [];
  let templates = [];
  let currentActionType = "command";
  let validationSequence = 0;
  let latestValidation = { valid: false, issues: [] };
  let toastTimer;
  let busyTimer;
  const demoMode = new URLSearchParams(window.location.search).get("demo") === "1";
  let demoData = null;
  if (demoMode) {
    document.querySelector(".safe-pill").textContent = "Static demo · no backend";
    document.querySelector(".brand").href = "./?demo=1";
  }

  function showToast(message, error = false) {
    clearTimeout(toastTimer);
    $("toast").textContent = message;
    $("toast").className = error ? "error visible" : "visible";
    toastTimer = setTimeout(() => { $("toast").className = ""; }, 2800);
  }

  async function ensureDemoData() {
    if (demoData) return;
    const response = await fetch("./demo-data.json");
    if (!response.ok) throw new Error("Static demo data could not be loaded.");
    demoData = await response.json();
  }

  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object") {
      return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
    }
    return value;
  }

  function demoSampleFor(hook) {
    const target = JSON.stringify(canonical(hook));
    return Object.values(demoData.samples).find((sample) => JSON.stringify(canonical(sample.hook)) === target);
  }

  async function demoApi(path, body) {
    await ensureDemoData();
    if (path === "/api/meta") return demoData.meta;
    if (path === "/api/document") {
      const target = JSON.stringify(canonical(body?.document));
      const sample = Object.values(demoData.samples).find((item) => JSON.stringify(canonical(item.export.document)) === target);
      if (!sample) throw new Error(demoData.notice);
      return { valid: true, document: body.document, issues: [] };
    }
    const sample = demoSampleFor(body?.hook);
    if (!sample) throw new Error(demoData.notice);
    if (path === "/api/validate") return sample.validation;
    if (path === "/api/risk") return sample.risk;
    if (path === "/api/export") {
      if (body.filename) throw new Error("Static demo export uses the bundled filename. Run the local app for custom names.");
      return sample.export;
    }
    if (path === "/api/simulate") {
      const entry = sample.simulations.find((item) => item.event.trigger === body.event?.trigger && item.event.subject === body.event?.subject);
      if (!entry) throw new Error("Static demo includes bundled event subjects only. Run the local app for arbitrary events.");
      return entry.result;
    }
    throw new Error("Unsupported static demo request.");
  }

  async function api(path, body) {
    if (demoMode) return demoApi(path, body);
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data;
    try { data = await response.json(); }
    catch { throw new Error("The local HookForge server returned an invalid response."); }
    if (!response.ok) {
      throw new Error(data.error?.message || `Request failed (${response.status}).`);
    }
    return data;
  }

  function readHook() {
    const action = currentActionType === "command"
      ? { type: "command", command: fields.command.value }
      : { type: "agent", prompt: fields.prompt.value };
    const hook = {
      name: fields.name.value,
      description: fields.description.value,
      trigger: fields.trigger.value,
      matcher: fields.matcher.value,
      action,
      enabled: fields.enabled.checked,
    };
    if (currentActionType === "command" && fields.timeout.value !== "") hook.timeout = Number(fields.timeout.value);
    return hook;
  }

  function pretty(value) { return JSON.stringify(value, null, 2) + "\n"; }

  function derivePath() {
    const requested = $("filename").value.trim();
    const source = (requested || fields.name.value.trim() || "hookforge-hook").replace(/\.json$/i, "");
    const ascii = source.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase().slice(0, 80).replace(/-+$/g, "");
    const reserved = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/;
    const safeSlug = reserved.test(ascii || "hookforge-hook") ? `hookforge-${ascii || "hook"}` : (ascii || "hookforge-hook");
    $("export-path").textContent = `.kiro/hooks/${safeSlug}.json`;
  }

  function fieldPath(path) {
    if (path === "$.name") return "name";
    if (path === "$.description") return "description";
    if (path === "$.trigger") return "trigger";
    if (path === "$.matcher") return "matcher";
    if (path === "$.timeout") return "timeout";
    if (path === "$.enabled") return "enabled";
    if (path === "$.action.command") return currentActionType === "command" ? "command" : null;
    if (path === "$.action.prompt") return currentActionType === "agent" ? "prompt" : null;
    return null;
  }

  function renderValidation(result) {
    latestValidation = result;
    const errors = result.issues.filter((issue) => issue.severity === "error");
    const warnings = result.issues.filter((issue) => issue.severity === "warning");
    const target = $("validation");
    target.className = `validation${errors.length ? " invalid" : ""}`;
    target.replaceChildren();
    const icon = document.createElement("span");
    icon.className = "validation-icon";
    icon.textContent = errors.length ? "!" : "✓";
    const body = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = errors.length ? `${errors.length} validation ${errors.length === 1 ? "error" : "errors"}` : "Valid IDE 1.x hook";
    body.append(title);
    if (errors.length) {
      const list = document.createElement("ul");
      errors.slice(0, 6).forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = issue.message;
        list.append(item);
      });
      if (errors.length > 6) {
        const item = document.createElement("li");
        item.textContent = `+ ${errors.length - 6} more`;
        list.append(item);
      }
      body.append(list);
      if (result.regex && !result.regex.ok) {
        const detail = document.createElement("p");
        detail.textContent = result.regex.message;
        body.append(detail);
      }
    } else {
      const detail = document.createElement("p");
      detail.textContent = warnings.length ? warnings.map((w) => w.message).join(" ") : "Required fields, action shape, trigger, and matcher are ready to export.";
      body.append(detail);
    }
    target.append(icon, body);
    const invalidFields = new Set(errors.map((issue) => fieldPath(issue.path)).filter(Boolean));
    Object.values(fields).forEach((field) => field.removeAttribute("aria-invalid"));
    invalidFields.forEach((name) => fields[name]?.setAttribute("aria-invalid", "true"));
    $("download-button").disabled = !result.valid;
  }

  async function refresh() {
    derivePath();
    const hook = readHook();
    $("json-preview").textContent = pretty({ version: "v1", hooks: [hook] });
    const sequence = ++validationSequence;
    clearTimeout(busyTimer);
    busyTimer = setTimeout(() => { $("schema-badge").textContent = "CHECKING…"; }, 180);
    try {
      const [validation, risk] = await Promise.all([
        api("/api/validate", { hook }),
        api("/api/risk", { hook }),
      ]);
      if (sequence !== validationSequence) return;
      clearTimeout(busyTimer);
      renderValidation(validation);
      renderRisk(risk);
      $("schema-badge").textContent = validation.valid ? "SCHEMA v1 · VALID" : "SCHEMA v1 · CHECK";
    } catch (error) {
      if (sequence !== validationSequence) return;
      clearTimeout(busyTimer);
      latestValidation = { valid: false, issues: [] };
      $("schema-badge").textContent = demoMode ? "STATIC DEMO LIMIT" : "SERVER OFFLINE";
      renderValidation({ valid: false, issues: [{ severity: "error", message: error.message }] });
      $("download-button").disabled = true;
      renderRisk({ warnings: [], summary: { high: 0, medium: 0 }, advisory: "Risk scan unavailable." });
    }
  }

  function renderRisk(risk) {
    const container = $("risk-results");
    container.replaceChildren();
    const count = risk.warnings.length;
    $("risk-count").textContent = `${count} ${count === 1 ? "flag" : "flags"}`;
    $("risk-count").className = `badge${count ? "" : " neutral"}`;
    if (!count) {
      const empty = document.createElement("div");
      empty.className = "risk-empty";
      empty.textContent = currentActionType === "agent" ? "Agent prompt selected — command scan does not apply." : (risk.advisory?.startsWith("Heuristic") ? "No destructive, network, or privileged patterns detected." : risk.advisory || "Risk scan unavailable.");
      container.append(empty);
      return;
    }
    risk.warnings.forEach((warning) => {
      const item = document.createElement("div");
      item.className = `risk-item ${warning.severity}`;
      const title = document.createElement("strong");
      title.textContent = `${warning.severity.toUpperCase()} · ${warning.title}`;
      const evidence = document.createElement("code");
      evidence.textContent = warning.evidence;
      const note = document.createElement("small");
      note.textContent = warning.message;
      item.append(title, evidence, note);
      container.append(item);
    });
    const advisory = document.createElement("small");
    advisory.textContent = risk.advisory;
    advisory.style.cssText = "display:block;color:var(--dim);font-size:9.5px;margin-top:13px";
    container.append(advisory);
  }

  function updateActionType() {
    currentActionType = document.querySelector('input[name="action-type"]:checked').value;
    const command = currentActionType === "command";
    $("command-field").hidden = !command;
    $("prompt-field").hidden = command;
    fields.command.disabled = !command;
    fields.prompt.disabled = command;
    fields.timeout.disabled = !command;
    $("action-label").textContent = command ? "Command *" : "Agent prompt *";
    refresh();
  }

  function updateTrigger() {
    const trigger = triggers.find((entry) => entry.name === fields.trigger.value);
    if (!trigger) return;
    fields.matcher.disabled = !trigger.matcher;
    fields.matcher.placeholder = trigger.matcher ? (trigger.subject === "tool name" ? "write" : trigger.subject === "prompt text" ? "refactor|review" : "\\.py$") : "Not used for this trigger";
    $("matcher-label").textContent = trigger.subject === "tool name" ? "Tool matcher" : "Matcher regex";
    $("matcher-help").textContent = trigger.matcher
      ? (trigger.subject === "tool name" ? "Tool ID, category, source selector, wildcard, or regex." : `Regex searched against ${trigger.subject}. Blank matches all.`)
      : `${trigger.name} has no matcher subject; leave this blank.`;
    $("trigger-help").textContent = trigger.command_only ? "Command actions only. Runs before a permission prompt." : trigger.blocking ? "A command exit code 2 can block this event." : "This trigger cannot be blocked by hook exit codes.";
    if (!trigger.matcher) fields.matcher.value = "";
    syncEventTrigger();
  }

  function syncEventTrigger() {
    $("event-trigger").value = fields.trigger.value;
    updateEventSubject();
  }

  function updateEventSubject() {
    const trigger = triggers.find((entry) => entry.name === $("event-trigger").value);
    if (!trigger) return;
    const tool = trigger.subject === "tool name";
    if (!trigger.subject) $("event-subject").value = "";
    $("event-subject-label").textContent = tool ? "Tool name" : trigger.subject === "prompt text" ? "Prompt text" : trigger.subject === "file path" ? "File path" : "Event subject";
    $("event-subject").placeholder = tool ? "fs_write" : trigger.subject === "prompt text" ? "Please refactor this module" : trigger.subject === "file path" ? "src/example.py" : "(no matcher subject)";
    $("event-subject").disabled = !trigger.subject;
    $("event-subject-help").textContent = trigger.subject ? `Synthetic ${trigger.subject}; no real event is emitted.` : "This trigger does not use a matcher subject.";
  }

  function renderTemplates() {
    const grid = $("template-grid");
    grid.replaceChildren();
    templates.forEach((template, index) => {
      const card = document.createElement("article");
      card.className = "template-card";
      const number = document.createElement("div");
      number.className = "template-number";
      number.textContent = `0${index + 1} / 03`;
      const eyebrow = document.createElement("p");
      eyebrow.className = "eyebrow";
      eyebrow.textContent = template.eyebrow;
      const title = document.createElement("h3");
      title.textContent = template.title;
      const description = document.createElement("p");
      description.textContent = template.description;
      const trigger = document.createElement("div");
      trigger.className = "template-trigger";
      trigger.textContent = template.hook.trigger;
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Load template →";
      button.addEventListener("click", () => loadHook(template.hook));
      card.append(number, eyebrow, title, description, trigger, button);
      grid.append(card);
    });
  }

  function loadHook(hook) {
    fields.name.value = hook.name;
    fields.description.value = hook.description || "";
    fields.trigger.value = hook.trigger;
    fields.matcher.value = hook.matcher || "";
    fields.command.value = hook.action.type === "command" ? hook.action.command : "";
    fields.prompt.value = hook.action.type === "agent" ? hook.action.prompt : "";
    fields.timeout.value = String(hook.timeout ?? 60);
    fields.enabled.checked = hook.enabled !== false;
    document.querySelector(`input[name="action-type"][value="${hook.action.type}"]`).checked = true;
    $("filename").value = "";
    currentActionType = hook.action.type;
    if (demoMode && demoData) {
      const sample = demoSampleFor(hook);
      if (sample) {
        $("event-trigger").value = sample.default_event.trigger;
        $("event-subject").value = sample.default_event.subject;
      }
    }
    updateActionType();
    updateTrigger();
    $("builder").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Hook loaded. Make it yours.");
  }

  async function importHook(file) {
    if (!file) return;
    if (file.size > 65_536) {
      showToast("Hook files must be at most 64 KiB.", true);
      return;
    }
    try {
      const document = JSON.parse(await file.text());
      const result = await api("/api/document", { document });
      if (!result.valid) {
        showToast(result.issues?.[0]?.message || "The hook file is invalid.", true);
        return;
      }
      if (result.document.hooks.length !== 1) {
        showToast("Import a file containing exactly one hook.", true);
        return;
      }
      loadHook(result.document.hooks[0]);
      showToast("Hook imported. Review it before export.");
    } catch (error) {
      showToast(error.message || "The JSON file could not be imported.", true);
    }
  }

  function renderSimulation(result) {
    const container = $("simulation-result");
    container.replaceChildren();
    const fired = result.fired === true;
    const blocked = result.status === "simulation_blocked" || result.status === "invalid";
    const verdict = document.createElement("div");
    verdict.className = `sim-verdict${fired ? "" : blocked ? " blocked" : " no-fire"}`;
    const symbol = document.createElement("div");
    symbol.className = "verdict-symbol";
    symbol.textContent = fired ? "→" : blocked ? "!" : "–";
    const copy = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = fired ? "Hook would fire" : blocked ? "Simulation stopped safely" : "Hook would not fire";
    const reason = document.createElement("p");
    reason.textContent = result.reason;
    copy.append(heading, reason);
    verdict.append(symbol, copy);
    container.append(verdict);

    const flow = document.createElement("div");
    flow.className = "decision-flow";
    const steps = [
      ["Config valid", result.status !== "invalid"],
      ["Enabled", result.status !== "disabled"],
      ["Trigger matches", result.status !== "trigger_mismatch"],
      ["Matcher passes", fired || result.status === "no_match" ? fired : result.status === "simulation_blocked" ? false : null],
    ];
    steps.forEach(([label, pass], index) => {
      if (index) {
        const arrow = document.createElement("span");
        arrow.className = "flow-arrow";
        arrow.textContent = "→";
        flow.append(arrow);
      }
      const step = document.createElement("span");
      step.className = `flow-step${pass === true ? " pass" : pass === false ? " fail" : ""}`;
      step.textContent = `${pass === true ? "✓" : pass === false ? "×" : "·"} ${label}`;
      flow.append(step);
    });
    container.append(flow);

    if (result.action_requested) {
      const box = document.createElement("div");
      box.className = "action-request";
      const bar = document.createElement("div");
      bar.className = "action-request-heading";
      const type = document.createElement("span");
      type.textContent = `ACTION REQUEST · ${result.action_requested.type.toUpperCase()}`;
      const inert = document.createElement("span");
      inert.textContent = "EXECUTED: FALSE";
      bar.append(type, inert);
      const pre = document.createElement("pre");
      pre.textContent = pretty(result.action_requested);
      box.append(bar, pre);
      container.append(box);
    }
    const note = document.createElement("p");
    note.className = "sim-footnote";
    note.textContent = result.note || "Dry run only. No action was executed.";
    container.append(note);
    if (result.issues?.length) {
      const list = document.createElement("ul");
      list.style.cssText = "color:var(--red);font-size:11px;margin-top:14px";
      result.issues.forEach((issue) => {
        const item = document.createElement("li");
        item.textContent = issue.message;
        list.append(item);
      });
      container.append(list);
    }
  }

  async function simulate() {
    const button = $("simulate-button");
    button.disabled = true;
    button.textContent = "Simulating…";
    try {
      const result = await api("/api/simulate", { hook: readHook(), event: { trigger: $("event-trigger").value, subject: $("event-subject").value } });
      renderSimulation(result);
    } catch (error) {
      showToast(error.message, true);
    } finally {
      button.disabled = false;
      button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 10 7-10 7V5Z"/></svg>Simulate event';
    }
  }

  async function download() {
    try {
      const result = await api("/api/export", { hook: readHook(), filename: $("filename").value });
      if (!result.ok) throw new Error(result.errors?.[0]?.message || "Fix validation errors before exporting.");
      const blob = new Blob([result.content], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showToast(`Downloaded ${result.filename}`);
    } catch (error) { showToast(error.message, true); }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText($("json-preview").textContent);
      showToast("JSON copied to clipboard.");
    } catch { showToast("Clipboard unavailable. Select the preview text to copy.", true); }
  }

  async function initialize() {
    try {
      const meta = await api("/api/meta");
      triggers = meta.triggers;
      templates = meta.templates;
      triggers.forEach((trigger) => {
        $("trigger").append(new Option(trigger.name, trigger.name));
        $("event-trigger").append(new Option(trigger.name, trigger.name));
      });
      renderTemplates();
      loadHook(templates[0].hook);
      $("builder").scrollIntoView({ block: "start" });
    } catch (error) {
      showToast(error.message, true);
      $("validation").textContent = `HookForge server unavailable: ${error.message}`;
    }
  }

  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
  document.querySelectorAll('input[name="action-type"]').forEach((radio) => radio.addEventListener("change", updateActionType));
  fields.trigger.addEventListener("change", updateTrigger);
  $("event-trigger").addEventListener("change", updateEventSubject);
  $("filename").addEventListener("input", derivePath);
  $("import-button").addEventListener("click", () => $("import-file").click());
  $("import-file").addEventListener("change", (event) => {
    importHook(event.target.files[0]);
    event.target.value = "";
  });
  $("reset-button").addEventListener("click", () => templates[0] && loadHook(templates[0].hook));
  $("simulate-button").addEventListener("click", simulate);
  $("download-button").addEventListener("click", download);
  $("copy-button").addEventListener("click", copy);
  initialize();
})();
