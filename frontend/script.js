const API_BASE_URL = "http://127.0.0.1:8000";

const form = document.getElementById("promptForm");
const promptInput = document.getElementById("promptInput");
const submitButton = document.getElementById("submitButton");
const responseOutput = document.getElementById("responseOutput");
const requestState = document.getElementById("requestState");
const formMessage = document.getElementById("formMessage");
const requestsSent = document.getElementById("requestsSent");
const successfulWrites = document.getElementById("successfulWrites");
const lastLatency = document.getElementById("lastLatency");
const apiTarget = document.getElementById("apiTarget");
const providerUsed = document.getElementById("providerUsed");
const requestId = document.getElementById("requestId");
const modelUsed = document.getElementById("modelUsed");
const inferenceLatency = document.getElementById("inferenceLatency");
const lastProvider = document.getElementById("lastProvider");
const requestCategory = document.getElementById("requestCategory");
const fallbackUsed = document.getElementById("fallbackUsed");
const backendTotal = document.getElementById("backendTotal");
const backendFailures = document.getElementById("backendFailures");
const averageLatency = document.getElementById("averageLatency");
const fallbackUsage = document.getElementById("fallbackUsage");
const providerHealth = document.getElementById("providerHealth");
const categoryBreakdown = document.getElementById("categoryBreakdown");
const requestPriority = document.getElementById("requestPriority");
const lifecycleState = document.getElementById("lifecycleState");
const queueWait = document.getElementById("queueWait");
const executionDuration = document.getElementById("executionDuration");
const queueDepth = document.getElementById("queueDepth");
const activeExecutions = document.getElementById("activeExecutions");
const requestsPerMinute = document.getElementById("requestsPerMinute");
const providerCapacity = document.getElementById("providerCapacity");
const lifecycleBreakdown = document.getElementById("lifecycleBreakdown");
const newSessionButton = document.getElementById("newSessionButton");
const currentSessionName = document.getElementById("currentSessionName");
const sessionList = document.getElementById("sessionList");
const sessionHistory = document.getElementById("sessionHistory");

// Phase 5 — new DOM references
const cacheHitEl = document.getElementById("cacheHit");
const deduplicatedEl = document.getElementById("deduplicated");
const estimatedCostEl = document.getElementById("estimatedCost");
const orchestrationHealth = document.getElementById("orchestrationHealth");
const cacheHitRatio = document.getElementById("cacheHitRatio");
const cacheHitsMisses = document.getElementById("cacheHitsMisses");
const cacheEntries = document.getElementById("cacheEntries");
const cacheEvictions = document.getElementById("cacheEvictions");
const providerScores = document.getElementById("providerScores");
const providerCooldowns = document.getElementById("providerCooldowns");
const dedupCount = document.getElementById("dedupCount");
const dedupRate = document.getElementById("dedupRate");
const totalCost = document.getElementById("totalCost");
const avgCostPerRequest = document.getElementById("avgCostPerRequest");
const totalTokens = document.getElementById("totalTokens");
const integrityViolations = document.getElementById("integrityViolations");
const recoveryActions = document.getElementById("recoveryActions");
const queueAnomalies = document.getElementById("queueAnomalies");
const activeQueueInspector = document.getElementById("activeQueueInspector");
const executionTimelines = document.getElementById("executionTimelines");
const violationLog = document.getElementById("violationLog");
const schedulerDecisions = document.getElementById("schedulerDecisions");

let requestCount = 0;
let successCount = 0;
let activeSessionId = localStorage.getItem("qorvexis.activeSessionId");
let activeSessionTitle = "New operational session";

apiTarget.textContent = new URL(API_BASE_URL).host;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setState(label, stateClass) {
  requestState.textContent = label;
  requestState.className = `request-state ${stateClass || ""}`.trim();
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "Submitting..." : "Submit request";
}

function setActiveSession(session) {
  activeSessionId = session.id;
  activeSessionTitle = session.title;
  localStorage.setItem("qorvexis.activeSessionId", activeSessionId);
  currentSessionName.textContent = activeSessionTitle;
}

