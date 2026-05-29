import os
import requests
from typing import Optional, Dict, Any, List

class QorvexisClient:
    """
    Drop-in Python SDK for routing AI requests through the Qorvexis AI Gateway.
    Provides native telemetry tracking, optimization, and fallback support.
    """
    
    def __init__(self, api_key: Optional[str] = None, gateway_url: str = "http://localhost:8000/gateway"):
        # The Qorvexis Gateway handles its own keys, or you can pass standard provider keys directly.
        self.api_key = api_key or os.getenv("QORVEXIS_API_KEY", "")
        self.gateway_url = gateway_url

    def chat(self, 
             provider: str, 
             model: str, 
             messages: List[Dict[str, str]], 
             team_id: Optional[str] = None,
             customer_id: Optional[str] = None,
             workload_id: Optional[str] = None,
             fallback_provider: Optional[str] = None,
             **kwargs) -> Dict[str, Any]:
        """
        Executes a chat completion via the Qorvexis Gateway.
        """
        payload = {
            "provider": provider,
            "model": model,
            "messages": messages,
            "api_key": self.api_key,
            "team_id": team_id,
            "customer_id": customer_id,
            "workload_id": workload_id,
            "fallback_provider": fallback_provider,
            **kwargs
        }
        
        response = requests.post(f"{self.gateway_url}/chat", json=payload)
        response.raise_for_status()
        return response.json()
