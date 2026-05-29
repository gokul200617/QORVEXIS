/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   Qorvexis â€” Infrastructure Intelligence Platform
   Frontend Controller v9 â€” Full data binding stabilisation
   All field names verified against live backend responses.
   â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

const isDev = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost';
const API_BASE_URL = isDev ? "http://127.0.0.1:8000" : "https://api.qorvexis.com";

// â”€â”€ State â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
let requestCount       = 0;
let successCount       = 0;
let activeSessionId    = localStorage.getItem("qorvexis.activeSessionId");
let activeSessionTitle = "New operational session";
let currentView        = "overview";

// â”€â”€ Centralized API Client â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const apiClient = {
  defaultTimeoutMs: 15000,
  maxRetries: 2,

  async fetchWithTimeout(url, options = {}) {
    const timeout    = options.timeout || this.defaultTimeoutMs;
    const controller = new AbortController();
    const id         = setTimeout(() => controller.abort(), timeout);
    try {
      const res = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(id);
      return res;
    } catch (err) {
      clearTimeout(id);
      throw err;
    }
  },

  async request(url, options = {}, retries = this.maxRetries) {
    try {
      const res = await this.fetchWithTimeout(url, options);
      if (!res.ok) {
        if (res.status >= 500 && retries > 0) {
          await new Promise(r => setTimeout(r, 500));
          return this.request(url, options, retries - 1);
        }
        throw new Error(`API error ${res.status}: ${res.statusText}`);
      }
      return await res.json();
    } catch (err) {
      if (err.name === "AbortError") {
        console.warn(`[Qorvexis] Timeout: ${url}`);
        return { _error: true, reason: "timeout" };
      }
      if (retries > 0 && (err.message.includes("fetch") || err.message.includes("Failed"))) {
        await new Promise(r => setTimeout(r, 500));
        return this.request(url, options, retries - 1);
      }
      console.warn(`[Qorvexis] Failed: ${url}`, err.message);
      return { _error: true, reason: err.message };
    }
  },

  async get(endpoint) {
    return this.request(`${API_BASE_URL}${endpoint}`);
  },

  async post(endpoint, body) {
    return this.request(`${API_BASE_URL}${endpoint}`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
  },
};

// â”€â”€ DOM: Topbar / Nav â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const sidebar           = document.getElementById("sidebar");
const sidebarToggle     = document.getElementById("sidebarToggle");
const appShell          = document.getElementById("appShell");
const themeToggle       = document.getElementById("themeToggle");
const iconSun           = document.querySelector(".icon-sun");
const iconMoon          = document.querySelector(".icon-moon");
const apiTarget         = document.getElementById("apiTarget");
const systemHealthPill  = document.getElementById("systemHealthPill");
const systemHealthLabel = document.getElementById("systemHealthLabel");
const manualRefreshBtn  = document.getElementById("manualRefreshBtn");

// â”€â”€ DOM: Workload Form â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const form            = document.getElementById("promptForm");
const promptInput     = document.getElementById("promptInput");
const submitButton    = document.getElementById("submitButton");
const responseOutput  = document.getElementById("responseOutput");
const requestState    = document.getElementById("requestState");
const formMessage     = document.getElementById("formMessage");

// â”€â”€ DOM: Response meta cells â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const requestId        = document.getElementById("requestId");
const providerUsed     = document.getElementById("providerUsed");
const modelUsed        = document.getElementById("modelUsed");
const inferenceLatency = document.getElementById("inferenceLatency");
const requestCategory  = document.getElementById("requestCategory");
const fallbackUsed     = document.getElementById("fallbackUsed");
const requestPriority  = document.getElementById("requestPriority");
const lifecycleState   = document.getElementById("lifecycleState");
const queueWait        = document.getElementById("queueWait");
const executionDuration = document.getElementById("executionDuration");
const cacheHitEl       = document.getElementById("cacheHit");
const deduplicatedEl   = document.getElementById("deduplicated");
const estimatedCostEl  = document.getElementById("estimatedCost");
const lastLatency      = document.getElementById("lastLatency");

// â”€â”€ DOM: Overview KPIs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const kpiMonthlySavings  = document.getElementById("kpiMonthlySavings");
const kpiGpuUtil         = document.getElementById("kpiGpuUtil");
const kpiGpuSub          = document.getElementById("kpiGpuSub");
const kpiGpuBadge        = document.getElementById("kpiGpuBadge");
const kpiActiveWorkloads = document.getElementById("kpiActiveWorkloads");
const kpiQueueSub        = document.getElementById("kpiQueueSub");
const kpiSuccessRate     = document.getElementById("kpiSuccessRate");
const kpiTotalRequests   = document.getElementById("kpiTotalRequests");
const kpiWorkloadsBadge  = document.getElementById("kpiWorkloadsBadge");
const kpiSuccessBadge    = document.getElementById("kpiSuccessBadge");

// â”€â”€ DOM: Orchestration health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const orchestrationHealth = document.getElementById("orchestrationHealth");
const orchHealthScore     = document.getElementById("orchHealthScore");

// â”€â”€ DOM: Throughput stats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const requestsPerMinute = document.getElementById("requestsPerMinute");
const avgQueueWait      = document.getElementById("avgQueueWait");
const avgExecution      = document.getElementById("avgExecution");
const completedRequests = document.getElementById("completedRequests");
const fallbackUsage     = document.getElementById("fallbackUsage");
const averageLatency    = document.getElementById("averageLatency");

// â”€â”€ DOM: Sessions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const newSessionButton   = document.getElementById("newSessionButton");
const currentSessionName = document.getElementById("currentSessionName");
const sessionList        = document.getElementById("sessionList");
const sessionHistory     = document.getElementById("sessionHistory");
const requestsSent       = document.getElementById("requestsSent");
const successfulWrites   = document.getElementById("successfulWrites");
const backendTotal       = document.getElementById("backendTotal");
const backendFailures    = document.getElementById("backendFailures");
const lastProvider       = document.getElementById("lastProvider");

// â”€â”€ DOM: Queue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const queueDepth           = document.getElementById("queueDepth");
const activeExecutions     = document.getElementById("activeExecutions");
const queueAnomalies       = document.getElementById("queueAnomalies");
const integrityViolations  = document.getElementById("integrityViolations");
const activeQueueInspector = document.getElementById("activeQueueInspector");
const violationLog         = document.getElementById("violationLog");
const recoveryActions      = document.getElementById("recoveryActions");
const recovActionsAlt      = document.getElementById("recovActionsAlt");
const schedulerDecisions   = document.getElementById("schedulerDecisions");

// â”€â”€ DOM: Cost â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const totalCost             = document.getElementById("totalCost");
const avgCostPerRequest     = document.getElementById("avgCostPerRequest");
const totalTokens           = document.getElementById("totalTokens");
const heuristicMonthlyCost  = document.getElementById("heuristicMonthlyCost");
const heuristicCacheSavings = document.getElementById("heuristicCacheSavings");
const heuristicDedupSavings = document.getElementById("heuristicDedupSavings");
const heuristicSessionCost  = document.getElementById("heuristicSessionCost");
const cacheHitRatio         = document.getElementById("cacheHitRatio");
const cacheHitsMisses       = document.getElementById("cacheHitsMisses");
const cacheEntries          = document.getElementById("cacheEntries");
const cacheEvictions        = document.getElementById("cacheEvictions");
const dedupCount            = document.getElementById("dedupCount");
const dedupRate             = document.getElementById("dedupRate");
const providerCostBreakdown = document.getElementById("providerCostBreakdown");

// â”€â”€ DOM: Provider â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const providerHealth    = document.getElementById("providerHealth");
const providerScores    = document.getElementById("providerScores");
const providerCooldowns = document.getElementById("providerCooldowns");
const providerCapacity  = document.getElementById("providerCapacity");

// â”€â”€ DOM: Workloads â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const executionTimelines = document.getElementById("executionTimelines");
const lifecycleBreakdown = document.getElementById("lifecycleBreakdown");
const categoryBreakdown  = document.getElementById("categoryBreakdown");

// â”€â”€ DOM: Infrastructure â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const infraCpu            = document.getElementById("infraCpu");
const infraMemory         = document.getElementById("infraMemory");
const infraDisk           = document.getElementById("infraDisk");
const infraPlatform       = document.getElementById("infraPlatform");
const infraCpuBar         = document.getElementById("infraCpuBar");
const infraMemoryBar      = document.getElementById("infraMemoryBar");
const infraDiskBar        = document.getElementById("infraDiskBar");
const infraCpuPressure    = document.getElementById("infraCpuPressure");
const infraMemoryPressure = document.getElementById("infraMemoryPressure");
const infraDiskPressure   = document.getElementById("infraDiskPressure");
const infraPythonVersion  = document.getElementById("infraPythonVersion");
const infraLastUpdatedLabel = document.getElementById("infraLastUpdatedLabel");
const infraHost           = document.getElementById("infraHost");
const infraLoadAvg        = document.getElementById("infraLoadAvg");
const infraDiskFree       = document.getElementById("infraDiskFree");
const infraMemAvail       = document.getElementById("infraMemAvail");
const gpuAvailBadge       = document.getElementById("gpuAvailBadge");
const gpuMetricsContent   = document.getElementById("gpuMetricsContent");
const gpuDetailContent    = document.getElementById("gpuDetailContent");
const gpuDetailBadge      = document.getElementById("gpuDetailBadge");

// â”€â”€ DOM: Optimization â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const recommendationsList = document.getElementById("recommendationsList");
const recsGeneratedAt     = document.getElementById("recsGeneratedAt");

// â”€â”€ DOM: Telemetry view â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const telCpu        = document.getElementById("telCpu");
const telMemory     = document.getElementById("telMemory");
const telDisk       = document.getElementById("telDisk");
const telLoad       = document.getElementById("telLoad");
const telGpuContent = document.getElementById("telGpuContent");

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// THEME
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function setTheme(theme) {
  const isLight = theme === "light";
  document.body.classList.toggle("theme-light", isLight);
  document.body.classList.toggle("theme-dark", !isLight);
  document.documentElement.setAttribute("data-theme", theme);
  if (iconSun)  iconSun.style.display  = isLight ? "none"  : "block";
  if (iconMoon) iconMoon.style.display = isLight ? "block" : "none";
  localStorage.setItem("qorvexis.theme", theme);
}

function initializeTheme() {
  const saved = localStorage.getItem("qorvexis.theme") || "dark";
  setTheme(saved);
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const next = document.body.classList.contains("theme-dark") ? "light" : "dark";
    setTheme(next);
  });
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// SIDEBAR
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function setSidebarState(collapsed) {
  sidebar.classList.toggle("collapsed", collapsed);
  appShell.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem("qorvexis.sidebarCollapsed", collapsed ? "1" : "0");
}

if (sidebarToggle) {
  sidebarToggle.addEventListener("click", () => {
    const isCollapsed = sidebar.classList.contains("collapsed");
    if (window.innerWidth <= 768) {
      sidebar.classList.toggle("mobile-open");
    } else {
      setSidebarState(!isCollapsed);
    }
  });
}

