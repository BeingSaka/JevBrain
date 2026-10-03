/**
 * JevBrain Decision Console V1 - Application Logic
 * Zero-cost, pure vanilla JavaScript.
 * Gracefully renders JevBrain evaluation data with safe degradation for missing fields.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const sourceSelect = document.getElementById("sourceSelect");
  const refreshBtn = document.getElementById("refreshBtn");
  const fileInput = document.getElementById("fileInput");
  const pasteBtn = document.getElementById("pasteBtn");
  const pasteModal = document.getElementById("pasteModal");
  const closePasteModal = document.getElementById("closePasteModal");
  const cancelPasteBtn = document.getElementById("cancelPasteBtn");
  const submitPasteBtn = document.getElementById("submitPasteBtn");
  const pasteTextarea = document.getElementById("pasteTextarea");
  const pasteError = document.getElementById("pasteError");
  const helpBtn = document.getElementById("helpBtn");
  const helpModal = document.getElementById("helpModal");
  const closeHelpModal = document.getElementById("closeHelpModal");
  const closeHelpBtn = document.getElementById("closeHelpBtn");
  const copyOutputBtn = document.getElementById("copyOutputBtn");
  const footerMeta = document.getElementById("footerMeta");

  // Top Status elements
  const topStatusBar = document.getElementById("topStatusBar");
  const statusBadge = document.getElementById("statusBadge");
  const metaRunId = document.getElementById("metaRunId");
  const metaProfile = document.getElementById("metaProfile");
  const metaTaskType = document.getElementById("metaTaskType");
  const repairActivityBadge = document.getElementById("repairActivityBadge");

  // Final Decision elements
  const finalDecisionTag = document.getElementById("finalDecisionTag");
  const finalReason = document.getElementById("finalReason");
  const finalOutput = document.getElementById("finalOutput");
  const outputCharCount = document.getElementById("outputCharCount");

  // Operational Metrics
  const metricRepairs = document.getElementById("metricRepairs");
  const metricRetries = document.getElementById("metricRetries");
  const metricLatency = document.getElementById("metricLatency");
  const metricLatencySub = document.getElementById("metricLatencySub");
  const metricCost = document.getElementById("metricCost");
  const metricChecks = document.getElementById("metricChecks");
  const metricPrimaryFailure = document.getElementById("metricPrimaryFailure");

  // Semantic Metrics
  const semNoulVal = document.getElementById("semNoulVal");
  const semNoulConf = document.getElementById("semNoulConf");
  const semNoulReason = document.getElementById("semNoulReason");
  const semNoulBadge = document.getElementById("semNoulBadge");

  const semChoiceVal = document.getElementById("semChoiceVal");
  const semChoiceConf = document.getElementById("semChoiceConf");
  const semChoiceReason = document.getElementById("semChoiceReason");
  const semChoiceBadge = document.getElementById("semChoiceBadge");

  const semScoreVal = document.getElementById("semScoreVal");
  const semScoreConf = document.getElementById("semScoreConf");
  const semScoreReason = document.getElementById("semScoreReason");
  const semScoreBadge = document.getElementById("semScoreBadge");

  const semEvidenceVal = document.getElementById("semEvidenceVal");
  const semEvidenceConf = document.getElementById("semEvidenceConf");
  const semEvidenceReason = document.getElementById("semEvidenceReason");
  const semEvidenceBadge = document.getElementById("semEvidenceBadge");

  // Pills
  const pillsTriggeredRules = document.getElementById("pillsTriggeredRules");
  const pillsFailedDimensions = document.getElementById("pillsFailedDimensions");

  // Before -> After
  const repairStatusBadge = document.getElementById("repairStatusBadge");
  const noRepairBanner = document.getElementById("noRepairBanner");
  const repairDiffContent = document.getElementById("repairDiffContent");
  const diffRepairCount = document.getElementById("diffRepairCount");
  const diffRepairReason = document.getElementById("diffRepairReason");
  const beforeOutput = document.getElementById("beforeOutput");
  const afterOutput = document.getElementById("afterOutput");
  const feedbackRulesList = document.getElementById("feedbackRulesList");

  // History Table
  const historyTableBody = document.getElementById("historyTableBody");

  let currentData = null;

  // Initialize
  loadSource("api-result");

  // Event Listeners
  sourceSelect.addEventListener("change", (e) => {
    loadSource(e.target.value);
  });

  refreshBtn.addEventListener("click", () => {
    loadSource(sourceSelect.value);
  });

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const json = JSON.parse(event.target.result);
        renderEvaluationResult(json, `File: ${file.name}`);
      } catch (err) {
        alert("Failed to parse JSON file: " + err.message);
      }
    };
    reader.readAsText(file);
    fileInput.value = "";
  });

  pasteBtn.addEventListener("click", () => {
    pasteModal.classList.remove("hidden");
    pasteTextarea.value = "";
    pasteError.classList.add("hidden");
    pasteTextarea.focus();
  });

  closePasteModal.addEventListener("click", () => pasteModal.classList.add("hidden"));
  cancelPasteBtn.addEventListener("click", () => pasteModal.classList.add("hidden"));

  // Help Modal listeners
  helpBtn.addEventListener("click", () => {
    helpModal.classList.remove("hidden");
  });
  closeHelpModal.addEventListener("click", () => helpModal.classList.add("hidden"));
  closeHelpBtn.addEventListener("click", () => helpModal.classList.add("hidden"));

  submitPasteBtn.addEventListener("click", () => {
    const raw = pasteTextarea.value.trim();
    if (!raw) {
      showPasteError("Please enter JSON content");
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      pasteModal.classList.add("hidden");
      renderEvaluationResult(parsed, "Pasted JSON");
    } catch (e) {
      showPasteError("Invalid JSON: " + e.message);
    }
  });

  copyOutputBtn.addEventListener("click", () => {
    const text = finalOutput.textContent;
    if (text && text !== "--") {
      navigator.clipboard.writeText(text).then(() => {
        const originalText = copyOutputBtn.textContent;
        copyOutputBtn.textContent = "Copied!";
        setTimeout(() => { copyOutputBtn.textContent = originalText; }, 1800);
      });
    }
  });

  function showPasteError(msg) {
    pasteError.textContent = msg;
    pasteError.classList.remove("hidden");
  }

  // Load Source Handler
  function loadSource(sourceKey) {
    let url = "";
    let label = "";

    switch (sourceKey) {
      case "api-result":
        url = "/api/result";
        label = "result.json";
        break;
      case "fixture-pass":
        url = "fixtures/sample_pass.json";
        label = "Sample PASS (fixtures/sample_pass.json)";
        break;
      case "fixture-repair":
        url = "fixtures/sample_repair.json";
        label = "Sample REPAIR (fixtures/sample_repair.json)";
        break;
      case "fixture-human-review":
        url = "fixtures/sample_human_review.json";
        label = "Sample HUMAN REVIEW (fixtures/sample_human_review.json)";
        break;
      default:
        url = "/api/result";
        label = "result.json";
    }

    footerMeta.textContent = `Loading ${label}...`;

    fetch(url)
      .then((res) => {
        if (!res.ok) {
          // If server /api/result fails, try static relative result.json fallback
          if (sourceKey === "api-result") {
            return fetch("result.json");
          }
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }
        return res.json();
      })
      .then((data) => {
        renderEvaluationResult(data, label);
      })
      .catch((err) => {
        console.warn(`Could not fetch ${url}:`, err);
        // Fall back to sample pass fixture if result.json was not accessible via static server
        if (sourceKey === "api-result") {
          console.info("Falling back to local fixture sample_pass.json (Static-only mode detected)");
          fetch("fixtures/sample_pass.json")
            .then(r => r.json())
            .then(data => renderEvaluationResult(data, "Default Sample PASS (Static-Only Mode: run 'python dashboard/server.py' for live result.json)"))
            .catch(() => showEmptyStateError(`Could not load ${label}. Running in static-only mode? Run 'python dashboard/server.py' for full live integration.`));
        } else {
          showEmptyStateError(`Failed to load ${label}: ${err.message}`);
        }
      });
  }

  function showEmptyStateError(msg) {
    footerMeta.textContent = msg;
    finalReason.textContent = msg;
    finalOutput.textContent = "--";
    outputCharCount.textContent = "0 chars";
  }

  // Main Render Function
  function renderEvaluationResult(data, sourceLabel) {
    currentData = data;
    footerMeta.textContent = `Loaded from ${sourceLabel || "Active Data"}`;

    // Normalize top-level vs event data
    const decision = (data.decision || data.policy_decision || "UNKNOWN").toUpperCase();
    const reason = data.reason || (data.history && data.history.length > 0 ? data.history[data.history.length - 1].reason : "--");
    const finalOut = data.final_output !== undefined ? data.final_output : (data.candidate_output || "--");
    const runId = data.run_id || (data.history && data.history[0] ? data.history[0].run_id : "N/A");
    const repairsCount = typeof data.repairs === "number" ? data.repairs : (data.retry_count || 0);

    const history = Array.isArray(data.history) && data.history.length > 0
      ? data.history
      : [data];

    const lastEvent = history[history.length - 1] || {};
    const firstEvent = history[0] || {};

    // 1. TOP STATUS
    applyTopStatus(decision, repairsCount, runId, lastEvent);

    // 2. FINAL DECISION
    applyFinalDecision(decision, reason, finalOut);

    // 3. EVALUATION METRICS
    applyMetrics(data, lastEvent, repairsCount);

    // 4. BEFORE -> AFTER (Repair Diff)
    applyBeforeAfterDiff(data, history, repairsCount);

    // 5. EVALUATION HISTORY
    renderHistoryTable(history);
  }

  function applyTopStatus(decision, repairsCount, runId, lastEvent) {
    topStatusBar.className = "top-status-bar";
    statusBadge.textContent = decision;

    if (decision === "PASS") {
      topStatusBar.classList.add("status-pass");
    } else if (decision === "REPAIR" || decision === "REVISE") {
      topStatusBar.classList.add("status-repair");
    } else {
      topStatusBar.classList.add("status-review");
    }

    metaRunId.textContent = runId;
    metaProfile.textContent = lastEvent.evaluation_profile || "universal";
    metaTaskType.textContent = lastEvent.task_type || "text";

    if (repairsCount > 0) {
      repairActivityBadge.textContent = `${repairsCount} REPAIR${repairsCount > 1 ? "S" : ""}`;
      repairActivityBadge.style.color = "#388bfd";
      repairActivityBadge.style.borderColor = "rgba(56, 139, 253, 0.4)";
      repairActivityBadge.style.backgroundColor = "rgba(56, 139, 253, 0.15)";
    } else {
      repairActivityBadge.textContent = "0 REPAIRS";
      repairActivityBadge.style.color = "var(--text-muted)";
      repairActivityBadge.style.borderColor = "var(--border-color)";
      repairActivityBadge.style.backgroundColor = "var(--bg-subtle)";
    }
  }

  function applyFinalDecision(decision, reason, finalOut) {
    finalDecisionTag.textContent = decision;
    finalDecisionTag.className = "tag-decision";

    if (decision === "PASS") {
      finalDecisionTag.classList.add("tag-pass");
    } else if (decision === "REPAIR" || decision === "REVISE") {
      finalDecisionTag.classList.add("tag-repair");
    } else {
      finalDecisionTag.classList.add("tag-review");
    }

    finalReason.textContent = reason;
    finalOutput.textContent = finalOut;
    outputCharCount.textContent = `${finalOut.length} chars`;
  }

  function applyMetrics(data, lastEvent, repairsCount) {
    // Repairs & Retries
    metricRepairs.textContent = repairsCount;
    metricRetries.textContent = lastEvent.retry_count !== undefined ? lastEvent.retry_count : repairsCount;

    // Latency
    const latencyMs = lastEvent.evaluation_latency_ms !== undefined
      ? lastEvent.evaluation_latency_ms
      : (lastEvent.elapsed_seconds ? Math.round(lastEvent.elapsed_seconds * 1000) : null);

    if (latencyMs !== null) {
      metricLatency.textContent = `${latencyMs} ms`;
      metricLatencySub.textContent = `${(latencyMs / 1000).toFixed(2)}s elapsed`;
    } else {
      metricLatency.textContent = "--";
      metricLatencySub.textContent = "Evaluation time";
    }

    // Cost
    const costUsd = lastEvent.evaluation_cost_usd !== undefined
      ? lastEvent.evaluation_cost_usd
      : lastEvent.estimated_jev_usd;

    if (costUsd !== undefined && costUsd !== null) {
      metricCost.textContent = `$${Number(costUsd).toFixed(6)}`;
    } else {
      metricCost.textContent = "--";
    }

    // Checks performed
    const checks = lastEvent.checks_performed !== undefined ? lastEvent.checks_performed : "--";
    metricChecks.textContent = checks;

    // Primary failure
    const primary = lastEvent.primary_failure || (lastEvent.semantic_evaluation && lastEvent.semantic_evaluation.choice ? lastEvent.semantic_evaluation.choice.value : "none");
    metricPrimaryFailure.textContent = primary;
    if (primary !== "none" && primary !== "--") {
      metricPrimaryFailure.style.color = "#ff7b72";
    } else {
      metricPrimaryFailure.style.color = "var(--text-main)";
    }

    // Semantic evaluation details
    const sem = data.semantic_evaluation || lastEvent.semantic_evaluation || null;
    applySemanticDetails(sem);

    // Rule Findings & Failed Dimensions
    applyFindingsPills(lastEvent);
  }

  function applySemanticDetails(sem) {
    if (!sem) {
      // Degrade safely when semantic_evaluation is absent
      semNoulVal.textContent = "--";
      semNoulConf.textContent = "--";
      semNoulReason.textContent = "Semantic pipeline not run or metrics omitted";
      semNoulBadge.textContent = "N/A";
      semNoulBadge.className = "dim-badge pill-none";

      semChoiceVal.textContent = "--";
      semChoiceConf.textContent = "--";
      semChoiceReason.textContent = "Semantic pipeline not run or metrics omitted";
      semChoiceBadge.textContent = "N/A";
      semChoiceBadge.className = "dim-badge pill-none";

      semScoreVal.textContent = "--";
      semScoreConf.textContent = "--";
      semScoreReason.textContent = "Semantic pipeline not run or metrics omitted";
      semScoreBadge.textContent = "N/A";
      semScoreBadge.className = "dim-badge pill-none";

      semEvidenceVal.textContent = "--";
      semEvidenceConf.textContent = "--";
      semEvidenceReason.textContent = "Evidence resolvability not recorded";
      semEvidenceBadge.textContent = "N/A";
      semEvidenceBadge.className = "dim-badge pill-none";
      return;
    }

    // Noul
    if (sem.noul) {
      semNoulVal.textContent = typeof sem.noul.value === "number" ? sem.noul.value.toFixed(2) : sem.noul.value;
      semNoulConf.textContent = typeof sem.noul.confidence === "number" ? `${Math.round(sem.noul.confidence * 100)}%` : "--";
      semNoulReason.textContent = sem.noul.reason || "--";
      const pass = sem.noul.value >= 0.90;
      semNoulBadge.textContent = pass ? "PASS" : "DEFECT";
      semNoulBadge.className = `dim-badge ${pass ? "tag-pass" : "tag-review"}`;
    }

    // Choice
    if (sem.choice) {
      semChoiceVal.textContent = sem.choice.value || "--";
      semChoiceConf.textContent = typeof sem.choice.confidence === "number" ? `${Math.round(sem.choice.confidence * 100)}%` : "--";
      semChoiceReason.textContent = sem.choice.reason || "--";
      const pass = sem.choice.value === "none";
      semChoiceBadge.textContent = pass ? "CLEAR" : "FLAGGED";
      semChoiceBadge.className = `dim-badge ${pass ? "tag-pass" : "tag-review"}`;
    }

    // Score
    if (sem.score) {
      semScoreVal.textContent = typeof sem.score.value === "number" ? sem.score.value.toFixed(2) : sem.score.value;
      semScoreConf.textContent = typeof sem.score.confidence === "number" ? `${Math.round(sem.score.confidence * 100)}%` : "--";
      semScoreReason.textContent = sem.score.reason || "--";
      const pass = sem.score.value >= 3.5;
      semScoreBadge.textContent = pass ? "READY" : "REVISE";
      semScoreBadge.className = `dim-badge ${pass ? "tag-pass" : "tag-review"}`;
    }

    // Evidence Resolvability
    if (sem.evidence_resolvable) {
      semEvidenceVal.textContent = typeof sem.evidence_resolvable.value === "number" ? sem.evidence_resolvable.value.toFixed(2) : sem.evidence_resolvable.value;
      semEvidenceConf.textContent = typeof sem.evidence_resolvable.confidence === "number" ? `${Math.round(sem.evidence_resolvable.confidence * 100)}%` : "--";
      semEvidenceReason.textContent = sem.evidence_resolvable.reason || "--";
      const pass = sem.evidence_resolvable.value >= 0.50;
      semEvidenceBadge.textContent = pass ? "RESOLVABLE" : "UNRESOLVED";
      semEvidenceBadge.className = `dim-badge ${pass ? "tag-pass" : "tag-review"}`;
    } else {
      semEvidenceVal.textContent = "--";
      semEvidenceConf.textContent = "--";
      semEvidenceReason.textContent = "Evidence resolvability dimension not present in output";
      semEvidenceBadge.textContent = "Omitted";
      semEvidenceBadge.className = "dim-badge pill-none";
    }
  }

  function applyFindingsPills(lastEvent) {
    // Triggered rules
    const rules = lastEvent.triggered_rule_ids || lastEvent.rules_triggered || [];
    pillsTriggeredRules.innerHTML = "";
    if (rules.length === 0) {
      pillsTriggeredRules.innerHTML = '<span class="pill pill-none">None</span>';
    } else {
      rules.forEach(r => {
        const span = document.createElement("span");
        span.className = "pill pill-rule";
        span.textContent = r;
        pillsTriggeredRules.appendChild(span);
      });
    }

    // Failed dimensions
    const dims = lastEvent.failed_dimensions || [];
    pillsFailedDimensions.innerHTML = "";
    if (dims.length === 0) {
      pillsFailedDimensions.innerHTML = '<span class="pill pill-none">None</span>';
    } else {
      dims.forEach(d => {
        const span = document.createElement("span");
        span.className = "pill pill-dim";
        span.textContent = d;
        pillsFailedDimensions.appendChild(span);
      });
    }
  }

  // 4. BEFORE -> AFTER DIFF
  function applyBeforeAfterDiff(data, history, repairsCount) {
    const hasRepair = repairsCount > 0 || history.some(h => h.repair_performed || h.repair_requested);

    if (!hasRepair) {
      repairStatusBadge.textContent = "No repair performed";
      repairStatusBadge.style.color = "var(--pass-color)";
      noRepairBanner.classList.remove("hidden");
      repairDiffContent.classList.add("hidden");
      return;
    }

    // Repair occurred
    repairStatusBadge.textContent = `${repairsCount} Repair Cycle${repairsCount > 1 ? "s" : ""}`;
    repairStatusBadge.style.color = "#388bfd";
    noRepairBanner.classList.add("hidden");
    repairDiffContent.classList.remove("hidden");

    diffRepairCount.textContent = repairsCount;

    // Determine initial defect reason from first event that requested repair
    const repairEvent = history.find(h => h.repair_requested || h.policy_decision === "REPAIR" || h.policy_decision === "REVISE") || history[0];
    diffRepairReason.textContent = repairEvent ? (repairEvent.reason || "--") : "--";

    // Candidate outputs
    const prevCandidate = data.previous_candidate || (history[0] && history[0].previous_candidate) || null;
    const finalCandidate = data.final_output || data.candidate_output || "--";

    if (prevCandidate) {
      beforeOutput.textContent = prevCandidate;
      beforePanelSub.textContent = "Pre-revision candidate";
    } else {
      // If previous candidate raw text was not retained, show candidate SHA and note
      const sha = history[0] && history[0].candidate_sha256 ? history[0].candidate_sha256.substring(0, 16) + "..." : "Initial";
      beforeOutput.textContent = `[Candidate before revision - SHA256: ${sha}]\nCandidate output was corrected by worker during repair cycle.`;
      beforePanelSub.textContent = "Pre-revision candidate (SHA referenced)";
    }

    afterOutput.textContent = finalCandidate;
    afterPanelSub.textContent = "Delivered candidate";

    // Triggered repair feedback rules
    feedbackRulesList.innerHTML = "";
    const findings = (repairEvent && repairEvent.rule_findings) ? repairEvent.rule_findings : [];
    const triggeredFindings = findings.filter(f => f.status === "triggered" && f.repair_instruction);

    if (triggeredFindings.length > 0) {
      triggeredFindings.forEach(f => {
        const item = document.createElement("div");
        item.className = "feedback-rule-item";
        item.innerHTML = `
          <span class="rule-id-tag">[${f.rule_id}]</span>
          <span class="rule-inst">${escapeHtml(f.repair_instruction)}</span>
        `;
        feedbackRulesList.appendChild(item);
      });
      document.getElementById("repairRulesFeedbackBlock").classList.remove("hidden");
    } else {
      // Check if primary failure target exists
      const prim = repairEvent ? repairEvent.primary_failure : null;
      if (prim && prim !== "none") {
        const item = document.createElement("div");
        item.className = "feedback-rule-item";
        item.innerHTML = `<span class="rule-id-tag">[PRIMARY]</span> <span class="rule-inst">Corrected primary defect: ${escapeHtml(prim)}</span>`;
        feedbackRulesList.appendChild(item);
        document.getElementById("repairRulesFeedbackBlock").classList.remove("hidden");
      } else {
        document.getElementById("repairRulesFeedbackBlock").classList.add("hidden");
      }
    }
  }

  // 5. EVALUATION HISTORY TABLE
  function renderHistoryTable(history) {
    historyTableBody.innerHTML = "";

    if (!history || history.length === 0) {
      historyTableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No history events available</td></tr>';
      return;
    }

    history.forEach((evt, idx) => {
      const tr = document.createElement("tr");

      const attemptNum = evt.retry_count !== undefined ? evt.retry_count : idx;
      const dec = (evt.policy_decision || evt.decision || "--").toUpperCase();
      const reason = evt.reason || "--";

      // Latency
      const lat = evt.evaluation_latency_ms !== undefined
        ? `${evt.evaluation_latency_ms} ms`
        : (evt.elapsed_seconds ? `${Math.round(evt.elapsed_seconds * 1000)} ms` : "--");

      // Cost
      const costVal = evt.evaluation_cost_usd !== undefined ? evt.evaluation_cost_usd : evt.estimated_jev_usd;
      const cost = costVal !== undefined && costVal !== null ? `$${Number(costVal).toFixed(6)}` : "--";

      // Rules
      const rules = evt.triggered_rule_ids || evt.rules_triggered || [];
      const rulesHtml = rules.length > 0
        ? rules.map(r => `<span class="pill pill-rule">${escapeHtml(r)}</span>`).join(" ")
        : '<span class="text-muted">None</span>';

      // Dimensions
      const dims = evt.failed_dimensions || [];
      const dimsHtml = dims.length > 0
        ? dims.map(d => `<span class="pill pill-dim">${escapeHtml(d)}</span>`).join(" ")
        : '<span class="text-muted">None</span>';

      // Tag class
      let tagClass = "tag-pass";
      if (dec === "REPAIR" || dec === "REVISE") tagClass = "tag-repair";
      else if (dec === "HUMAN REVIEW") tagClass = "tag-review";

      tr.innerHTML = `
        <td class="mono"><strong>#${attemptNum}</strong></td>
        <td><span class="tag-decision ${tagClass}">${escapeHtml(dec)}</span></td>
        <td>${escapeHtml(reason)}</td>
        <td>${rulesHtml}</td>
        <td>${dimsHtml}</td>
        <td class="mono">${lat}</td>
        <td class="mono">${cost}</td>
      `;

      historyTableBody.appendChild(tr);
    });
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
