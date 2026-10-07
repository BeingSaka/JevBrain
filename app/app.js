const mindspace = document.getElementById('mindspace');
const heroButton = document.getElementById('jev-hero-button');
const characterNode = document.getElementById('jev-character');
const idlePromptGroup = document.getElementById('idle-prompt-group');
const activePanel = document.getElementById('active-panel');
const composerView = document.getElementById('composer-view');

const form = document.getElementById('jev-form');
const requestInput = document.getElementById('request_text');
const button = document.getElementById('evaluate-button');
const processingSection = document.getElementById('processing-section');
const elapsedTimeNode = document.getElementById('elapsed-time');
const messageSection = document.getElementById('message-section');
const messageTitle = document.getElementById('message-title');
const messageContent = document.getElementById('message-content');
const messageIcon = document.getElementById('message-icon');
const resultSection = document.getElementById('result-section');

const historicalBanner = document.getElementById('historical-banner');
const historicalTimeNode = document.getElementById('historical-time');
const historicalRequestNode = document.getElementById('historical-request-display');

const decisionPanel = document.getElementById('decision-panel');
const decisionNode = document.getElementById('decision-value');
const decisionIcon = document.getElementById('decision-icon');
const jobSignatureNode = document.getElementById('job-signature');
const reasonNode = document.getElementById('reason-value');
const acceptanceProbabilityNode = document.getElementById('acceptance-probability-value');
const evaluationConfidenceNode = document.getElementById('evaluation-confidence-value');
const repairCountNode = document.getElementById('repair-count-value');
const failedDimensionsNode = document.getElementById('failed-dimensions-value');
const concernsNode = document.getElementById('concerns-value');
const finalOutputNode = document.getElementById('final-output-value');
const jobDurationNode = document.getElementById('job-duration-value');
const detailsNode = document.getElementById('technical-details');

const historyToggleButton = document.getElementById('history-toggle-button');
const historyDrawer = document.getElementById('history-drawer');
const historyBackdrop = document.getElementById('history-backdrop');
const closeHistoryButton = document.getElementById('close-history-button');
const clearHistoryButton = document.getElementById('clear-history-button');
const historyList = document.getElementById('history-list');
const historyCountNode = document.getElementById('history-count');

const JEV_ASSETS = {
  idle: 'assets/jev/jev_idle.png',
  attentive: 'assets/jev/jev_attentive.png',
  checking: 'assets/jev/jev_checking.png',
  human_review: 'assets/jev/jev_human_review.png',
  failure: 'assets/jev/jev_failure.png',
};

const HISTORY_STORAGE_KEY = 'jev.v0.2.history';
const MAX_HISTORY_ENTRIES = 50;

let inFlight = false;
let elapsedTimer = null;
let startedAt = 0;
let lastSavedFingerprint = '';
let activeEvaluation = null;

function setCharacterState(state) {
  if (characterNode && JEV_ASSETS[state]) {
    characterNode.src = JEV_ASSETS[state];
    characterNode.dataset.state = state;
  }
}

function getStoredHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    console.warn('Failed to read Jev history from localStorage:', err);
    return [];
  }
}

function persistHistory(entries) {
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
  } catch (err) {
    console.warn('Failed to write Jev history to localStorage:', err);
  }
}

function generateHistoryId() {
  return 'jev-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
}

function getDecisionCategory(rawDecision) {
  const upper = typeof rawDecision === 'string' ? rawDecision.trim().toUpperCase() : '';
  if (upper === 'PASS') return 'PASS';
  if (upper === 'HUMAN REVIEW') return 'HUMAN_REVIEW';
  if (['FAIL', 'FAILED', 'REJECTED', 'FAILURE'].includes(upper)) return 'FAILURE';
  return 'NEUTRAL';
}

function updateHistoryBadgeCount(count) {
  if (historyCountNode) {
    const total = typeof count === 'number' ? count : getStoredHistory().length;
    historyCountNode.textContent = String(total);
  }
}