(function restoreSidebar() {
  if (window.innerWidth <= 768) return;
  if (localStorage.getItem("qorvexis.sidebarCollapsed") === "1") {
    setSidebarState(true);
  }
})();

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// NAVIGATION
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function navigateTo(section) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

  const view = document.getElementById(`view-${section}`);
  if (view) view.classList.add("active");

  const navItem = document.getElementById(`nav-${section}`);
  if (navItem) navItem.classList.add("active");

  currentView = section;

  if (window.innerWidth <= 768) {
    sidebar.classList.remove("mobile-open");
  }
}

document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", e => {
    e.preventDefault();
    navigateTo(item.dataset.section);
  });
});

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// UTILITIES
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(value, fallback = "--") {
  return value !== null && value !== undefined ? String(value) : fallback;
}

function fmtMs(value) {
  if (value === null || value === undefined) return "--";
  const n = Math.round(Number(value));
  return n === 0 ? "0 ms" : `${n} ms`;
}

function fmtPct(value) {
  return value !== null && value !== undefined ? `${Number(value).toFixed(1)}%` : "--";
}

function fmtUsd(value) {
  if (value === null || value === undefined) return "--";
  const n = Number(value);
  return n === 0 ? "$0.00" : `$${n.toFixed(n < 0.01 ? 6 : 2)}`;
}

function fmtBytes(bytes) {
  if (!bytes) return "--";
  const gb = bytes / 1073741824;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / 1048576;
  return `${mb.toFixed(0)} MB`;
}

function fmtTime(iso) {
  if (!iso) return "--";
  try { return new Date(iso).toLocaleTimeString(); } catch { return iso; }
}

function pressureClass(pressure) {
  const map = {
    low: "pressure-low", medium: "pressure-medium",
    high: "pressure-high", critical: "pressure-high",
    idle: "pressure-idle", unavailable: "pressure-unavailable", unknown: "pressure-unavailable",
  };
  return map[pressure] || "";
}

