"""Token Anomaly Detection Engine.

Detects lightweight deterministic anomalies like sudden spend spikes, 
abnormal completion inflation, and runaway workloads.
"""

from typing import List, Dict, Any

# Static thresholds
MAX_PROMPT_TOKENS = 32000
MAX_COMPLETION_TOKENS = 4000
MAX_INFLATION_RATIO = 5.0  # e.g., if completion is 5x prompt
COST_SPIKE_THRESHOLD = 2.0  # USD per request

def detect_anomalies(
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost: float,
    model: str,
    provider: str
) -> List[Dict[str, Any]]:
    """Evaluate a single request for anomalies based on static thresholds."""
    
    anomalies = []
    
    if prompt_tokens > MAX_PROMPT_TOKENS:
        anomalies.append({
            "type": "unusually_large_prompt",
            "severity": "warning",
            "detail": f"Prompt tokens ({prompt_tokens}) exceeded expected maximum."
        })
        
    if completion_tokens > MAX_COMPLETION_TOKENS:
        anomalies.append({
            "type": "runaway_completion",
            "severity": "critical",
            "detail": f"Completion tokens ({completion_tokens}) exceeded safe threshold. Possible runaway generation."
        })
        
    if estimated_cost > COST_SPIKE_THRESHOLD:
        anomalies.append({
            "type": "spend_spike",
            "severity": "critical",
            "detail": f"Single request cost (${estimated_cost:.4f}) is abnormally high."
        })
        
    if prompt_tokens > 0:
        inflation_ratio = completion_tokens / prompt_tokens
        if inflation_ratio > MAX_INFLATION_RATIO and completion_tokens > 100:
            anomalies.append({
                "type": "abnormal_inflation",
                "severity": "warning",
                "detail": f"Completion inflation ratio ({inflation_ratio:.1f}x) exceeded efficient threshold."
            })
            
    return anomalies