function saveEvaluationToHistory(data, requestText) {
  if (!data || !data.ok || !data.result) return null;
  const result = data.result || {};
  const rawDecision = typeof result.decision === 'string' && result.decision
    ? result.decision.trim()
    : 'not provided';

  const cleanRequest = typeof requestText === 'string' ? requestText.trim() : '';
  if (!cleanRequest) return null;

  const durationMs = Number(data.job_duration_ms);
  const noulValue = result.semantic_evaluation?.noul?.value;
  const noulConfidence = result.semantic_evaluation?.noul?.confidence;
  const concerns = result.semantic_evaluation?.concerns || result.concerns;

  const fingerprint = `${cleanRequest}|${rawDecision}|${result.final_output || ''}`;
  if (lastSavedFingerprint === fingerprint) {
    return null;
  }

  const existing = getStoredHistory();
  if (existing.length > 0) {
    const top = existing[0];
    if (
      top.request === cleanRequest &&
      top.decision === rawDecision &&
      top.final_output === (result.final_output || '')
    ) {
      lastSavedFingerprint = fingerprint;
      return top;
    }
  }

  const entry = {
    id: generateHistoryId(),
    timestamp: new Date().toISOString(),
    request: cleanRequest,
    decision: rawDecision,
    duration_ms: Number.isFinite(durationMs) ? durationMs : null,
    final_output: typeof result.final_output === 'string' ? result.final_output : '',
    reason: typeof result.reason === 'string' ? result.reason : null,
    acceptance_probability: Number.isFinite(noulValue) ? noulValue : null,
    evaluation_confidence: Number.isFinite(noulConfidence) ? noulConfidence : null,
    failed_dimensions: Array.isArray(result.failed_dimensions) ? result.failed_dimensions : [],
    concerns: Array.isArray(concerns) ? concerns : [],
    repairs: result.repairs ?? null,
  };

  const updated = [entry, ...existing].slice(0, MAX_HISTORY_ENTRIES);
  persistHistory(updated);
  lastSavedFingerprint = fingerprint;
  updateHistoryBadgeCount(updated.length);
  return entry;
}

function formatHistoryTimestamp(isoString) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