function pressureBarClass(pressure) {
  if (pressure === "high" || pressure === "critical") return "pressure-high";
  if (pressure === "medium") return "pressure-medium";
  return "pressure-low";
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// REQUEST STATE CHIP
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function setState(label, cls) {
  if (!requestState) return;
  requestState.textContent = label;
  requestState.className = `state-chip ${cls || ""}`.trim();
}

function setLoading(isLoading) {
  if (!submitButton) return;
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? "Submittingâ€¦" : "Submit workload";
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// SYSTEM HEALTH PILL
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function setSystemHealth(ok) {
  if (!systemHealthPill) return;
  systemHealthPill.classList.toggle("degraded", !ok);
  if (systemHealthLabel) systemHealthLabel.textContent = ok ? "Operational" : "Degraded";
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// SESSIONS
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function setActiveSession(session) {
  activeSessionId    = session.id;
  activeSessionTitle = session.title;
  localStorage.setItem("qorvexis.activeSessionId", activeSessionId);
  if (currentSessionName) currentSessionName.textContent = activeSessionTitle;
}

async function createSession(title = "New operational session") {
  const session = await apiClient.post("/sessions", { title });
  if (session._error) throw new Error("Unable to create session.");
  setActiveSession(session);
  await refreshSessions();
  await loadSessionHistory();
}

async function refreshSessions() {
  const sessions = await apiClient.get("/sessions");
  if (sessions._error) return;

  if (sessions.length === 0) {
    activeSessionId = null;
    localStorage.removeItem("qorvexis.activeSessionId");
    if (currentSessionName) currentSessionName.textContent = "No active session";
    if (sessionList) sessionList.innerHTML = '<span class="empty-state">No sessions yet.</span>';
    return;
  }

  if (!activeSessionId || !sessions.some(s => s.id === activeSessionId)) {
    setActiveSession(sessions[0]);
  } else {
    const active = sessions.find(s => s.id === activeSessionId);
    if (active) setActiveSession(active);
  }

  if (sessionList) {
    sessionList.innerHTML = sessions.map(s => `
      <button
        type="button"
        class="session-btn ${s.id === activeSessionId ? "active" : ""}"
        data-session-id="${escapeHtml(s.id)}"
        data-session-title="${escapeHtml(s.title)}"
      >${escapeHtml(s.title)}</button>
    `).join("");
  }
}

async function loadSessionHistory() {
  if (!activeSessionId || !sessionHistory) return;
  const history = await apiClient.get(`/sessions/${activeSessionId}/requests`);
  if (history._error) return;

  if (history.length === 0) {
    sessionHistory.innerHTML = '<span class="empty-state">No requests in this session yet.</span>';
    return;
  }

  sessionHistory.innerHTML = history.slice(-8).reverse().map(item => `
    <div class="data-row">
      <strong>${escapeHtml(item.category || "general")} â€” ${escapeHtml(item.provider || item.status || "--")}</strong>
      <span>${escapeHtml(item.prompt)}</span>
    </div>
  `).join("");
}

if (newSessionButton) {
  newSessionButton.addEventListener("click", async () => {
    try {
      await createSession();
      setState("Idle", "");
    } catch (err) {
      if (formMessage) { formMessage.textContent = err.message; formMessage.className = "form-message error"; }
    }
  });
}

if (sessionList) {
  sessionList.addEventListener("click", async e => {
    const btn = e.target.closest(".session-btn");
    if (!btn) return;
    setActiveSession({ id: btn.dataset.sessionId, title: btn.dataset.sessionTitle });
    await refreshSessions();
    await loadSessionHistory();
  });
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// WORKLOAD FORM
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if (form) {
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const prompt = promptInput ? promptInput.value.trim() : "";
    if (!prompt) {
      if (formMessage) { formMessage.textContent = "Enter a prompt before submitting."; formMessage.className = "form-message error"; }
      return;
    }

    requestCount++;
    if (requestsSent) requestsSent.textContent = requestCount;
    if (formMessage) { formMessage.textContent = ""; formMessage.className = "form-message"; }
    if (responseOutput) responseOutput.textContent = "Routing workload through control planeâ€¦";

    [requestId, providerUsed, modelUsed, inferenceLatency, requestCategory,
     fallbackUsed, requestPriority, lifecycleState, queueWait, executionDuration,
     cacheHitEl, deduplicatedEl, estimatedCostEl, lastLatency]
      .forEach(el => { if (el) el.textContent = "--"; });

    setState("Loading", "loading");
    setLoading(true);
    const t0 = performance.now();

    try {
      const payload = await apiClient.post("/ask", { prompt, session_id: activeSessionId });
      if (payload._error) throw new Error(payload.reason || "Request failed.");

      successCount++;
      if (payload.session_id && payload.session_id !== activeSessionId) {
        activeSessionId = payload.session_id;
        localStorage.setItem("qorvexis.activeSessionId", activeSessionId);
      }
      if (successfulWrites) successfulWrites.textContent = successCount;
      if (responseOutput)   responseOutput.textContent   = payload.response;

      if (requestId)         requestId.textContent         = fmt(payload.request_id);
      if (providerUsed)      providerUsed.textContent      = fmt(payload.provider);
      if (modelUsed)         modelUsed.textContent         = fmt(payload.model);
      if (inferenceLatency)  inferenceLatency.textContent  = payload.latency_ms ? `${payload.latency_ms} ms` : "--";
      if (requestCategory)   requestCategory.textContent   = fmt(payload.category);
      if (fallbackUsed)      fallbackUsed.textContent      = payload.fallback_used
        ? `Yes (${payload.original_provider} â†’ ${payload.provider})` : "No";
      if (requestPriority)   requestPriority.textContent   = fmt(payload.priority);
      if (lifecycleState)    lifecycleState.textContent    = fmt(payload.lifecycle_state);
      if (queueWait)         queueWait.textContent         = fmtMs(payload.queue_wait_ms);
      if (executionDuration) executionDuration.textContent = fmtMs(payload.execution_duration_ms);
      if (cacheHitEl)        cacheHitEl.textContent        = payload.cache_hit ? "Yes" : "No";
      if (deduplicatedEl)    deduplicatedEl.textContent    = payload.deduplicated ? "Yes" : "No";
      if (estimatedCostEl)   estimatedCostEl.textContent   = fmtUsd(payload.estimated_cost);
      if (lastProvider)      lastProvider.textContent      = fmt(payload.provider);

      setState("Stored", "success");
      setSystemHealth(true);
      await refreshSessions();
      await loadSessionHistory();
      await refreshMetrics();
    } catch (err) {
      if (responseOutput) responseOutput.textContent = "Request failed.";
      if (formMessage) { formMessage.textContent = err.message || "Unexpected error."; formMessage.className = "form-message error"; }
      setState("Error", "error");
    } finally {
      const elapsed = Math.round(performance.now() - t0);
      if (lastLatency) lastLatency.textContent = `${elapsed} ms`;
      setLoading(false);
    }
  });
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// RENDER HELPERS â€” All field names verified against live backend payloads
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// /metrics/orchestration/health
// { orchestration_health_score, components: { provider_reliability, queue_efficiency,
//   execution_efficiency, cache_efficiency, failover_health } }
function renderOrchestrationHealth(data) {
  if (!orchestrationHealth) return;

  const score = data.orchestration_health_score;
  if (score === undefined) {
    orchestrationHealth.innerHTML = '<span class="empty-state">No health data yet.</span>';
    return;
  }

  const c   = data.components || {};
  const cls = score >= 75 ? "health-ok" : score >= 40 ? "health-warn" : "health-critical";
  if (orchHealthScore) orchHealthScore.textContent = `${score}/100`;
  setSystemHealth(score >= 40);

  const componentRows = Object.entries(c).map(([key, val]) => {
    const compCls = val >= 75 ? "health-ok" : val >= 40 ? "health-warn" : "health-critical";
    return `<div class="data-row">
      <strong>${escapeHtml(key.replace(/_/g, " "))}</strong>
      <span class="${compCls}">${val} / 100</span>
    </div>`;
  }).join("");

  orchestrationHealth.innerHTML = `
    <div class="data-row" style="border-bottom: 1px solid var(--border); margin-bottom: 8px; padding-bottom: 8px;">
      <strong class="${cls}">Overall: ${score}/100</strong>
      <span>${score >= 75 ? "Healthy" : score >= 40 ? "Degraded" : "Critical"}</span>
    </div>
    ${componentRows}
  `;
}

// /metrics/providers
// { providers: [ { provider, total_requests, failure_count, success_rate, average_latency_ms, last_success_at } ] }
function renderProviderHealth(data) {
  if (!providerHealth) return;
  const list = data.providers || [];
  if (!list.length) { providerHealth.innerHTML = '<span class="empty-state">No provider data yet.</span>'; return; }
  providerHealth.innerHTML = list.map(p => {
    const cls = p.success_rate >= 95 ? "health-ok" : p.success_rate >= 70 ? "health-warn" : "health-critical";
    return `<div class="data-row">
      <strong>${escapeHtml(p.provider)}</strong>
      <span class="${cls}">${p.success_rate}% success Â· ${p.total_requests} req Â· ${p.failure_count} fail Â· ${fmtMs(p.average_latency_ms)} avg</span>
    </div>`;
  }).join("");
}

// /metrics/providers/score
// { providers: [ { provider, score, success_count, failure_count, request_count, average_latency_ms, success_rate } ] }
function renderProviderScores(data) {
  if (!providerScores) return;
  const list = data.providers || [];
  if (!list.length) { providerScores.innerHTML = '<span class="empty-state">No scoring data yet.</span>'; return; }
  providerScores.innerHTML = list.map(p => {
    const cls = p.score >= 70 ? "health-ok" : p.score >= 40 ? "health-warn" : "health-critical";
    return `<div class="data-row">
      <strong>${escapeHtml(p.provider)}</strong>
      <span class="${cls}">Score ${p.score}/100 Â· ${p.success_count} ok Â· ${p.failure_count} fail Â· ${fmtMs(p.average_latency_ms)} avg</span>
    </div>`;
  }).join("");
}

// /metrics/failover
// { providers: [ { provider, is_cooled_down, cooldown_remaining_seconds, total_cooldowns,
//   consecutive_failures, window_events, window_failure_rate } ] }
function renderCooldowns(data) {
  if (!providerCooldowns) return;
  const list = data.providers || [];
  if (!list.length) { providerCooldowns.innerHTML = '<span class="empty-state">No cooldown data yet.</span>'; return; }
  providerCooldowns.innerHTML = list.map(p => {
    const cls   = p.is_cooled_down ? "health-critical" : "health-ok";
    const label = p.is_cooled_down ? `Cooled down (${p.cooldown_remaining_seconds}s remaining)` : "Operational";
    return `<div class="data-row">
      <strong>${escapeHtml(p.provider)}</strong>
      <span class="${cls}">${label} Â· ${p.total_cooldowns} cooldowns Â· ${p.consecutive_failures} consecutive fail Â· ${p.window_failure_rate}% failure rate</span>
    </div>`;
  }).join("");
}

// /metrics/capacity
// { providers: [ { provider, active_requests, queued_requests, average_execution_ms,
//   failure_rate, concurrency_level, last_execution_at } ] }
function renderCapacity(data) {
  if (!providerCapacity) return;
  const list = data.providers || [];
  if (!list.length) { providerCapacity.innerHTML = '<span class="empty-state">No capacity data yet.</span>'; return; }
  providerCapacity.innerHTML = list.map(p => `
    <div class="data-row">
      <strong>${escapeHtml(p.provider)}</strong>
      <span>${p.active_requests} active Â· ${p.queued_requests} queued Â· limit ${p.concurrency_level} Â· ${fmtMs(p.average_execution_ms)} avg Â· ${p.failure_rate}% fail</span>
    </div>
  `).join("");
}

// /metrics/categories
// { categories: [ { category, total_requests, successful_requests, percentage } ] }
function renderCategories(data) {
  if (!categoryBreakdown) return;
  const list = data.categories || [];
  if (!list.length) { categoryBreakdown.innerHTML = '<span class="empty-state">No category data yet.</span>'; return; }
  categoryBreakdown.innerHTML = list.map(c => `
    <div class="data-row">
      <strong>${escapeHtml(c.category)}</strong>
      <span>${c.total_requests} requests Â· ${c.percentage}% of traffic Â· ${c.successful_requests} ok</span>
    </div>
  `).join("");
}

// /metrics/lifecycle
// { states: [ { state, count } ], priorities: [ { priority, count } ] }
function renderLifecycle(data) {
  if (!lifecycleBreakdown) return;
  const states     = data.states || [];
  const priorities = data.priorities || [];
  if (!states.length && !priorities.length) {
    lifecycleBreakdown.innerHTML = '<span class="empty-state">No lifecycle data yet.</span>';
    return;
  }
  lifecycleBreakdown.innerHTML = [
    ...states.map(s     => `<div class="data-row"><strong>${escapeHtml(s.state)}</strong><span>${s.count} requests</span></div>`),
    ...priorities.map(p => `<div class="data-row"><strong>${escapeHtml(p.priority)} priority</strong><span>${p.count} requests</span></div>`),
  ].join("");
}

// /metrics/cache
// { entries, max_entries, ttl_seconds, hits, misses, evictions, total_lookups, hit_ratio }
function renderCacheMetrics(data) {
  if (cacheHitRatio)   cacheHitRatio.textContent   = data.hit_ratio !== undefined ? `${data.hit_ratio}%` : "--";
  if (cacheHitsMisses) cacheHitsMisses.textContent = `${data.hits || 0} / ${data.misses || 0}`;
  if (cacheEntries)    cacheEntries.textContent    = `${data.entries || 0} / ${data.max_entries || 0}`;
  if (cacheEvictions)  cacheEvictions.textContent  = fmt(data.evictions, "0");
}

// /metrics/dedup
// { active_entries, window_seconds, duplicates_detected, total_checked, dedup_rate }
function renderDedupMetrics(data) {
  if (dedupCount) dedupCount.textContent = fmt(data.duplicates_detected, "0");
  if (dedupRate)  dedupRate.textContent  = data.dedup_rate !== undefined ? `${data.dedup_rate}%` : "--";
}

// /metrics/costs
// { total_estimated_cost, total_prompt_tokens, total_response_tokens, total_requests,
//   average_cost_per_request, providers: [...], infrastructure_cost_heuristics: {...} }
function renderCostMetrics(data) {
  if (totalCost)         totalCost.textContent         = fmtUsd(data.total_estimated_cost);
  if (avgCostPerRequest) avgCostPerRequest.textContent = fmtUsd(data.average_cost_per_request);
  if (totalTokens) {
    const tokens = (data.total_prompt_tokens || 0) + (data.total_response_tokens || 0);
    totalTokens.textContent = tokens ? tokens.toLocaleString() : "0";
  }

  if (providerCostBreakdown) {
    const providers = data.providers || [];
    if (providers.length) {
      providerCostBreakdown.innerHTML = providers.map(p => `
        <div class="cost-row">
          <div>
            <div class="cost-provider-name">${escapeHtml(p.provider)}</div>
            <div class="cost-tokens">${(p.total_prompt_tokens || 0) + (p.total_response_tokens || 0)} tokens</div>
          </div>
          <div class="cost-amount">${fmtUsd(p.estimated_cost)}</div>
        </div>
      `).join("");
    } else {
      providerCostBreakdown.innerHTML = '<span class="empty-state">No cost breakdown yet.</span>';
    }
  }

  const h = data.infrastructure_cost_heuristics;
  if (h && h.label !== "heuristic unavailable") {
    if (heuristicMonthlyCost)  heuristicMonthlyCost.textContent  = fmtUsd(h.heuristic_monthly_cost_estimate_usd);
    if (heuristicCacheSavings) heuristicCacheSavings.textContent = fmtUsd(h.estimated_cache_savings_usd);
    if (heuristicDedupSavings) heuristicDedupSavings.textContent = fmtUsd(h.estimated_dedup_savings_usd);
    if (heuristicSessionCost)  heuristicSessionCost.textContent  = fmtUsd(h.total_estimated_session_cost_usd);

    const totalSavings = (h.estimated_cache_savings_usd || 0) + (h.estimated_dedup_savings_usd || 0);
    if (kpiMonthlySavings) kpiMonthlySavings.textContent = fmtUsd(totalSavings);
  }
}

// /metrics/diagnostics
// { queue: { queue_depth, active_executions, ... , queued_items: [...] },
//   integrity: { violation_count, recent_violations: [...] },
//   recovery: { recovery_action_count },
//   timelines: [...],   transitions: [...] }
function renderDiagnostics(data) {
  const queue      = data.queue      || {};
  const integrity  = data.integrity  || {};
  const items      = queue.queued_items   || [];
  const timelines  = (data.timelines  || []).slice(0, 10);
  const violations = (integrity.recent_violations || []).slice(0, 8);
  const transitions = (data.transitions || []).slice(0, 8);

  // Queue mini KPIs
  if (integrityViolations) integrityViolations.textContent = fmt(integrity.violation_count, "0");
  if (queueAnomalies)      queueAnomalies.textContent      = fmt(queue.queue_anomalies, "0");

  // Recovery actions come from /metrics/recovery separately â€” set badge if available
  // (diagnostics does not include recovery sub-key by default)

  // Active queue inspector
  if (activeQueueInspector) {
    activeQueueInspector.innerHTML = items.length ? items.map(item => `
      <div class="data-row">
        <strong>#${item.request_id} Â· ${escapeHtml(item.provider || "pending")}</strong>
        <span>queued ${fmtMs(item.queue_wait_ms)}</span>
      </div>
    `).join("") : '<span class="empty-state">Queue is empty.</span>';
  }

  // Execution timelines (Workloads view)
  if (executionTimelines) {
    executionTimelines.innerHTML = timelines.length ? timelines.map(item => `
      <div class="data-row">
        <strong>#${item.request_id} Â· ${escapeHtml(item.lifecycle_state || "--")}</strong>
        <span>${escapeHtml(item.provider || "unassigned")} Â· queue ${fmtMs(item.queue_wait_ms)} Â· exec ${fmtMs(item.execution_duration_ms)}</span>
        <span>${fmtTime(item.received_at)} â†’ ${fmtTime(item.completed_at)}</span>
      </div>
    `).join("") : '<span class="empty-state">No timelines yet.</span>';
  }

  // Violation log
  if (violationLog) {
    violationLog.innerHTML = violations.length ? violations.map(v => `
      <div class="data-row">
        <strong>#${v.request_id || "--"} Â· ${escapeHtml(v.reason || "violation")}</strong>
        <span>${escapeHtml(v.current_state || "unknown")} â†’ ${escapeHtml(v.attempted_state || "--")}</span>
      </div>
    `).join("") : '<span class="empty-state">No violations recorded.</span>';
  }

  // Scheduler / lifecycle transitions
  if (schedulerDecisions) {
    schedulerDecisions.innerHTML = transitions.length ? transitions.map(t => `
      <div class="data-row">
        <strong>#${t.request_id} Â· ${escapeHtml(t.state)}</strong>
        <span>${escapeHtml(t.detail || "transition")} Â· ${fmtTime(t.created_at)}</span>
      </div>
    `).join("") : '<span class="empty-state">No lifecycle transitions yet.</span>';
  }
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// METRICS POLLING â€” 30s interval with lock
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

let isRefreshingMetrics = false;

async function fetchAndRender(endpoint, renderFn) {
  const data = await apiClient.get(endpoint);
  if (data._error) {
    console.warn(`[Qorvexis] ${endpoint} unavailable â€” keeping last state.`);
    return;
  }
  try {
    renderFn(data);
  } catch (err) {
    console.warn(`[Qorvexis] Render error for ${endpoint}:`, err);
  }
}

async function refreshMetrics() {
  if (isRefreshingMetrics) return;
  isRefreshingMetrics = true;
  console.debug("[Qorvexis] refreshMetrics cycle start");

  try {
    await Promise.allSettled([

      // â”€â”€ Overview KPIs + Sessions panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/overview", (d) => {
        if (backendTotal)      backendTotal.textContent      = fmt(d.total_requests, "0");
        if (backendFailures)   backendFailures.textContent   = fmt(d.failed_requests, "0");
        if (averageLatency)    averageLatency.textContent    = fmtMs(d.average_latency_ms);
        if (fallbackUsage)     fallbackUsage.textContent     = `${d.fallback_count || 0} (${(d.fallback_rate || 0).toFixed(1)}%)`;

        // Success rate â€” use pre-calculated field from backend
        if (kpiSuccessRate)    kpiSuccessRate.textContent    = d.success_rate !== undefined ? `${d.success_rate}%` : "--%";
        if (kpiTotalRequests)  kpiTotalRequests.textContent  = `${d.total_requests || 0} total`;
        if (kpiSuccessBadge)   kpiSuccessBadge.textContent   = "all time";
      }),

      // â”€â”€ Queue KPIs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/queue", (d) => {
        if (queueDepth)          queueDepth.textContent          = fmt(d.queue_depth, "0");
        if (activeExecutions)    activeExecutions.textContent    = fmt(d.active_executions, "0");
        if (kpiActiveWorkloads)  kpiActiveWorkloads.textContent  = fmt(d.active_executions, "0");
        if (kpiQueueSub)         kpiQueueSub.textContent         = `${d.queue_depth || 0} queued`;
        if (kpiWorkloadsBadge)   kpiWorkloadsBadge.textContent   = d.active_executions > 0 ? "running" : "idle";
      }),

      // â”€â”€ Throughput panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      // Backend fields: requests_per_minute, average_queue_wait_ms, average_execution_duration_ms,
      //                 request_completion_count, request_cancellation_count, provider_throughput
      fetchAndRender("/metrics/throughput", (d) => {
        if (requestsPerMinute) requestsPerMinute.textContent = fmt(d.requests_per_minute, "0");
        if (avgQueueWait)      avgQueueWait.textContent      = fmtMs(d.average_queue_wait_ms);
        if (avgExecution)      avgExecution.textContent      = fmtMs(d.average_execution_duration_ms);
        if (completedRequests) completedRequests.textContent = fmt(d.request_completion_count, "0");
      }),

      // â”€â”€ Orchestration health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/orchestration/health", renderOrchestrationHealth),

      // â”€â”€ Provider health + scores + cooldowns + capacity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/providers",       renderProviderHealth),
      fetchAndRender("/metrics/providers/score", renderProviderScores),
      fetchAndRender("/metrics/failover",        renderCooldowns),
      fetchAndRender("/metrics/capacity",        renderCapacity),

      // â”€â”€ Workloads / lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/lifecycle",   renderLifecycle),
      fetchAndRender("/metrics/categories",  renderCategories),

      // â”€â”€ Cache / dedup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/cache", renderCacheMetrics),
      fetchAndRender("/metrics/dedup", renderDedupMetrics),

      // â”€â”€ Cost intelligence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/costs", renderCostMetrics),

      // â”€â”€ Diagnostics (queue inspector + timelines + violations) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
      fetchAndRender("/metrics/diagnostics", renderDiagnostics),

    ]);
  } finally {
    isRefreshingMetrics = false;
    console.debug("[Qorvexis] refreshMetrics cycle complete");
  }
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// TELEMETRY â€” 15s interval (Phase 7, independent of metrics)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function setBarPressure(barEl, pct, pressure) {
  if (!barEl) return;
  barEl.style.width  = `${Math.min(100, pct || 0)}%`;
  barEl.className    = `progress-bar-fill ${pressureBarClass(pressure)}`;
}

