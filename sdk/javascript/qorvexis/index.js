/**
 * Drop-in JavaScript SDK for routing AI requests through the Qorvexis AI Gateway.
 * Provides native telemetry tracking, optimization, and fallback support.
 */
class QorvexisClient {
  constructor(options = {}) {
    this.apiKey = options.apiKey || process.env.QORVEXIS_API_KEY || "";
    this.gatewayUrl = options.gatewayUrl || "http://localhost:8000/gateway";
  }

  async chat(options) {
    const {
      provider,
      model,
      messages,
      team_id,
      customer_id,
      workload_id,
      fallback_provider,
      ...rest
    } = options;

    const payload = {
      provider,
      model,
      messages,
      api_key: this.apiKey,
      team_id,
      customer_id,
      workload_id,
      fallback_provider,
      ...rest,
    };

    const response = await fetch(`${this.gatewayUrl}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Qorvexis Gateway Error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }
}

module.exports = { QorvexisClient };
