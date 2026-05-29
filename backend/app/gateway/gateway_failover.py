import logging
from app.gateway.gateway_schemas import GatewayChatRequest, GatewayChatResponse
from app.gateway.gateway_provider_registry import gateway_provider_registry

logger = logging.getLogger("qorvexis.gateway.failover")

class GatewayFailoverManager:
    """Handles routing, fallbacks, and resilient execution."""

    def execute_with_failover(self, req: GatewayChatRequest, execute_fn) -> GatewayChatResponse:
        """
        Executes a gateway request, catching provider errors and automatically routing
        to the fallback provider if specified.
        
        execute_fn must take (provider_name, model, api_key) and return a GatewayChatResponse
        """
        # We assume the caller passed the credentials in req.api_key, 
        # or we fetch them from the credential manager if they are missing.
        from app.gateway.provider_credentials.credential_manager import credential_manager
        from app.database.session import SessionLocal
        
        primary_provider = req.provider
        primary_model = req.model
        primary_key = req.api_key
        
        if not primary_key:
            with SessionLocal() as db:
                primary_key = credential_manager.get_active_credential(db, primary_provider)
                if not primary_key:
                    return self._build_error_response(primary_provider, primary_model, "No API key provided or found in credential manager")

        # Attempt Primary
        response = execute_fn(primary_provider, primary_model, primary_key)
        
        if response.success:
            return response
            
        # Primary failed, check failover
        if req.fallback_provider:
            logger.warning("gateway.failover.triggered from=%s to=%s error=%s", primary_provider, req.fallback_provider, response.error)
            fallback_provider = req.fallback_provider
            fallback_model = req.fallback_model or primary_model
            
            with SessionLocal() as db:
                fallback_key = credential_manager.get_active_credential(db, fallback_provider)
                if not fallback_key:
                    logger.error("gateway.failover.aborted reason='No credential found for fallback' provider=%s", fallback_provider)
                    return response # return the original failure

            fallback_response = execute_fn(fallback_provider, fallback_model, fallback_key)
            fallback_response.fallback_used = True
            return fallback_response
            
        # No failover specified, return the original failure
        return response

    def _build_error_response(self, provider: str, model: str, error: str) -> GatewayChatResponse:
        return GatewayChatResponse(
            request_id="error",
            provider=provider,
            model=model,
            content="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            estimated_cost=0.0,
            latency_ms=0.0,
            success=False,
            error=error
        )

gateway_failover_manager = GatewayFailoverManager()