let isRefreshingTelemetry = false;

// /metrics/infrastructure
// { cpu_percent, memory_percent, disk_percent, memory_total_bytes, memory_available_bytes,
//   disk_total_bytes, disk_free_bytes, load_avg_1m, load_avg_5m, gpu_available,
//   platform, python_version, host_identifier, last_updated_at,
//   utilization_analysis: { cpu_pressure, memory_pressure, disk_pressure, gpu_pressure },
//   idle_resources: { idle_resources: [...], idle_count } }
async function fetchInfrastructureMetrics() {
  const data = await apiClient.get("/metrics/infrastructure");
  if (data._error || data.status === "telemetry_unavailable") return;

  const util = data.utilization_analysis || {};

  if (infraCpu) {
    infraCpu.textContent = fmtPct(data.cpu_percent);
    infraCpu.className   = `kpi-mini-value ${pressureClass(util.cpu_pressure)}`;
  }
  if (infraMemory) {
    infraMemory.textContent = fmtPct(data.memory_percent);
    infraMemory.className   = `kpi-mini-value ${pressureClass(util.memory_pressure)}`;
  }
  if (infraDisk) {
    infraDisk.textContent = fmtPct(data.disk_percent);
    infraDisk.className   = `kpi-mini-value ${pressureClass(util.disk_pressure)}`;
  }

  if (infraCpuPressure)    infraCpuPressure.textContent    = util.cpu_pressure    || "--";
  if (infraMemoryPressure) infraMemoryPressure.textContent = util.memory_pressure || "--";
  if (infraDiskPressure)   infraDiskPressure.textContent   = util.disk_pressure   || "--";

  setBarPressure(infraCpuBar,    data.cpu_percent,    util.cpu_pressure);
  setBarPressure(infraMemoryBar, data.memory_percent, util.memory_pressure);
  setBarPressure(infraDiskBar,   data.disk_percent,   util.disk_pressure);

  if (infraPlatform)      infraPlatform.textContent      = fmt(data.platform, "--");
  // Backend returns host_identifier (not hostname)
  if (infraHost)          infraHost.textContent          = fmt(data.host_identifier, "--");
  if (infraPythonVersion) infraPythonVersion.textContent = data.python_version ? `Python ${data.python_version}` : "--";
  if (infraLoadAvg)       infraLoadAvg.textContent       = data.load_avg_1m !== null && data.load_avg_1m !== undefined
    ? Number(data.load_avg_1m).toFixed(2) : "--";
  if (infraDiskFree)      infraDiskFree.textContent      = fmtBytes(data.disk_free_bytes);
  if (infraMemAvail)      infraMemAvail.textContent      = fmtBytes(data.memory_available_bytes);

  if (data.last_updated_at && infraLastUpdatedLabel) {
    infraLastUpdatedLabel.textContent = `Updated ${new Date(data.last_updated_at).toLocaleTimeString()}`;
  }

  // Mirror to Telemetry section
  if (telCpu)    telCpu.textContent    = fmtPct(data.cpu_percent);
  if (telMemory) telMemory.textContent = fmtPct(data.memory_percent);
  if (telDisk)   telDisk.textContent   = fmtPct(data.disk_percent);
  if (telLoad)   telLoad.textContent   = data.load_avg_1m !== null && data.load_avg_1m !== undefined
    ? Number(data.load_avg_1m).toFixed(2) : "--";

  // If no GPU detected, update the GPU hero KPI
  if (!data.gpu_available && kpiGpuUtil) {
    kpiGpuUtil.textContent = "N/A";
    if (kpiGpuSub)   kpiGpuSub.textContent   = "No GPU detected";
    if (kpiGpuBadge) kpiGpuBadge.textContent = "inactive";
  }
}

// /metrics/gpu
// { available, reason, last_updated_at }  â€” when no GPU
// { available, gpu_percent, gpu_memory_percent, gpu_memory_used_bytes, gpu_memory_total_bytes,
//   temperature_c, power_watts, gpu_device_name, gpu_device_count, last_updated_at } â€” when GPU present
async function fetchGpuMetrics() {
  const data = await apiClient.get("/metrics/gpu");
  if (data._error) return;

  // Backend uses "reason" for unavailability message
  const unavailReason  = data.reason || "pynvml not installed";
  // Backend uses gpu_device_name (not device_name)
  const deviceName     = data.device_name || null;

  const unavailHtml = `<div class="data-row"><strong>No GPU detected</strong><span>${escapeHtml(unavailReason)}</span></div>`;

  if (!data.available) {
    if (gpuAvailBadge)      gpuAvailBadge.textContent    = "unavailable";
    if (gpuMetricsContent)  gpuMetricsContent.innerHTML  = unavailHtml;
    if (gpuDetailContent)   gpuDetailContent.innerHTML   = unavailHtml;
    if (gpuDetailBadge)     gpuDetailBadge.textContent   = "unavailable";
    if (telGpuContent)      telGpuContent.innerHTML      = unavailHtml;
    return;
  }

  // Hero KPI
  if (kpiGpuUtil)  kpiGpuUtil.textContent  = fmtPct(data.gpu_percent);
  if (kpiGpuSub)   kpiGpuSub.textContent   = `${fmtPct(data.gpu_memory_percent)} VRAM`;
  if (kpiGpuBadge) {
    const util = data.gpu_percent || 0;
    kpiGpuBadge.textContent = util < 10 ? "idle" : util < 70 ? "active" : "high";
  }
  if (gpuAvailBadge)   gpuAvailBadge.textContent   = escapeHtml(deviceName || "detected");
  if (gpuDetailBadge)  gpuDetailBadge.textContent   = escapeHtml(deviceName || "GPU");

  const gpuHtml = `
    <div class="data-row">
      <strong>${escapeHtml(deviceName || "GPU")}</strong>
      <span>Utilization ${fmtPct(data.gpu_percent)} Â· VRAM ${fmtPct(data.gpu_memory_percent)}</span>
      ${data.temperature_c !== null && data.temperature_c !== undefined ? `<span>Temperature ${data.temperature_c}Â°C</span>` : ""}
      ${data.power_watts   !== null && data.power_watts   !== undefined ? `<span>Power ${data.power_watts} W</span>` : ""}
    </div>
  `;

  if (gpuMetricsContent) gpuMetricsContent.innerHTML = gpuHtml;
  if (gpuDetailContent)  gpuDetailContent.innerHTML  = gpuHtml;
  if (telGpuContent)     telGpuContent.innerHTML     = gpuHtml;
}

// /metrics/recommendations
// { count, last_updated_at, generated_at,
//   recommendations: [ { severity, title, detail, estimated_monthly_waste_usd, estimated_savings_usd } ] }
async function fetchRecommendations() {
  const data = await apiClient.get("/analytics/token/recommendations");
  if (data._error) return;

  const recs = data.recommendations || [];

  if (recsGeneratedAt && data.generated_at) {
    recsGeneratedAt.textContent = `Generated ${new Date(data.generated_at).toLocaleTimeString()}`;
  }

  if (!recommendationsList) return;

  if (!recs.length) {
    recommendationsList.innerHTML = `
      <div class="panel" style="grid-column:1/-1;text-align:center;padding:40px">
        <p style="font-size:1.1rem;font-weight:600;color:var(--emerald);margin-bottom:8px">All systems optimal</p>
        <p class="empty-state" style="font-style:normal">No active recommendations. Infrastructure looks healthy.</p>
      </div>
    `;
    return;
  }

  recommendationsList.innerHTML = recs.map(rec => {
    const sev    = escapeHtml(rec.severity || "info");
    const waste  = rec.estimated_monthly_waste_usd > 0
      ? `<span class="rec-waste"><span class="rec-impact-label">Est. waste </span>${fmtUsd(rec.estimated_monthly_waste_usd)}/mo</span>` : "";
    const saving = rec.estimated_savings_usd > 0
      ? `<span class="rec-saving"><span class="rec-impact-label">Est. savings </span>${fmtUsd(rec.estimated_savings_usd)}/mo</span>` : "";
    const impactHtml = (waste || saving) ? `<div class="rec-impact">${waste}${saving}</div>` : "";
    return `
      <div class="rec-card sev-${sev}">
        <div class="rec-header">
          <span class="rec-badge ${sev}">${sev}</span>
          <span class="rec-title">${escapeHtml(rec.title)}</span>
        </div>
        <div class="rec-detail">${escapeHtml(rec.detail)}</div>
        ${impactHtml}
      </div>
    `;
  }).join("");
}