function formatHistoryDuration(durationMs) {
  if (!Number.isFinite(durationMs) || durationMs === null) return '';
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(1)}s`;
  }
  return `${durationMs.toFixed(0)}ms`;
}

function openHistoricalEntry(entry) {
  closeHistoryDrawer();

  // Reconstruct result presentation for read-only viewing
  const reconstructed = {
    ok: true,
    job_duration_ms: entry.duration_ms,
    request_text: entry.request,
    result: {
      decision: entry.decision,
      reason: entry.reason,
      final_output: entry.final_output,
      repairs: entry.repairs,
      failed_dimensions: entry.failed_dimensions,
      semantic_evaluation: {
        noul: {
          value: entry.acceptance_probability,
          confidence: entry.evaluation_confidence,
        },
        concerns: entry.concerns,
      },
    },
  };

  renderResult(reconstructed, true, entry);
}

function renderHistoryDrawer() {
  if (!historyList) return;
  historyList.replaceChildren();
  const entries = getStoredHistory();
  updateHistoryBadgeCount(entries.length);

  if (entries.length === 0) {
    const emptyNode = document.createElement('div');
    emptyNode.className = 'history-empty';
    emptyNode.textContent = 'No completed evaluations recorded yet.';
    historyList.appendChild(emptyNode);
    return;
  }

  for (const entry of entries) {
    const itemButton = document.createElement('button');
    itemButton.type = 'button';
    itemButton.className = 'history-item';
    itemButton.setAttribute('role', 'listitem');

    const topRow = document.createElement('div');
    topRow.className = 'history-item-top';

    const decisionBadge = document.createElement('span');
    decisionBadge.className = 'history-badge';
    const decisionCat = getDecisionCategory(entry.decision);
    decisionBadge.dataset.decision = decisionCat;
    decisionBadge.textContent = entry.decision || 'not provided';
    topRow.appendChild(decisionBadge);

    const timeSpan = document.createElement('span');
    timeSpan.className = 'history-item-time';
    const timeText = formatHistoryTimestamp(entry.timestamp);
    const durText = formatHistoryDuration(entry.duration_ms);
    timeSpan.textContent = durText ? `${timeText} • ${durText}` : timeText;
    topRow.appendChild(timeSpan);

    const requestP = document.createElement('p');
    requestP.className = 'history-item-request';
    requestP.textContent = entry.request;

    itemButton.appendChild(topRow);
    itemButton.appendChild(requestP);

    itemButton.addEventListener('click', () => {
      openHistoricalEntry(entry);
    });

    historyList.appendChild(itemButton);
  }
}

function openHistoryDrawer() {
  renderHistoryDrawer();
  if (historyDrawer) {
    historyDrawer.classList.remove('hidden');
  }
  if (historyBackdrop) {
    historyBackdrop.classList.remove('hidden');
  }
  if (closeHistoryButton) {
    closeHistoryButton.focus();
  }
}

function closeHistoryDrawer() {
  if (historyDrawer) {
    historyDrawer.classList.add('hidden');
  }
  if (historyBackdrop) {
    historyBackdrop.classList.add('hidden');
  }
}

function toggleHistoryDrawer() {
  if (historyDrawer && !historyDrawer.classList.contains('hidden')) {
    closeHistoryDrawer();
  } else {
    openHistoryDrawer();
  }
}

function clearAllHistory() {
  const confirmed = window.confirm('Clear all saved evaluation history?');
  if (!confirmed) {
    return;
  }
  try {
    localStorage.removeItem(HISTORY_STORAGE_KEY);
  } catch (err) {
    console.warn('Failed to clear history from localStorage:', err);
  }
  lastSavedFingerprint = '';
  renderHistoryDrawer();
}

function clearActiveResult() {
  if (historicalBanner) {
    historicalBanner.classList.add('hidden');
  }
  if (resultSection) {
    resultSection.classList.add('hidden');
  }
  if (decisionPanel) {
    decisionPanel.dataset.decision = 'OTHER';
  }
  if (decisionNode) {
    decisionNode.textContent = 'not provided';
  }
  if (decisionIcon) {
    decisionIcon.textContent = '●';
  }
  if (jobSignatureNode) {
    jobSignatureNode.textContent = 'JEV';
  }
  if (finalOutputNode) {
    finalOutputNode.textContent = 'not provided';
  }
  if (reasonNode) {
    reasonNode.textContent = 'not provided';
  }
  if (acceptanceProbabilityNode) {
    acceptanceProbabilityNode.textContent = 'not provided';
  }
  if (evaluationConfidenceNode) {
    evaluationConfidenceNode.textContent = 'not provided';
  }
  if (repairCountNode) {
    repairCountNode.textContent = 'not provided';
  }
  if (failedDimensionsNode) {
    failedDimensionsNode.textContent = 'not provided';
  }
  if (concernsNode) {
    concernsNode.replaceChildren();
    concernsNode.textContent = 'none reported';
  }
  if (jobDurationNode) {
    jobDurationNode.textContent = 'not provided';
  }
  if (detailsNode) {
    detailsNode.textContent = '';
  }
  const consoleDetails = document.querySelector('.decision-console');
  if (consoleDetails) {
    consoleDetails.removeAttribute('open');
  }
  if (mindspace) {
    mindspace.classList.remove('has-result');
  }
}

function activateComposer() {
  closeHistoryDrawer();

  // 1. Save completed evaluation to History BEFORE clearing, if not already saved
  if (activeEvaluation && !activeEvaluation.saved) {
    saveEvaluationToHistory(activeEvaluation.data, activeEvaluation.request);
    activeEvaluation.saved = true;
  }
  activeEvaluation = null;

  // 2. Preserve request if transition is from clarification, otherwise clear
  const isClarificationTransition = messageSection && messageSection.dataset.state === 'clarification';
  if (!isClarificationTransition) {
    if (requestInput) {
      requestInput.value = '';
    }
    clearMessage();
  }

  // 3. Clear active result presentation from workspace
  clearActiveResult();

  // 4. Switch Jev to attentive
  setCharacterState('attentive');

  // 5. Reveal clean request composer
  if (mindspace) {
    mindspace.classList.add('is-active');
  }
  if (activePanel) {
    activePanel.classList.remove('hidden');
  }
  if (processingSection) {
    processingSection.classList.add('hidden');
  }
  if (composerView) {
    composerView.classList.remove('hidden');
  }

  // 6. Ensure CTA button is 'Let’s Check'
  if (button) {
    button.disabled = false;
    const buttonLabel = button.querySelector('span');
    if (buttonLabel) {
      buttonLabel.textContent = 'Let’s Check';
    }
  }

  // 7. Focus textarea
  if (requestInput) {
    requestInput.focus();
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderMarkdownSafely(container, rawText) {
  if (!rawText || rawText === 'not provided') {
    container.textContent = rawText || 'not provided';
    return;
  }

  // 1. Escape all untrusted characters first (XSS prevention)
  const escaped = escapeHtml(rawText);

  // 2. Extract code blocks (``` ... ```)
  const codeBlockPlaceholders = [];
  const withoutCodeBlocks = escaped.replace(/```([a-zA-Z0-9_-]*)\r?\n([\s\S]*?)```/g, (match, lang, code) => {
    const idx = codeBlockPlaceholders.length;
    codeBlockPlaceholders.push(`<pre><code>${code.trim()}</code></pre>`);
    return `@@CODEBLOCK_${idx}@@`;
  });

  const lines = withoutCodeBlocks.split(/\r?\n/);
  const blocks = [];
  let currentList = null;
  let listItems = [];
  let currentParagraph = [];

  function formatInline(text) {
    return text
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/__([^_]+)__/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/_([^_]+)_/g, '<em>$1</em>');
  }

  function flushParagraph() {
    if (currentParagraph.length > 0) {
      blocks.push(`<p>${formatInline(currentParagraph.join('<br>'))}</p>`);
      currentParagraph = [];
    }
  }

  function flushList() {
    if (currentList && listItems.length > 0) {
      blocks.push(`<${currentList}>${listItems.map((item) => `<li>${formatInline(item)}</li>`).join('')}</${currentList}>`);
      currentList = null;
      listItems = [];
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (trimmed.startsWith('@@CODEBLOCK_')) {
      flushParagraph();
      flushList();
      blocks.push(trimmed);
      continue;
    }

    // Horizontal Rule: 3 or more hyphens, asterisks, or underscores alone on a line
    if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushParagraph();
      flushList();
      blocks.push('<hr>');
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length <= 3 ? 3 : 4;
      blocks.push(`<h${level}>${formatInline(headingMatch[2])}</h${level}>`);
      continue;
    }

    const ulMatch = trimmed.match(/^[\*\-]\s+(.+)$/);
    if (ulMatch) {
      flushParagraph();
      if (currentList && currentList !== 'ul') flushList();
      currentList = 'ul';
      listItems.push(ulMatch[1]);
      continue;
    }

    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      flushParagraph();
      if (currentList && currentList !== 'ol') flushList();
      currentList = 'ol';
      listItems.push(olMatch[1]);
      continue;
    }

    flushList();
    currentParagraph.push(trimmed);
  }

  flushParagraph();
  flushList();

  let html = blocks.join('\n');
  for (let idx = 0; idx < codeBlockPlaceholders.length; idx++) {
    html = html.replace(`@@CODEBLOCK_${idx}@@`, codeBlockPlaceholders[idx]);
  }

  container.innerHTML = html;
}

function setMessage(state, title, content) {
  messageSection.dataset.state = state;
  messageSection.classList.remove('hidden');
  messageTitle.textContent = title;
  messageIcon.textContent = state === 'clarification' ? '?' : '!';
  messageContent.replaceChildren();

  const messages = Array.isArray(content) ? content : [content];
  for (const message of messages) {
    const item = document.createElement('p');
    item.textContent = message;
    messageContent.appendChild(item);
  }

  // Technical errors do not use authoritative failure asset
  setCharacterState('attentive');
}

function clearMessage() {
  messageSection.classList.add('hidden');
  messageSection.removeAttribute('data-state');
  messageTitle.textContent = '';
  messageContent.replaceChildren();
}

function readPayload() {
  return {
    request_text: String(new FormData(form).get('request_text') || ''),
  };
}

function formatPercentage(value) {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    return 'not provided';
  }

  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value * 100)}%`;
}

