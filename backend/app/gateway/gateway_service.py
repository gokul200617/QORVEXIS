import logging
import time
import uuid

from app.gateway.gateway_schemas import GatewayChatRequest, GatewayChatResponse
from app.gateway.gateway_provider_registry import gateway_provider_registry
from app.gateway.gateway_failover import gateway_failover_manager
from app.gateway.gateway_cost_engine import gateway_cost_engine
from app.gateway.gateway_telemetry import GatewayTelemetryEvent, gateway_telemetry

logger = logging.getLogger("qorvexis.gateway.service")

class GatewayService:
    """Proxy and observe AI requests using resilient providers."""

    def execute(self, req: GatewayChatRequest, org_id: str | None = None) -> GatewayChatResponse:
        request_id = str(uuid.uuid4())
        
        # 1. Define the execution closure that failover will call
        def _execute_provider(provider_name: str, model: str, api_key: str) -> GatewayChatResponse:
            provider = gateway_provider_registry.get(provider_name)
            if not provider:
                return GatewayChatResponse(
                    request_id=request_id,
                    provider=provider_name,
                    model=model,
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    estimated_cost=0.0,
                    latency_ms=0.0,
                    success=False,
                    error=f"Provider '{provider_name}' not registered."
                )

            t_start = time.monotonic()
            try:
                content, prompt_tokens, completion_tokens = provider.generate(
                    api_key=api_key,
                    model=model,
                    messages=req.messages,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens
                )
                latency_ms = (time.monotonic() - t_start) * 1000
                
                # Heuristic estimation if provider drops token usage (e.g. some streaming endpoints)
                if prompt_tokens == 0 and completion_tokens == 0:
                    # Simple heuristic: ~4 chars per token
                    prompt_len = sum(len(m.get("content", "")) for m in req.messages)
                    prompt_tokens = prompt_len // 4
                    completion_tokens = len(content) // 4
                
                total_tokens = prompt_tokens + completion_tokens
                cost = gateway_cost_engine.estimate(provider_name, model, prompt_tokens, completion_tokens)
                
                return GatewayChatResponse(
                    request_id=request_id,
                    provider=provider_name,
                    model=model,
                    content=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=cost,
                    latency_ms=latency_ms,
                    success=True
                )
            except Exception as exc:
                latency_ms = (time.monotonic() - t_start) * 1000
                logger.warning("gateway.execute.error provider=%s model=%s error=%s", provider_name, model, exc)
                return GatewayChatResponse(
                    request_id=request_id,
                    provider=provider_name,
                    model=model,
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    estimated_cost=0.0,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc)
                )

        # 2. Execute with failover
        response = gateway_failover_manager.execute_with_failover(req, _execute_provider)
        
        # 3. Fire-and-forget Telemetry
        gateway_telemetry.record(GatewayTelemetryEvent(
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            estimated_cost=response.estimated_cost,
            latency_ms=response.latency_ms,
            success=response.success,
            workload_id=req.workload_id,
            workload_name=req.workload_name,
            team_id=req.team_id,
            team_name=req.team_name,
            customer_id=req.customer_id,
            customer_name=req.customer_name,
            application_id=req.application_id,
            session_id=req.session_id,
            request_id=request_id,
        ))

        return response

gateway_service = GatewayService()