async function refreshTelemetry() {
  if (isRefreshingTelemetry) return;
  isRefreshingTelemetry = true;
  try {
    await Promise.allSettled([
      fetchInfrastructureMetrics(),
      fetchGpuMetrics(),
      fetchRecommendations(),
    ]);
  } finally {
    isRefreshingTelemetry = false;
  }
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// INITIALIZE
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async function initializeDashboard() {
  if (apiTarget) apiTarget.textContent = new URL(API_BASE_URL).host;

  try {
    await refreshSessions();
    if (!activeSessionId) await createSession();
    await loadSessionHistory();
  } catch {
    if (currentSessionName) currentSessionName.textContent = "Session unavailable";
  }

  await refreshMetrics();
}

if (manualRefreshBtn) {
  manualRefreshBtn.addEventListener("click", async () => {
    manualRefreshBtn.textContent = "Refreshingâ€¦";
    manualRefreshBtn.disabled    = true;
    await Promise.allSettled([refreshMetrics(), refreshTelemetry()]);
    manualRefreshBtn.textContent = "Refresh now";
    manualRefreshBtn.disabled    = false;
  });
}

// â”€â”€ Boot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
initializeTheme();
initializeDashboard();
refreshTelemetry();

// Clear any ghost intervals from hot-reload, then set fresh ones
if (window._qorvexisMetricsInterval)    clearInterval(window._qorvexisMetricsInterval);
if (window._qorvexisTelemetryInterval)  clearInterval(window._qorvexisTelemetryInterval);
if (window._qorvexisOpenAIInterval)     clearInterval(window._qorvexisOpenAIInterval);

window._qorvexisMetricsInterval   = setInterval(refreshMetrics,   30000);  // 30s
window._qorvexisTelemetryInterval = setInterval(refreshTelemetry, 15000);  // 15s

// ─── Phase 8B: OpenAI Connector Logic ──────────────────────────────────────────

const openaiConnectForm    = document.getElementById("openaiConnectForm");
const openaiKeyInput       = document.getElementById("openaiKeyInput");
const openaiSubmitBtn      = document.getElementById("openaiSubmitBtn");
const openaiFormMessage    = document.getElementById("openaiFormMessage");
const openaiStatusBadge    = document.getElementById("openaiStatusBadge");

// Token Analytics DOM
const openaiAnalyticsGrid  = document.getElementById("openaiAnalyticsGrid");
const openaiTotalSpend     = document.getElementById("openaiTotalSpend");
const openaiMonthlySpend   = document.getElementById("openaiMonthlySpend");
const openaiMostExpensive  = document.getElementById("openaiMostExpensive");
const openaiEfficiency     = document.getElementById("openaiEfficiency");

// Health DOM
const connectorHealthPanel = document.getElementById("connectorHealthPanel");
const openaiHealthStatus   = document.getElementById("openaiHealthStatus");
const openaiSyncCount      = document.getElementById("openaiSyncCount");
const openaiLastSync       = document.getElementById("openaiLastSync");
const openaiConnectorId    = document.getElementById("openaiConnectorId");

// State
let isOpenAIConnected = false;

if (openaiConnectForm) {
  openaiConnectForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = openaiKeyInput.value.trim();
    if (!key) return;

    openaiSubmitBtn.disabled = true;
    openaiSubmitBtn.textContent = "Connecting...";
    openaiFormMessage.textContent = "";

    try {
      const res = await apiClient.post("/connectors/openai/authenticate", {
        api_key: key,
        name: "OpenAI Production"
      });

      if (res._error) throw new Error(res.reason || "Authentication failed");

      // Success
      isOpenAIConnected = true;
      openaiStatusBadge.textContent = "Connected";
      openaiStatusBadge.className = "panel-badge health-ok";
      openaiFormMessage.textContent = "Successfully authenticated!";
      openaiFormMessage.className = "form-message success";
      openaiKeyInput.value = "";
      
      // Show analytics and health panels
      openaiAnalyticsGrid.style.display = "grid";
      connectorHealthPanel.style.display = "block";
      
      // Update health details immediately
      openaiHealthStatus.textContent = "Connected";
      openaiSyncCount.textContent = res.sync_count;
      openaiLastSync.textContent = fmtTime(res.last_synced_at);
      openaiConnectorId.textContent = res.connector_id;
      
      // Trigger first usage fetch
      await fetchOpenAIUsage();
      
      // Start polling for usage
      window._qorvexisOpenAIInterval = setInterval(fetchOpenAIUsage, 15000); // 15s

    } catch (err) {
      openaiFormMessage.textContent = err.message || "Invalid API Key";
      openaiFormMessage.className = "form-message error";
      openaiStatusBadge.textContent = "Error";
      openaiStatusBadge.className = "panel-badge health-critical";
    } finally {
      openaiSubmitBtn.disabled = false;
      openaiSubmitBtn.textContent = "Connect API";
    }
  });
}

async function fetchOpenAIUsage() {
  if (!isOpenAIConnected) return;
  const spendData = await apiClient.get("/analytics/token/spend");
  const effData = await apiClient.get("/analytics/token/efficiency");
  
  if (spendData._error || effData._error) return;

  if (openaiTotalSpend)    openaiTotalSpend.textContent    = fmtUsd(spendData.summary?.total_spend_usd);
  if (openaiMonthlySpend)  openaiMonthlySpend.textContent  = fmtUsd(spendData.summary?.estimated_monthly_usd);
  
  const mostExpensive = spendData.drivers?.models?.[0]?.model || "--";
  if (openaiMostExpensive) openaiMostExpensive.textContent = fmt(mostExpensive);
  
  if (openaiEfficiency)    openaiEfficiency.textContent    = fmtPct(effData.efficiency_score);
}

// Ensure the interval clears correctly on hot reloads
window.addEventListener("beforeunload", () => {
  if (window._qorvexisOpenAIInterval) clearInterval(window._qorvexisOpenAIInterval);
});

// ─── Phase 8D: AWS Cloud Intelligence ───────────────────────────────────────

// ── DOM refs ─────────────────────────────────────────────────────────────────
const awsConnectForm          = document.getElementById("awsConnectForm");
const awsAccessKeyInput       = document.getElementById("awsAccessKeyInput");
const awsSecretKeyInput       = document.getElementById("awsSecretKeyInput");
const awsRegionInput          = document.getElementById("awsRegionInput");
const awsDemoModeToggle       = document.getElementById("awsDemoModeToggle");
const awsSubmitBtn            = document.getElementById("awsSubmitBtn");
const awsFormMessage          = document.getElementById("awsFormMessage");
const awsConnectorStatusBadge = document.getElementById("awsConnectorStatusBadge");
const awsAccountPanel         = document.getElementById("awsAccountPanel");
const awsRefreshBtn           = document.getElementById("awsRefreshBtn");
const awsLastSyncLabel        = document.getElementById("awsLastSyncLabel");
const awsSyncStatusBadge      = document.getElementById("awsSyncStatusBadge");

// Account metadata
const awsAccountId            = document.getElementById("awsAccountId");
const awsAccountAlias         = document.getElementById("awsAccountAlias");
const awsAccountRegion        = document.getElementById("awsAccountRegion");
const awsLastSync             = document.getElementById("awsLastSync");
const awsResourcesDiscovered  = document.getElementById("awsResourcesDiscovered");
const awsSuccessfulSyncs      = document.getElementById("awsSuccessfulSyncs");
const awsFailedSyncs          = document.getElementById("awsFailedSyncs");
const awsConnectorId          = document.getElementById("awsConnectorId");

// KPI cards
const awsMonthlySpend         = document.getElementById("awsMonthlySpend");
const awsDailySpend           = document.getElementById("awsDailySpend");
const awsActiveInstances      = document.getElementById("awsActiveInstances");
const awsTotalInstancesSub    = document.getElementById("awsTotalInstancesSub");
const awsUnderutilized        = document.getElementById("awsUnderutilized");
const awsHealthScore          = document.getElementById("awsHealthScore");
const awsHealthBar            = document.getElementById("awsHealthBar");
const awsOptimizationScore    = document.getElementById("awsOptimizationScore");
const awsOptimizationBar      = document.getElementById("awsOptimizationBar");
const awsWasteScore           = document.getElementById("awsWasteScore");
const awsEstimatedSavings     = document.getElementById("awsEstimatedSavings");

// Intelligence panels
const awsRecommendationsList  = document.getElementById("awsRecommendationsList");
const awsRecCount             = document.getElementById("awsRecCount");
const awsCostBreakdown        = document.getElementById("awsCostBreakdown");
const awsSpendTrend           = document.getElementById("awsSpendTrend");
const awsInstanceList         = document.getElementById("awsInstanceList");
const awsAnalyticsPanel       = document.getElementById("awsAnalyticsPanel");

let isAWSConnected = false;

// ── AWS Connect Form Handler ──────────────────────────────────────────────────