async function createSession(title = "New operational session") {
  const response = await fetch(`${API_BASE_URL}/sessions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title }),
  });

  if (!response.ok) {
    throw new Error("Unable to create operational session.");
  }

  const session = await response.json();
  setActiveSession(session);
  await refreshSessions();
  await loadSessionHistory();
}

async function refreshSessions() {
  const response = await fetch(`${API_BASE_URL}/sessions`);
  if (!response.ok) {
    throw new Error("Unable to load sessions.");
  }

  const sessions = await response.json();
  if (sessions.length === 0) {
    activeSessionId = null;
    localStorage.removeItem("qorvexis.activeSessionId");
    currentSessionName.textContent = "No active session";
    sessionList.innerHTML = '<span class="empty-state">No sessions yet.</span>';
    return;
  }

  if (!activeSessionId || !sessions.some((session) => session.id === activeSessionId)) {
    setActiveSession(sessions[0]);
  } else {
    const activeSession = sessions.find((session) => session.id === activeSessionId);
    if (activeSession) {
      setActiveSession(activeSession);
    }
  }

  sessionList.innerHTML = sessions
    .map((session) => {
      const safeTitle = escapeHtml(session.title);
      return `
      <button
        type="button"
        class="session-item ${session.id === activeSessionId ? "active" : ""}"
        data-session-id="${escapeHtml(session.id)}"
        data-session-title="${safeTitle}"
      >
        ${safeTitle}
      </button>
    `;
    })
    .join("");
}

async function loadSessionHistory() {
  if (!activeSessionId) {
    sessionHistory.innerHTML = '<span class="empty-state">No active session.</span>';
    return;
  }

  const response = await fetch(`${API_BASE_URL}/sessions/${activeSessionId}/requests`);
  if (!response.ok) {
    throw new Error("Unable to load session memory.");
  }

  const history = await response.json();
  if (history.length === 0) {
    sessionHistory.innerHTML = '<span class="empty-state">No requests in this session yet.</span>';
    return;
  }

  sessionHistory.innerHTML = history
    .slice(-6)
    .reverse()
    .map((item) => `
      <div class="ops-row">
        <strong>${escapeHtml(item.category || "general")} | ${escapeHtml(item.provider || item.status)}</strong>
        <span>${escapeHtml(item.prompt)}</span>
      </div>
    `)
    .join("");
}

function formatLatency(value) {
  return value || value === 0 ? `${Math.round(value)} ms` : "--";
}

function renderProviderHealth(metrics) {
  if (!metrics.providers || metrics.providers.length === 0) {
    providerHealth.innerHTML = '<span class="empty-state">No provider metrics yet.</span>';
    return;
  }

  providerHealth.innerHTML = metrics.providers
    .map((provider) => {
      const healthClass = provider.success_rate >= 95 ? "health-ok" : "health-warn";
      return `
        <div class="ops-row">
          <strong>${provider.provider}</strong>
          <span class="${healthClass}">${provider.success_rate}% success</span>
          <span>${provider.total_requests} requests | ${provider.failure_count} failures | ${formatLatency(provider.average_latency_ms)} avg</span>
        </div>
      `;
    })
    .join("");
}

function renderCategories(metrics) {
  if (!metrics.categories || metrics.categories.length === 0) {
    categoryBreakdown.innerHTML = '<span class="empty-state">No category metrics yet.</span>';
    return;
  }

  categoryBreakdown.innerHTML = metrics.categories
    .map((category) => `
      <div class="ops-row">
        <strong>${category.category}</strong>
        <span>${category.total_requests} requests | ${category.percentage}% of traffic</span>
      </div>
    `)
    .join("");
}

function renderCapacity(metrics) {
  if (!metrics.providers || metrics.providers.length === 0) {
    providerCapacity.innerHTML = '<span class="empty-state">No capacity metrics yet.</span>';
    return;
  }

  providerCapacity.innerHTML = metrics.providers
    .map((provider) => `
      <div class="ops-row">
        <strong>${escapeHtml(provider.provider)}</strong>
        <span>${provider.active_requests} active | ${provider.queued_requests} queued | limit ${provider.concurrency_level}</span>
        <span>${formatLatency(provider.average_execution_ms)} avg | ${provider.failure_rate}% failures</span>
      </div>
    `)
    .join("");
}

function renderLifecycle(metrics) {
  const states = metrics.states || [];
  const priorities = metrics.priorities || [];
  if (states.length === 0 && priorities.length === 0) {
    lifecycleBreakdown.innerHTML = '<span class="empty-state">No lifecycle metrics yet.</span>';
    return;
  }

  lifecycleBreakdown.innerHTML = [
    ...states.map((item) => `
      <div class="ops-row">
        <strong>${escapeHtml(item.state)}</strong>
        <span>${item.count} requests</span>
      </div>
    `),
    ...priorities.map((item) => `
      <div class="ops-row">
        <strong>${escapeHtml(item.priority)} priority</strong>
        <span>${item.count} requests</span>
      </div>
    `),
  ].join("");
}

// Phase 5 — render functions

function renderOrchestrationHealth(metrics) {
  if (!metrics || metrics.orchestration_health_score === undefined) {
    orchestrationHealth.innerHTML = '<span class="empty-state">No health data yet.</span>';
    return;
  }
  const score = metrics.orchestration_health_score;
  const components = metrics.components || {};
  const scoreClass = score >= 75 ? "health-ok" : score >= 40 ? "health-warn" : "health-critical";

  orchestrationHealth.innerHTML = `
    <div class="ops-row">
      <strong class="${scoreClass}">Overall: ${score}/100</strong>
      <span>Reliability ${components.provider_reliability || 0} | Queue ${components.queue_efficiency || 0} | Execution ${components.execution_efficiency || 0} | Cache ${components.cache_efficiency || 0} | Failover ${components.failover_health || 0}</span>
    </div>
  `;
}

function renderCacheMetrics(metrics) {
  cacheHitRatio.textContent = metrics.hit_ratio !== undefined ? `${metrics.hit_ratio}%` : "--";
  cacheHitsMisses.textContent = `${metrics.hits || 0} / ${metrics.misses || 0}`;
  cacheEntries.textContent = `${metrics.entries || 0} / ${metrics.max_entries || 0}`;
  cacheEvictions.textContent = metrics.evictions || 0;
}

function renderProviderScores(metrics) {
  if (!metrics.providers || metrics.providers.length === 0) {
    providerScores.innerHTML = '<span class="empty-state">No scoring data yet.</span>';
    return;
  }
  providerScores.innerHTML = metrics.providers
    .map((p) => {
      const scoreClass = p.score >= 70 ? "health-ok" : p.score >= 40 ? "health-warn" : "health-critical";
      return `
        <div class="ops-row">
          <strong>${escapeHtml(p.provider)}</strong>
          <span class="${scoreClass}">Score: ${p.score}/100</span>
          <span>${p.success_count} success | ${p.failure_count} failures | ${formatLatency(p.average_latency_ms)} avg</span>
        </div>
      `;
    })
    .join("");
}

function renderCooldowns(metrics) {
  if (!metrics.providers || metrics.providers.length === 0) {
    providerCooldowns.innerHTML = '<span class="empty-state">No cooldown data yet.</span>';
    return;
  }
  providerCooldowns.innerHTML = metrics.providers
    .map((p) => {
      const statusClass = p.is_cooled_down ? "health-critical" : "health-ok";
      const statusLabel = p.is_cooled_down
        ? `COOLED DOWN (${p.cooldown_remaining_seconds}s remaining)`
        : "Operational";
      return `
        <div class="ops-row">
          <strong>${escapeHtml(p.provider)}</strong>
          <span class="${statusClass}">${statusLabel}</span>
          <span>${p.total_cooldowns} cooldowns | ${p.consecutive_failures} consecutive failures | ${p.window_failure_rate}% failure rate</span>
        </div>
      `;
    })
    .join("");
}

function renderDedupMetrics(metrics) {
  dedupCount.textContent = metrics.duplicates_detected || 0;
  dedupRate.textContent = metrics.dedup_rate !== undefined ? `${metrics.dedup_rate}%` : "--";
}

function renderCostMetrics(metrics) {
  totalCost.textContent = metrics.total_estimated_cost !== undefined
    ? `$${metrics.total_estimated_cost.toFixed(4)}`
    : "--";
  avgCostPerRequest.textContent = metrics.average_cost_per_request !== undefined
    ? `$${metrics.average_cost_per_request.toFixed(6)}`
    : "--";
  totalTokens.textContent = metrics.total_prompt_tokens !== undefined
    ? `${(metrics.total_prompt_tokens + metrics.total_response_tokens).toLocaleString()}`
    : "--";
}

function renderDiagnostics(metrics) {
  const queue = metrics.queue || {};
  const integrity = metrics.integrity || {};
  const recovery = metrics.recovery || {};
  const queuedItems = queue.queued_items || [];
  const timelines = metrics.timelines || [];
  const violations = (integrity.recent_violations || []).slice(0, 8);
  const transitions = (metrics.transitions || []).slice(0, 8);

  integrityViolations.textContent = integrity.violation_count || 0;
  recoveryActions.textContent = recovery.recovery_action_count || 0;
  queueAnomalies.textContent = queue.queue_anomalies || 0;

  activeQueueInspector.innerHTML = queuedItems.length
    ? queuedItems.map((item) => `
      <div class="ops-row">
        <strong>#${item.request_id} | ${escapeHtml(item.provider)}</strong>
        <span>priority ${item.priority_sort} | queued ${formatLatency(item.queued_for_ms)}</span>
      </div>
    `).join("")
    : '<span class="empty-state">Queue is currently empty.</span>';

  executionTimelines.innerHTML = timelines.length
    ? timelines.map((item) => `
      <div class="ops-row">
        <strong>#${item.request_id} | ${escapeHtml(item.lifecycle_state)}</strong>
        <span>${escapeHtml(item.provider || "unassigned")} | queue ${formatLatency(item.queue_wait_ms)} | execution ${formatLatency(item.execution_duration_ms)}</span>
        <span>received ${escapeHtml(item.received_at || "--")} | completed ${escapeHtml(item.completed_at || "--")}</span>
      </div>
    `).join("")
    : '<span class="empty-state">No request timelines yet.</span>';

  violationLog.innerHTML = violations.length
    ? violations.map((item) => `
      <div class="ops-row">
        <strong>#${item.request_id || "--"} | ${escapeHtml(item.reason)}</strong>
        <span>${escapeHtml(item.current_state || "unknown")} -> ${escapeHtml(item.attempted_state)}</span>
      </div>
    `).join("")
    : '<span class="empty-state">No violations recorded.</span>';

  schedulerDecisions.innerHTML = transitions.length
    ? transitions.map((item) => `
      <div class="ops-row">
        <strong>#${item.request_id} | ${escapeHtml(item.state)}</strong>
        <span>${escapeHtml(item.detail || "transition")} | ${escapeHtml(item.created_at)}</span>
      </div>
    `).join("")
    : '<span class="empty-state">No lifecycle transitions yet.</span>';
}

async function refreshMetrics() {
  try {
    const [
      overviewResponse,
      providersResponse,
      categoriesResponse,
      queueResponse,
      capacityResponse,
      throughputResponse,
      lifecycleResponse,
      cacheResponse,
      scoresResponse,
      healthResponse,
      costsResponse,
      failoverResponse,
      dedupResponse,
      diagnosticsResponse,
    ] = await Promise.all([
      fetch(`${API_BASE_URL}/metrics/overview`),
      fetch(`${API_BASE_URL}/metrics/providers`),
      fetch(`${API_BASE_URL}/metrics/categories`),
      fetch(`${API_BASE_URL}/metrics/queue`),
      fetch(`${API_BASE_URL}/metrics/capacity`),
      fetch(`${API_BASE_URL}/metrics/throughput`),
      fetch(`${API_BASE_URL}/metrics/lifecycle`),
      fetch(`${API_BASE_URL}/metrics/cache`),
      fetch(`${API_BASE_URL}/metrics/providers/score`),
      fetch(`${API_BASE_URL}/metrics/orchestration/health`),
      fetch(`${API_BASE_URL}/metrics/costs`),
      fetch(`${API_BASE_URL}/metrics/failover`),
      fetch(`${API_BASE_URL}/metrics/dedup`),
      fetch(`${API_BASE_URL}/metrics/diagnostics`),
    ]);

    if (
      !overviewResponse.ok ||
      !providersResponse.ok ||
      !categoriesResponse.ok ||
      !queueResponse.ok ||
      !capacityResponse.ok ||
      !throughputResponse.ok ||
      !lifecycleResponse.ok
    ) {
      throw new Error("Metrics refresh failed.");
    }

    const overview = await overviewResponse.json();
    const providers = await providersResponse.json();
    const categories = await categoriesResponse.json();
    const queueMetrics = await queueResponse.json();
    const capacity = await capacityResponse.json();
    const throughput = await throughputResponse.json();
    const lifecycle = await lifecycleResponse.json();

    backendTotal.textContent = overview.total_requests;
    backendFailures.textContent = overview.failed_requests;
    averageLatency.textContent = formatLatency(overview.average_latency_ms);
    fallbackUsage.textContent = `${overview.fallback_count} (${overview.fallback_rate}%)`;
    queueDepth.textContent = queueMetrics.queue_depth;
    activeExecutions.textContent = queueMetrics.active_executions;
    requestsPerMinute.textContent = throughput.requests_per_minute;
    renderProviderHealth(providers);
    renderCategories(categories);
    renderCapacity(capacity);
    renderLifecycle(lifecycle);

    // Phase 5 — render new metrics (graceful on failure)
    if (cacheResponse.ok) renderCacheMetrics(await cacheResponse.json());
    if (scoresResponse.ok) renderProviderScores(await scoresResponse.json());
    if (healthResponse.ok) renderOrchestrationHealth(await healthResponse.json());
    if (costsResponse.ok) renderCostMetrics(await costsResponse.json());
    if (failoverResponse.ok) renderCooldowns(await failoverResponse.json());
    if (dedupResponse.ok) renderDedupMetrics(await dedupResponse.json());
    if (diagnosticsResponse.ok) renderDiagnostics(await diagnosticsResponse.json());
  } catch (error) {
    backendTotal.textContent = "--";
    backendFailures.textContent = "--";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const prompt = promptInput.value.trim();
  if (!prompt) {
    formMessage.textContent = "Enter a prompt before submitting.";
    formMessage.className = "form-message error";
    return;
  }

  requestCount += 1;
  requestsSent.textContent = requestCount;
  formMessage.textContent = "";
  formMessage.className = "form-message";
  responseOutput.textContent = "Awaiting backend response...";
  requestId.textContent = "--";
  providerUsed.textContent = "--";
  modelUsed.textContent = "--";
  inferenceLatency.textContent = "--";
  requestCategory.textContent = "--";
  fallbackUsed.textContent = "--";
  requestPriority.textContent = "--";
  lifecycleState.textContent = "--";
  queueWait.textContent = "--";
  executionDuration.textContent = "--";
  setState("Loading", "loading");
  setLoading(true);

  const startedAt = performance.now();

  try {
    const response = await fetch(`${API_BASE_URL}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ prompt, session_id: activeSessionId }),
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Request failed.");
    }

    successCount += 1;
    if (payload.session_id && payload.session_id !== activeSessionId) {
      activeSessionId = payload.session_id;
      localStorage.setItem("qorvexis.activeSessionId", activeSessionId);
    }
    successfulWrites.textContent = successCount;
    requestId.textContent = payload.request_id;
    responseOutput.textContent = payload.response;
    providerUsed.textContent = payload.provider;
    modelUsed.textContent = payload.model;
    inferenceLatency.textContent = `${payload.latency_ms} ms`;
    requestCategory.textContent = payload.category;
    fallbackUsed.textContent = payload.fallback_used
      ? `Yes (${payload.original_provider} -> ${payload.provider})`
      : "No";
    requestPriority.textContent = payload.priority;
    lifecycleState.textContent = payload.lifecycle_state;
    queueWait.textContent = formatLatency(payload.queue_wait_ms);
    executionDuration.textContent = formatLatency(payload.execution_duration_ms);
    lastProvider.textContent = payload.provider;
    // Phase 5 — display new response fields
    cacheHitEl.textContent = payload.cache_hit ? "Yes" : "No";
    deduplicatedEl.textContent = payload.deduplicated ? "Yes" : "No";
    estimatedCostEl.textContent = payload.estimated_cost !== null && payload.estimated_cost !== undefined
      ? `$${payload.estimated_cost.toFixed(6)}`
      : "--";
    setState("Stored", "success");
    await refreshSessions();
    await loadSessionHistory();
    await refreshMetrics();
  } catch (error) {
    responseOutput.textContent = "Unable to complete request.";
    formMessage.textContent = error.message || "Unexpected backend error.";
    formMessage.className = "form-message error";
    setState("Error", "error");
  } finally {
    const elapsed = Math.round(performance.now() - startedAt);
    lastLatency.textContent = `${elapsed} ms`;
    setLoading(false);
  }
});

newSessionButton.addEventListener("click", async () => {
  try {
    await createSession();
    responseOutput.textContent = "New operational session ready.";
    setState("Idle", "");
  } catch (error) {
    formMessage.textContent = error.message || "Unable to create session.";
    formMessage.className = "form-message error";
  }
});

sessionList.addEventListener("click", async (event) => {
  const button = event.target.closest(".session-item");
  if (!button) {
    return;
  }

  setActiveSession({
    id: button.dataset.sessionId,
    title: button.dataset.sessionTitle,
  });
  await refreshSessions();
  await loadSessionHistory();
});

async function initializeDashboard() {
  try {
    await refreshSessions();
    if (!activeSessionId) {
      await createSession();
    }
    await loadSessionHistory();
  } catch (error) {
    currentSessionName.textContent = "Session service unavailable";
  }
  await refreshMetrics();
}

initializeDashboard();
setInterval(refreshMetrics, 30000);
