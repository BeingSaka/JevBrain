const form = document.getElementById('jev-form');
const errorSection = document.getElementById('error-section');
const resultSection = document.getElementById('result-section');
const button = document.getElementById('evaluate-button');

const decisionNode = document.getElementById('decision-value');
const reasonNode = document.getElementById('reason-value');
const repairCountNode = document.getElementById('repair-count-value');
const failedDimensionsNode = document.getElementById('failed-dimensions-value');
const finalOutputNode = document.getElementById('final-output-value');
const jobDurationNode = document.getElementById('job-duration-value');
const detailsNode = document.getElementById('technical-details');

function setError(message) {
  errorSection.classList.remove('hidden');
  errorSection.textContent = message;
  resultSection.classList.add('hidden');
}

function clearError() {
  errorSection.classList.add('hidden');
  errorSection.textContent = '';
}

function parseJsonField(rawValue) {
  if (!rawValue || !rawValue.trim()) {
    return {};
  }
  try {
    const value = JSON.parse(rawValue);
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value;
    }
    throw new Error('Deterministic checks must be a JSON object');
  } catch (error) {
    throw new Error(`Invalid deterministic checks: ${error.message}`);
  }
}

function parseListText(value) {
  if (!value || !value.trim()) {
    return [];
  }
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function readPayload() {
  const formData = new FormData(form);
  const payload = {
    original_request: String(formData.get('original_request') || ''),
    locked_requirements: parseListText(String(formData.get('locked_requirements') || '')),
    candidate_output: String(formData.get('candidate_output') || ''),
    output_type: String(formData.get('output_type') || 'text'),
  };

  const availableEvidence = String(formData.get('available_evidence') || '');
  if (availableEvidence.trim()) {
    payload.available_evidence = availableEvidence;
  }

  const knownConstraints = parseListText(String(formData.get('known_constraints') || ''));
  if (knownConstraints.length) {
    payload.known_constraints = knownConstraints;
  }

  const rawChecks = String(formData.get('deterministic_checks') || '');
  if (rawChecks.trim()) {
    payload.deterministic_checks = parseJsonField(rawChecks);
  }

  return payload;
}

async function submitEvaluation(event) {
  event.preventDefault();
  clearError();
  button.disabled = true;
  button.textContent = 'Evaluating...';

  try {
    const payload = readPayload();
    const response = await fetch('/api/evaluate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Host': window.location.host,
        'Origin': window.location.origin,
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok || !data.ok) {
      const message = data && data.error && data.error.message ? data.error.message : 'Evaluation failed';
      throw new Error(message);
    }

    const result = data.result || {};
    decisionNode.textContent = result.decision || 'not provided';
    reasonNode.textContent = result.reason || 'not provided';
    repairCountNode.textContent = result.repairs ?? 'not provided';
    failedDimensionsNode.textContent = Array.isArray(result.failed_dimensions) && result.failed_dimensions.length ? result.failed_dimensions.join(', ') : 'not provided';
    finalOutputNode.textContent = result.final_output ?? 'not provided';
    jobDurationNode.textContent = `${Number(data.job_duration_ms || 0).toFixed(3)} ms`;
    detailsNode.textContent = JSON.stringify(data, null, 2);
    resultSection.classList.remove('hidden');
  } catch (error) {
    setError(error.message || 'Evaluation failed');
  } finally {
    button.disabled = false;
    button.textContent = 'EVALUATE';
  }
}

form.addEventListener('submit', submitEvaluation);