if (awsConnectForm) {
  awsConnectForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const accessKey     = awsAccessKeyInput  ? awsAccessKeyInput.value.trim()  : "";
    const secretKey     = awsSecretKeyInput  ? awsSecretKeyInput.value.trim()  : "";
    const region        = awsRegionInput     ? awsRegionInput.value             : "us-east-1";
    const simulationMode = awsDemoModeToggle ? awsDemoModeToggle.checked        : false;

    // If real mode, require both keys
    if (!simulationMode && (!accessKey || !secretKey)) {
      if (awsFormMessage) {
        awsFormMessage.textContent = "Please provide both Access Key ID and Secret Access Key, or enable Demo Mode.";
        awsFormMessage.className   = "form-message error";
      }
      return;
    }

    // In demo mode allow empty keys
    const payload = {
      access_key:      simulationMode ? "DEMO_ACCESS_KEY" : accessKey,
      secret_key:      simulationMode ? "DEMO_SECRET_KEY" : secretKey,
      region:          region,
      name:            simulationMode ? "AWS Demo Account" : "AWS Production",
      simulation_mode: simulationMode,
    };

    if (awsSubmitBtn) { awsSubmitBtn.disabled = true; awsSubmitBtn.textContent = "Connecting…"; }
    if (awsFormMessage) { awsFormMessage.textContent = ""; awsFormMessage.className = "form-message"; }
    if (awsConnectorStatusBadge) awsConnectorStatusBadge.textContent = "Connecting…";

    try {
      const res = await apiClient.post("/connectors/aws/connect", payload);
      if (res._error) throw new Error(res.reason || "Connection failed");

      // ── Success ───────────────────────────────────────────────────────────
      isAWSConnected = true;

      if (awsConnectorStatusBadge) {
        awsConnectorStatusBadge.textContent = simulationMode ? "Demo Mode" : "Connected";
        awsConnectorStatusBadge.className   = simulationMode ? "panel-badge health-warn" : "panel-badge health-ok";
      }
      if (awsFormMessage) {
        awsFormMessage.textContent = res.message || "AWS connector registered successfully.";
        awsFormMessage.className   = "form-message success";
      }

      // Show the account panel
      if (awsAccountPanel) awsAccountPanel.style.display = "block";
      if (awsConnectorId)  awsConnectorId.textContent    = res.connector_id || "--";
      if (awsAccountRegion) awsAccountRegion.textContent = res.region || "--";

      // Clear sensitive inputs
      if (awsAccessKeyInput) awsAccessKeyInput.value = "";
      if (awsSecretKeyInput) awsSecretKeyInput.value = "";

      // Initial data fetch + start polling
      await fetchAWSSummary();

      // Poll every 60 seconds to avoid excessive AWS API costs
      if (window._qorvexisAWSInterval) clearInterval(window._qorvexisAWSInterval);
      window._qorvexisAWSInterval = setInterval(fetchAWSSummary, 60000);

    } catch (err) {
      if (awsFormMessage) {
        awsFormMessage.textContent = err.message || "AWS connection failed.";
        awsFormMessage.className   = "form-message error";
      }
      if (awsConnectorStatusBadge) {
        awsConnectorStatusBadge.textContent = "Error";
        awsConnectorStatusBadge.className   = "panel-badge health-critical";
      }
    } finally {
      if (awsSubmitBtn) { awsSubmitBtn.disabled = false; awsSubmitBtn.textContent = "Connect AWS"; }
    }
  });
}

// Manual refresh button
if (awsRefreshBtn) {
  awsRefreshBtn.addEventListener("click", async () => {
    awsRefreshBtn.textContent = "Syncing…";
    awsRefreshBtn.disabled    = true;
    await fetchAWSSummary();
    awsRefreshBtn.textContent = "Sync now";
    awsRefreshBtn.disabled    = false;
  });
}

// ── Primary AWS Data Fetch (summary endpoint) ─────────────────────────────────

async function fetchAWSSummary() {
  const data = await apiClient.get("/connectors/aws/summary");
  if (data._error) {
    console.warn("[Qorvexis] AWS summary unavailable:", data.reason);
    return;
  }

  try {
    renderAWSSummary(data);
  } catch (err) {
    console.warn("[Qorvexis] AWS render error:", err);
  }
}

// ── Render: KPI Cards ─────────────────────────────────────────────────────────

function renderAWSSummary(data) {
  if (!data.available) {
    // Connector not connected — show disconnected state gracefully
    return;
  }

  // ── KPI Cards ─────────────────────────────────────────────────────────────
  if (awsMonthlySpend)  awsMonthlySpend.textContent  = fmtUsd(data.monthly_spend);
  if (awsDailySpend)    awsDailySpend.textContent    = fmtUsd(data.daily_spend);
  if (awsActiveInstances) awsActiveInstances.textContent = fmt(data.active_instances, "0");
  if (awsTotalInstancesSub) awsTotalInstancesSub.textContent = `${data.total_instances || 0} total`;
  if (awsUnderutilized) awsUnderutilized.textContent = fmt(data.underutilized_instances, "0");
  if (awsEstimatedSavings) awsEstimatedSavings.textContent = fmtUsd(data.estimated_savings);

  // Health score
  const health = data.infrastructure_health_score || 0;
  if (awsHealthScore) {
    awsHealthScore.textContent = `${health}/100`;
    awsHealthScore.className   = `kpi-mini-value ${health >= 75 ? "health-ok" : health >= 40 ? "health-warn" : "health-critical"}`;
  }
  if (awsHealthBar) {
    awsHealthBar.style.width = `${health}%`;
    awsHealthBar.className   = `progress-bar-fill ${health >= 75 ? "pressure-low" : health >= 40 ? "pressure-medium" : "pressure-high"}`;
  }

  // Optimization score
  const optScore = data.optimization_score || 0;
  if (awsOptimizationScore) awsOptimizationScore.textContent = `${optScore}/100`;
  if (awsOptimizationBar)   awsOptimizationBar.style.width   = `${optScore}%`;

  // Waste score
  if (awsWasteScore) {
    const ws = data.waste_score || 0;
    awsWasteScore.textContent = `${ws}%`;
    awsWasteScore.className   = `kpi-mini-value ${ws >= 50 ? "health-critical" : ws >= 25 ? "health-warn" : "health-ok"}`;
  }

  // ── Sync state ─────────────────────────────────────────────────────────────
  const syncState = data.sync_state || {};
  const syncStatus = data.connector_status || syncState.sync_status || "idle";

  if (awsSyncStatusBadge) {
    awsSyncStatusBadge.textContent = syncStatus;
    awsSyncStatusBadge.className   = `panel-badge ${
      syncStatus === "completed" ? "health-ok"
      : syncStatus === "degraded" || syncStatus === "failed" ? "health-critical"
      : syncStatus === "syncing" ? "health-warn"
      : ""
    }`;
  }

  const lastSyncIso = data.last_sync;
  if (awsLastSync)      awsLastSync.textContent      = lastSyncIso ? fmtTime(lastSyncIso) : "--";
  if (awsLastSyncLabel) awsLastSyncLabel.textContent = lastSyncIso ? `Last sync ${fmtTime(lastSyncIso)}` : "Awaiting sync";

  if (awsResourcesDiscovered) awsResourcesDiscovered.textContent = fmt(syncState.resources_discovered, "0");
  if (awsSuccessfulSyncs)     awsSuccessfulSyncs.textContent     = fmt(syncState.successful_sync_count, "0");
  if (awsFailedSyncs)         awsFailedSyncs.textContent         = fmt(syncState.failed_sync_count, "0");

  // ── Account metadata ────────────────────────────────────────────────────────
  const acct = data.account_metadata || {};
  if (awsAccountId)    awsAccountId.textContent    = fmt(acct.account_id, "--");
  if (awsAccountAlias) awsAccountAlias.textContent = fmt(acct.account_alias, "—");
  if (awsAccountRegion && !awsAccountRegion.textContent.match(/^[a-z]/)) {
    awsAccountRegion.textContent = fmt(acct.region, "--");
  }

  // ── Optimization recommendations (top 3 from summary) ─────────────────────
  const topRecs = data.top_recommendations || [];
  const totalRec = data.recommendation_count || 0;
  if (awsRecCount) awsRecCount.textContent = `${totalRec} recommendation${totalRec !== 1 ? "s" : ""}`;
  renderAWSRecommendations(topRecs, totalRec);

  // ── Analytics panel ─────────────────────────────────────────────────────────
  renderAWSAnalytics(data);

  // Show account panel if hidden
  if (awsAccountPanel && awsAccountPanel.style.display === "none") {
    awsAccountPanel.style.display = "block";
  }

  // Also fetch full recommendations + cost breakdown
  fetchAWSRecommendationsFull();
  fetchAWSCostBreakdown();
}

// ── Render: Optimization Recommendations ─────────────────────────────────────

function renderAWSRecommendations(recs, totalCount) {
  if (!awsRecommendationsList) return;

  if (!recs || !recs.length) {
    if (totalCount === 0) {
      awsRecommendationsList.innerHTML = `
        <div style="text-align:center;padding:24px;">
          <p style="color:var(--emerald);font-weight:600;margin-bottom:6px;">✓ No optimization issues detected</p>
          <p class="empty-state" style="font-style:normal;">Your AWS infrastructure appears efficient.</p>
        </div>
      `;
    } else {
      awsRecommendationsList.innerHTML = `<span class="empty-state">Loading recommendations…</span>`;
    }
    return;
  }

  awsRecommendationsList.innerHTML = recs.map(rec => {
    const severityColor = {
      critical: "var(--red, #ef4444)",
      high:     "var(--yellow, #eab308)",
      medium:   "var(--accent, #6366f1)",
      low:      "var(--emerald, #10b981)",
    }[rec.severity] || "var(--text-muted)";

    const savings = rec.estimated_monthly_savings_usd > 0
      ? `<div style="margin-top:8px;padding:6px 10px;background:rgba(16,185,129,0.1);border-radius:6px;font-size:.85rem;">
           <strong style="color:var(--emerald)">Est. savings: ${fmtUsd(rec.estimated_monthly_savings_usd)}/mo</strong>
           · ${(rec.affected_resources || []).length} resource${rec.affected_resources.length !== 1 ? "s" : ""} affected
         </div>` : "";

    return `
      <div style="border:1px solid var(--border);border-left:3px solid ${severityColor};border-radius:8px;padding:14px;margin-bottom:12px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <span style="font-size:.75rem;font-weight:600;color:${severityColor};text-transform:uppercase;letter-spacing:.05em;">${escapeHtml(rec.severity)}</span>
          <strong style="font-size:.95rem;">${escapeHtml(rec.title)}</strong>
        </div>
        <p style="font-size:.85rem;color:var(--text-muted);margin-bottom:4px;line-height:1.5;">${escapeHtml(rec.why)}</p>
        <p style="font-size:.82rem;color:var(--text-secondary);line-height:1.4;font-style:italic;">${escapeHtml(rec.impact)}</p>
        ${savings}
      </div>
    `;
  }).join("");
}

// ── Fetch full recommendations (separate call for detail) ─────────────────────

async function fetchAWSRecommendationsFull() {
  const data = await apiClient.get("/connectors/aws/recommendations");
  if (data._error || !data.available) return;

  const recs = data.recommendations || [];
  if (awsRecCount) awsRecCount.textContent = `${recs.length} recommendation${recs.length !== 1 ? "s" : ""}`;
  renderAWSRecommendations(recs, recs.length);
}

// ── Render: Cost Breakdown ────────────────────────────────────────────────────

async function fetchAWSCostBreakdown() {
  const data = await apiClient.get("/connectors/aws/costs");
  if (data._error || !data.available) return;

  renderAWSCostBreakdown(data);
}