function formatElapsedTime() {
  const elapsedSeconds = ((Date.now() - startedAt) / 1000).toFixed(1);
  elapsedTimeNode.textContent = `${elapsedSeconds}s`;
}

function startProcessing() {
  startedAt = Date.now();
  if (mindspace) {
    mindspace.classList.remove('has-result');
  }
  composerView.classList.add('hidden');
  processingSection.classList.remove('hidden');
  setCharacterState('checking');
  formatElapsedTime();
  elapsedTimer = window.setInterval(formatElapsedTime, 100);
}

function stopProcessing() {
  if (elapsedTimer !== null) {
    window.clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
  processingSection.classList.add('hidden');
}

function renderResult(data, isHistorical = false, historicalEntry = null) {
  if (!isHistorical) {
    saveEvaluationToHistory(data, requestInput ? requestInput.value : '');
    activeEvaluation = {
      data,
      request: requestInput ? requestInput.value : '',
      saved: true,
    };
    if (historicalBanner) {
      historicalBanner.classList.add('hidden');
    }
  } else {
    activeEvaluation = null;
    if (historicalBanner) {
      historicalBanner.classList.remove('hidden');
      if (historicalTimeNode && historicalEntry) {
        const timeText = formatHistoryTimestamp(historicalEntry.timestamp);
        const durText = formatHistoryDuration(historicalEntry.duration_ms);
        historicalTimeNode.textContent = durText ? `${timeText} • ${durText}` : timeText;
      }
      if (historicalRequestNode && historicalEntry) {
        historicalRequestNode.textContent = `Request: ${historicalEntry.request}`;
      }
    }
  }

  const result = data.result || {};
  const rawDecision = typeof result.decision === 'string' && result.decision
    ? result.decision.trim()
    : 'not provided';

  decisionNode.textContent = rawDecision;
  decisionPanel.dataset.decision = rawDecision;

  // Authoritative decision mapping
  const upperDecision = rawDecision.toUpperCase();
  if (upperDecision === 'PASS') {
    decisionPanel.dataset.decision = 'PASS';
    decisionIcon.textContent = '✔';
    setCharacterState('idle');
  } else if (upperDecision === 'HUMAN REVIEW') {
    decisionPanel.dataset.decision = 'HUMAN REVIEW';
    decisionIcon.textContent = '!';
    setCharacterState('human_review');
  } else if (['FAIL', 'FAILED', 'REJECTED', 'FAILURE'].includes(upperDecision)) {
    decisionPanel.dataset.decision = 'FAILURE';
    decisionIcon.textContent = '✕';
    setCharacterState('failure');
  } else {
    // REPAIR, REVISE, or unconfirmed decisions remain neutral
    decisionPanel.dataset.decision = 'NEUTRAL';
    decisionIcon.textContent = '●';
    setCharacterState('attentive');
  }

  // Execution signature using job_duration_ms
  const durationMs = Number(data.job_duration_ms);
  if (Number.isFinite(durationMs) && durationMs >= 1000) {
    jobSignatureNode.textContent = `JEV • ${(durationMs / 1000).toFixed(1)}s`;
  } else if (Number.isFinite(durationMs)) {
    jobSignatureNode.textContent = `JEV • ${durationMs.toFixed(1)}ms`;
  } else {
    jobSignatureNode.textContent = 'JEV';
  }

  reasonNode.textContent = result.reason ?? 'not provided';
  acceptanceProbabilityNode.textContent = formatPercentage(result.semantic_evaluation?.noul?.value);
  evaluationConfidenceNode.textContent = formatPercentage(result.semantic_evaluation?.noul?.confidence);
  failedDimensionsNode.textContent = Array.isArray(result.failed_dimensions) && result.failed_dimensions.length
    ? result.failed_dimensions.join(', ')
    : 'not provided';

  const concerns = result.semantic_evaluation?.concerns || result.concerns;
  concernsNode.replaceChildren();
  if (Array.isArray(concerns) && concerns.every((concern) => typeof concern === 'string') && concerns.length) {
    for (const concern of concerns) {
      const item = document.createElement('div');
      item.textContent = concern;
      concernsNode.appendChild(item);
    }
  } else {
    concernsNode.textContent = 'none reported';
  }

  repairCountNode.textContent = result.repairs ?? 'not provided';
  renderMarkdownSafely(finalOutputNode, result.final_output ?? 'not provided');
  jobDurationNode.textContent = Number.isFinite(durationMs) ? `${durationMs.toFixed(3)} ms` : 'not provided';
  detailsNode.textContent = JSON.stringify(data, null, 2);

  if (mindspace) {
    mindspace.classList.add('is-active');
    mindspace.classList.add('has-result');
  }
  if (activePanel) {
    activePanel.classList.remove('hidden');
  }
  if (composerView) {
    composerView.classList.add('hidden');
  }
  resultSection.classList.remove('hidden');
}

async function submitEvaluation(event) {
  event.preventDefault();
  if (inFlight) {
    return;
  }

  const payload = readPayload();
  if (!payload.request_text.trim()) {
    setMessage('clarification', 'Add a request to continue', 'Describe what you want Jev to do, then run it again.');
    requestInput.focus();
    return;
  }

  inFlight = true;
  button.disabled = true;
  button.querySelector('span').textContent = 'Checking…';
  clearMessage();
  clearActiveResult();
  startProcessing();

  try {
    const response = await fetch('/api/evaluate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Host': window.location.host,
        'Origin': window.location.origin,
      },
      body: JSON.stringify(payload),
    });

    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error('Jev returned an unreadable response. Check the local server and try again.');
    }

    if (data && data.status === 'NEEDS_CLARIFICATION') {
      const issues = Array.isArray(data.clarification_issues)
        ? data.clarification_issues.filter((issue) => typeof issue === 'string')
        : [];
      composerView.classList.remove('hidden');
      setMessage(
        'clarification',
        'A quick clarification',
        issues.length ? issues : ['Please clarify your request.'],
      );
      return;
    }

    if (!response.ok || !data?.ok) {
      const serverMessage = typeof data?.error?.message === 'string'
        ? data.error.message.split(/\r?\n/, 1)[0].trim()
        : '';
      throw new Error(serverMessage || 'Jev couldn’t complete this run. Check the local server and try again.');
    }

    renderResult(data);
  } catch (error) {
    composerView.classList.remove('hidden');
    const message = error instanceof Error && error.message
      ? error.message
      : 'Jev couldn’t complete this run. Check the local server and try again.';
    setMessage('error', 'Run couldn’t be completed', message);
    setCharacterState('attentive');
  } finally {
    stopProcessing();
    inFlight = false;
    button.disabled = false;
    button.querySelector('span').textContent = 'Let’s Check';
  }
}

if (heroButton) {
  heroButton.addEventListener('click', activateComposer);
}

if (historyToggleButton) {
  historyToggleButton.addEventListener('click', toggleHistoryDrawer);
}

if (closeHistoryButton) {
  closeHistoryButton.addEventListener('click', closeHistoryDrawer);
}

if (historyBackdrop) {
  historyBackdrop.addEventListener('click', closeHistoryDrawer);
}

if (clearHistoryButton) {
  clearHistoryButton.addEventListener('click', clearAllHistory);
}

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && historyDrawer && !historyDrawer.classList.contains('hidden')) {
    closeHistoryDrawer();
  }
});

form.addEventListener('submit', submitEvaluation);
requestInput.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    form.requestSubmit();
  }
});
requestInput.addEventListener('focus', () => {
  if (!inFlight) {
    setCharacterState('attentive');
  }
});
requestInput.addEventListener('input', () => {
  if (!inFlight) {
    setCharacterState('attentive');
  }
});
requestInput.addEventListener('blur', () => {
  if (!inFlight && !requestInput.value.trim() && !mindspace?.classList.contains('is-active')) {
    setCharacterState('idle');
  }
});

// Initialize history badge count from storage
updateHistoryBadgeCount();