function renderAWSCostBreakdown(data) {
  if (!awsCostBreakdown) return;

  const categoryBreakdown = data.category_breakdown || {};
  const spendTrend        = data.spend_trend        || {};
  const topServices       = data.top_services       || [];

  // Spend trend badge
  if (awsSpendTrend) {
    const dir = spendTrend.direction || "stable";
    awsSpendTrend.textContent = dir === "increasing"
      ? `↑ ${spendTrend.change_pct}% vs prior week`
      : dir === "decreasing"
        ? `↓ ${Math.abs(spendTrend.change_pct)}% vs prior week`
        : "Stable";
    awsSpendTrend.className = `panel-badge ${dir === "increasing" ? "health-critical" : dir === "decreasing" ? "health-ok" : ""}`;
  }

  const categoryRows = Object.entries(categoryBreakdown)
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([service, amount]) => `
      <div class="stat-row">
        <span class="stat-label" style="text-transform:capitalize;">${escapeHtml(service)}</span>
        <span class="stat-value">${fmtUsd(amount)}</span>
      </div>
    `).join("");

  const topServiceRows = topServices.slice(0, 5).map(s => `
    <div class="stat-row">
      <span class="stat-label" style="font-size:.8rem;">${escapeHtml(s.service)}</span>
      <span class="stat-value">${fmtUsd(s.amount)}</span>
    </div>
  `).join("");

  awsCostBreakdown.innerHTML = `
    <div style="font-size:.75rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Category</div>
    ${categoryRows || '<span class="empty-state">No category data.</span>'}
    <div style="font-size:.75rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:12px 0 8px;">Top Services</div>
    ${topServiceRows || '<span class="empty-state">No service data.</span>'}
  `;

  // Instance fleet
  fetchAWSInstanceFleet();
}

// ── Fetch + Render: EC2 Instance Fleet ───────────────────────────────────────

async function fetchAWSInstanceFleet() {
  const data = await apiClient.get("/connectors/aws/infrastructure");
  if (data._error || !data.available) return;

  renderAWSInstanceFleet(data.instances || []);
}

function renderAWSInstanceFleet(instances) {
  if (!awsInstanceList) return;

  if (!instances.length) {
    awsInstanceList.innerHTML = '<span class="empty-state">No instances discovered yet.</span>';
    return;
  }

  awsInstanceList.innerHTML = instances.map(inst => {
    const stateColor = {
      running:    "var(--emerald)",
      stopped:    "var(--text-muted)",
      terminated: "var(--red, #ef4444)",
    }[inst.state] || "var(--text-muted)";

    const cpuLabel = inst.state === "running"
      ? `CPU ${fmtPct(inst.cpu_utilization)}${inst.cpu_utilization < 10 ? " ⚠ underutilized" : ""}`
      : inst.state;

    return `
      <div class="data-row" style="border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:8px;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="width:8px;height:8px;border-radius:50%;background:${stateColor};display:inline-block;flex-shrink:0;"></span>
          <strong style="font-family:monospace;font-size:.85rem;">${escapeHtml(inst.instance_id)}</strong>
          <span style="font-size:.8rem;color:var(--text-muted);">${escapeHtml(inst.instance_type)}</span>
        </div>
        <span style="font-size:.8rem;color:${inst.cpu_utilization < 10 && inst.state === "running" ? "var(--yellow, #eab308)" : "var(--text-muted)"};">${cpuLabel}</span>
      </div>
    `;
  }).join("");
}

// ── Render: Cloud Infrastructure Analytics ───────────────────────────────────

function renderAWSAnalytics(data) {
  if (!awsAnalyticsPanel) return;

  const active  = data.active_instances || 0;
  const total   = data.total_instances  || 0;
  const under   = data.underutilized_instances || 0;
  const health  = data.infrastructure_health_score || 0;
  const optScore = data.optimization_score || 0;
  const savings = data.estimated_savings || 0;
  const monthly = data.monthly_spend || 0;

  const utilizationRate = active > 0 ? Math.round((active / Math.max(total, 1)) * 100) : 0;
  const wasteRate = under > 0 && active > 0 ? Math.round((under / active) * 100) : 0;

  awsAnalyticsPanel.innerHTML = `
    <div class="stat-row"><span class="stat-label">Fleet Utilization Rate</span><span class="stat-value">${utilizationRate}% running</span></div>
    <div class="stat-row"><span class="stat-label">Waste Rate (underutil.)</span><span class="stat-value ${wasteRate > 40 ? "health-critical" : wasteRate > 20 ? "health-warn" : "health-ok"}">${wasteRate}% of fleet</span></div>
    <div class="stat-row"><span class="stat-label">Infrastructure Health</span><span class="stat-value ${health >= 75 ? "health-ok" : health >= 40 ? "health-warn" : "health-critical"}">${health}/100</span></div>
    <div class="stat-row"><span class="stat-label">Optimization Score</span><span class="stat-value">${optScore}/100</span></div>
    <div class="stat-row"><span class="stat-label">Monthly AWS Spend</span><span class="stat-value">${fmtUsd(monthly)}</span></div>
    <div class="stat-row"><span class="stat-label">Potential Savings/Mo</span><span class="stat-value accent-emerald">${fmtUsd(savings)}</span></div>
    <div class="stat-row"><span class="stat-label">Savings as % of Spend</span><span class="stat-value">${monthly > 0 ? Math.round((savings / monthly) * 100) : 0}%</span></div>
  `;
}

// ── Interval management ───────────────────────────────────────────────────────

window.addEventListener("beforeunload", () => {
  if (window._qorvexisAWSInterval) clearInterval(window._qorvexisAWSInterval);
});

// Auto-poll AWS summary if already connected on load (e.g. page refresh)
(async () => {
  const health = await apiClient.get("/connectors/aws/health");
  if (!health._error && health.available) {
    isAWSConnected = true;
    if (awsConnectorStatusBadge) {
      awsConnectorStatusBadge.textContent = "Connected";
      awsConnectorStatusBadge.className   = "panel-badge health-ok";
    }
    if (awsAccountPanel) awsAccountPanel.style.display = "block";
    await fetchAWSSummary();
    if (window._qorvexisAWSInterval) clearInterval(window._qorvexisAWSInterval);
    window._qorvexisAWSInterval = setInterval(fetchAWSSummary, 60000);
  }
})();

// ── Phase 9: Providers Dashboard Logic ────────────────────────────────────────

const providersRefreshBtn = document.getElementById("providersRefreshBtn");
const providerTotalSpend = document.getElementById("providerTotalSpend");
const providerActiveCount = document.getElementById("providerActiveCount");
const providerTopName = document.getElementById("providerTopName");
const providerOptScore = document.getElementById("providerOptScore");

const providerComparisonTable = document.getElementById("providerComparisonTable");
const providerRecommendationsList = document.getElementById("providerRecommendationsList");
const providerWorkloadsList = document.getElementById("providerWorkloadsList");
const providerRecCount = document.getElementById("providerRecCount");

if (providersRefreshBtn) {
  providersRefreshBtn.addEventListener("click", async () => {
    providersRefreshBtn.classList.add("loading");
    providersRefreshBtn.textContent = "Syncing...";
    try {
      await apiClient.post("/providers/sync", {});
    } catch (e) {
      console.warn("Manual sync failed", e);
    }
    
    await fetchProviderIntelligence().finally(() => {
      providersRefreshBtn.classList.remove("loading");
      providersRefreshBtn.textContent = "Sync now";
    });
  });
}

async function fetchProviderIntelligence() {
  const [summary, comp, recs, workloads, vis] = await Promise.all([
    apiClient.get("/providers/summary"),
    apiClient.get("/providers/comparison"),
    apiClient.get("/providers/recommendations"),
    apiClient.get("/providers/workloads"),
    apiClient.get("/providers/visibility")
  ]);

  if (!summary._error) renderProviderSummary(summary);
  if (!comp._error) renderProviderComparison(comp);
  if (!recs._error) renderProviderRecommendations(recs);
  if (!workloads._error) renderProviderWorkloads(workloads);
  if (!vis._error) renderProviderVisibility(vis);
}

function renderProviderSummary(summary) {
  if (providerTotalSpend) providerTotalSpend.textContent = fmtUsd(summary.total_ai_spend || 0);
  if (providerActiveCount) providerActiveCount.textContent = summary.active_providers || 0;
  if (providerTopName) providerTopName.textContent = summary.top_provider || "None";
  if (providerOptScore) providerOptScore.textContent = `${summary.optimization_score || 0}/100`;
}

function renderProviderComparison(comp) {
  if (!providerComparisonTable) return;
  if (!comp || comp.length === 0) {
    providerComparisonTable.innerHTML = `<tr><td colspan="6" class="empty-state">No provider data available.</td></tr>`;
    return;
  }
  
  providerComparisonTable.innerHTML = comp.map(p => `
    <tr style="border-bottom:1px solid var(--border);">
      <td style="padding:1rem .5rem;text-transform:capitalize;font-weight:600;">${escapeHtml(p.provider)}</td>
      <td style="padding:1rem .5rem;">${fmtUsd(p.spend)}</td>
      <td style="padding:1rem .5rem;">${p.requests}</td>
      <td style="padding:1rem .5rem;">${p.latency_ms.toFixed(0)} ms</td>
      <td style="padding:1rem .5rem;">${fmtUsd(p.cost_per_1k)}</td>
      <td style="padding:1rem .5rem;color:${p.reliability_score > 90 ? 'var(--emerald)' : 'var(--text-muted)'}">${p.reliability_score.toFixed(0)}/100</td>
    </tr>
  `).join("");
}

function renderProviderVisibility(vis) {
  const table = document.getElementById("providerVisibilityTable");
  const statusBadge = document.getElementById("visibilitySyncStatus");
  if (!table) return;

  if (statusBadge && vis.sync_status) {
    statusBadge.textContent = `Sync: ${vis.sync_status.sync_status} (${vis.sync_status.sync_errors} errors)`;
    statusBadge.className = `panel-badge ${vis.sync_status.sync_errors > 0 ? 'health-warn' : (vis.sync_status.sync_status === 'running' ? 'health-ok' : '')}`;
  }

  if (!vis.providers || vis.providers.length === 0) {
    table.innerHTML = `<tr><td colspan="7" class="empty-state">No telemetry visibility data available.</td></tr>`;
    return;
  }

  table.innerHTML = vis.providers.map(p => {
    let lastSyncStr = "Never";
    if (p.last_sync) {
        const d = new Date(p.last_sync);
        lastSyncStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' ' + d.toLocaleDateString();
    }
    return `
    <tr style="border-bottom:1px solid var(--border);">
      <td style="padding:1rem .5rem;font-weight:600;">${escapeHtml(p.provider)}</td>
      <td style="padding:1rem .5rem;color:${p.visibility_pct === 100 ? 'var(--emerald)' : 'var(--accent)'}">${p.visibility_pct}%</td>
      <td style="padding:1rem .5rem;">${escapeHtml(p.source)}</td>
      <td style="padding:1rem .5rem;font-size:.85em;color:var(--text-muted);">${escapeHtml(p.confidence)}</td>
      <td style="padding:1rem .5rem;font-size:.85em;color:var(--text-primary);">${p.records || 0}</td>
      <td style="padding:1rem .5rem;font-size:.85em;color:var(--text-muted);">${lastSyncStr}</td>
      <td style="padding:1rem .5rem;font-size:.85em;color:var(--text-muted);max-width:250px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${p.limitation || 'None'}">${p.limitation ? escapeHtml(p.limitation) : '<span style="opacity:0.5">None</span>'}</td>
    </tr>
  `}).join("");
}

function renderProviderRecommendations(recs) {
  if (!providerRecommendationsList) return;
  if (providerRecCount) providerRecCount.textContent = `${recs.length} recommendation${recs.length !== 1 ? 's' : ''}`;
  
  if (!recs || recs.length === 0) {
    providerRecommendationsList.innerHTML = `<span class="empty-state">No optimization opportunities detected.</span>`;
    return;
  }

  providerRecommendationsList.innerHTML = recs.map(r => `
    <div class="data-row" style="border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
        <strong style="color:var(--text-primary);font-size:.9rem;">${escapeHtml(r.workload)}</strong>
        <span class="panel-badge ${r.type === 'provider_migration' ? 'health-warn' : 'health-ok'}">${r.type.replace('_', ' ')}</span>
      </div>
      <div style="font-size:.8rem;color:var(--text-muted);margin-bottom:8px;">
        ${escapeHtml(r.rule)}
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.8rem;">
        <span style="color:var(--text-primary);">â†’ ${escapeHtml(r.recommendation)}</span>
        <strong style="color:var(--emerald);">Save ${fmtUsd(r.estimated_savings)}</strong>
      </div>
    </div>
  `).join("");
}

function renderProviderWorkloads(workloads) {
  if (!providerWorkloadsList) return;
  if (!workloads || workloads.length === 0) {
    providerWorkloadsList.innerHTML = `<span class="empty-state">No workload data available.</span>`;
    return;
  }

  providerWorkloadsList.innerHTML = workloads.map(w => `
    <div class="data-row" style="border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <strong style="font-size:.85rem;">${escapeHtml(w.category)}</strong>
        <span style="font-size:.85rem;color:var(--text-primary);">${fmtUsd(w.spend)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.8rem;color:var(--text-muted);">
        <span>${escapeHtml(w.provider)} &middot; ${escapeHtml(w.model)}</span>
        <span>${w.requests} reqs &middot; ${w.avg_latency.toFixed(0)} ms</span>
      </div>
    </div>
  `).join("");
}

// Initial fetch
fetchProviderIntelligence();

// ══════════════════════════════════════════════════════════════════════════════
// Phase 10: Business Intelligence Dashboard
// ══════════════════════════════════════════════════════════════════════════════

const bizRefreshBtn       = document.getElementById("bizRefreshBtn");
const bizTotalSpend       = document.getElementById("bizTotalSpend");
const bizGatewayRequests  = document.getElementById("bizGatewayRequests");
const bizTopCostDriver    = document.getElementById("bizTopCostDriver");
const bizSavingsOpp       = document.getElementById("bizSavingsOpp");
const bizForecastConfidence = document.getElementById("bizForecastConfidence");
const bizAvgDaily         = document.getElementById("bizAvgDaily");
const bizForecast7d       = document.getElementById("bizForecast7d");
const bizForecast30d      = document.getElementById("bizForecast30d");
const bizForecast90d      = document.getElementById("bizForecast90d");
const bizTrendDir         = document.getElementById("bizTrendDir");
const bizDataPoints       = document.getElementById("bizDataPoints");
const bizWorkloadList     = document.getElementById("bizWorkloadList");
const bizWorkloadCount    = document.getElementById("bizWorkloadCount");
const bizRecList          = document.getElementById("bizRecList");
const bizRecCount         = document.getElementById("bizRecCount");
const bizTeamList         = document.getElementById("bizTeamList");
const bizTeamCount        = document.getElementById("bizTeamCount");
const bizCustomerList     = document.getElementById("bizCustomerList");
const bizCustomerCount    = document.getElementById("bizCustomerCount");

if (bizRefreshBtn) {
  bizRefreshBtn.addEventListener("click", async () => {
    bizRefreshBtn.classList.add("loading");
    bizRefreshBtn.textContent = "Syncing...";
    try {
      await apiClient.post("/providers/sync", {});
    } catch (e) {
      console.warn("Manual BI sync failed", e);
    }
    
    await fetchBusinessIntelligence().finally(() => {
      bizRefreshBtn.classList.remove("loading");
      bizRefreshBtn.textContent = "Sync now";
    });
  });
}

async function fetchBusinessIntelligence() {
  const [summary, workloads, teams, customers, forecast, recs] = await Promise.all([
    apiClient.get("/business/summary"),
    apiClient.get("/business/workloads"),
    apiClient.get("/business/teams"),
    apiClient.get("/business/customers"),
    apiClient.get("/business/forecast"),
    apiClient.get("/business/recommendations"),
  ]);

  if (!summary._error) renderBizSummary(summary);
  if (!forecast._error) renderBizForecast(forecast);
  if (!workloads._error && Array.isArray(workloads)) renderBizWorkloads(workloads);
  if (!recs._error && Array.isArray(recs)) renderBizRecommendations(recs);
  if (!teams._error && Array.isArray(teams)) renderBizTeams(teams);
  if (!customers._error && Array.isArray(customers)) renderBizCustomers(customers);
}

function renderBizSummary(s) {
  const bizGatewaySpend = document.getElementById("bizGatewaySpend");
  const bizProviderSpend = document.getElementById("bizProviderSpend");
  const bizObservedSpend = document.getElementById("bizObservedSpend");
  
  if (bizTotalSpend)    bizTotalSpend.textContent    = fmtUsd(s.total_ai_spend || 0);
  if (bizGatewayRequests) bizGatewayRequests.textContent = (s.gateway_requests || 0).toLocaleString() + " requests";
  if (bizGatewaySpend) bizGatewaySpend.textContent = fmtUsd(s.gateway_spend || 0);
  if (bizProviderSpend) bizProviderSpend.textContent = fmtUsd(s.provider_spend || 0);
  if (bizObservedSpend) bizObservedSpend.textContent = fmtUsd(s.observed_spend || 0);
  
  if (bizTopCostDriver) bizTopCostDriver.textContent = s.top_cost_driver || "None";
  if (bizSavingsOpp)    bizSavingsOpp.textContent    = fmtUsd(s.optimization_opportunity || 0);
}

function renderBizForecast(f) {
  if (bizForecastConfidence) bizForecastConfidence.textContent = `Confidence: ${f.confidence || "low"}`;
  if (bizAvgDaily)    bizAvgDaily.textContent    = fmtUsd(f.avg_daily_spend || 0);
  if (bizForecast7d)  bizForecast7d.textContent  = fmtUsd(f.forecast_7d || 0);
  if (bizForecast30d) bizForecast30d.textContent = fmtUsd(f.forecast_30d || 0);
  if (bizForecast90d) bizForecast90d.textContent = fmtUsd(f.forecast_90d || 0);

  const dir = f.trend_direction || "stable";
  if (bizTrendDir) {
    bizTrendDir.textContent = dir.charAt(0).toUpperCase() + dir.slice(1);
    bizTrendDir.style.color = dir === "increasing" ? "var(--red, #ef4444)" : dir === "decreasing" ? "var(--emerald)" : "var(--text-muted)";
  }
  if (bizDataPoints) bizDataPoints.textContent = f.data_points || 0;
}

function renderBizWorkloads(workloads) {
  if (!bizWorkloadList) return;
  if (bizWorkloadCount) bizWorkloadCount.textContent = `${workloads.length} workload${workloads.length !== 1 ? "s" : ""}`;

  if (!workloads.length) {
    bizWorkloadList.innerHTML = `<span class="empty-state">Route requests through <code>POST /gateway/chat</code> with <code>workload_id</code> to unlock attribution.</span>`;
    return;
  }

  // Sort by cost descending
  const sorted = [...workloads].sort((a, b) => (b.monthly_cost || 0) - (a.monthly_cost || 0));
  bizWorkloadList.innerHTML = sorted.map(w => `
    <div class="data-row" style="border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <strong style="font-size:.9rem;">${escapeHtml(w.workload_name || w.workload_id)}</strong>
        <span style="color:var(--accent);font-weight:700;">${fmtUsd(w.monthly_cost)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.8rem;color:var(--text-muted);">
        <span>${escapeHtml(w.provider)} &middot; ${escapeHtml(w.model)}</span>
        <span>${(w.request_count || 0).toLocaleString()} reqs &middot; ${(w.avg_latency || 0).toFixed(0)} ms</span>
      </div>
    </div>
  `).join("");
}

function renderBizRecommendations(recs) {
  if (!bizRecList) return;
  if (bizRecCount) bizRecCount.textContent = `${recs.length} recommendation${recs.length !== 1 ? "s" : ""}`;

  if (!recs.length) {
    bizRecList.innerHTML = `<span class="empty-state">No recommendations yet — more data needed.</span>`;
    return;
  }

  const priorityColor = { high: "var(--red, #ef4444)", medium: "var(--yellow, #eab308)", low: "var(--text-muted)" };
  bizRecList.innerHTML = recs.map(r => `
    <div class="data-row" style="border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
        <strong style="font-size:.875rem;">${escapeHtml(r.workload)}</strong>
        <span style="font-size:.75rem;padding:2px 8px;border-radius:4px;background:rgba(255,255,255,0.06);color:${priorityColor[r.priority] || "var(--text-muted)"};">${r.priority || "medium"}</span>
      </div>
      <div style="font-size:.8rem;color:var(--text-muted);margin-bottom:6px;">${escapeHtml(r.rule)}</div>
      <div style="display:flex;justify-content:space-between;font-size:.8rem;">
        <span style="color:var(--text-primary);">→ ${escapeHtml(r.recommendation)}</span>
        <strong style="color:var(--emerald);">Save ${fmtUsd(r.estimated_savings)}/mo</strong>
      </div>
    </div>
  `).join("");
}

function renderBizTeams(teams) {
  if (!bizTeamList) return;
  if (bizTeamCount) bizTeamCount.textContent = `${teams.length} team${teams.length !== 1 ? "s" : ""}`;

  if (!teams.length) {
    bizTeamList.innerHTML = `<span class="empty-state">Tag gateway requests with <code>team_id</code> to unlock team attribution.</span>`;
    return;
  }

  bizTeamList.innerHTML = teams.map(t => `
    <div class="data-row" style="border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <strong>${escapeHtml(t.team_name)}</strong>
        <span style="font-weight:700;">${fmtUsd(t.monthly_cost)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.8rem;color:var(--text-muted);">
        <span>${(t.request_count || 0).toLocaleString()} requests</span>
        <span style="color:var(--emerald);">Save ${fmtUsd(t.savings_opportunity)}</span>
      </div>
    </div>
  `).join("");
}

function renderBizCustomers(customers) {
  if (!bizCustomerList) return;
  if (bizCustomerCount) bizCustomerCount.textContent = `${customers.length} customer${customers.length !== 1 ? "s" : ""}`;

  if (!customers.length) {
    bizCustomerList.innerHTML = `<span class="empty-state">Tag gateway requests with <code>customer_id</code> to track per-customer AI costs.</span>`;
    return;
  }

  bizCustomerList.innerHTML = customers.map(c => `
    <div class="data-row" style="border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <strong>${escapeHtml(c.customer_name)}</strong>
        <span style="font-weight:700;">${fmtUsd(c.monthly_cost)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.8rem;color:var(--text-muted);">
        <span>${(c.requests || 0).toLocaleString()} requests</span>
        <span>${(c.tokens || 0).toLocaleString()} tokens</span>
      </div>
    </div>
  `).join("");
}

// Auto-fetch on page load
fetchBusinessIntelligence();


