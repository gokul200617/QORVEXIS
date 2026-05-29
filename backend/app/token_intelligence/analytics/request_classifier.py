"""Request Classification Engine.

Deterministically categorizes AI workloads based on heuristics without using ML models.
"""

def classify_request(prompt: str, prompt_tokens: int, completion_tokens: int, model: str) -> str:
    """Categorize a workload deterministically based on text patterns and token counts."""
    
    prompt_lower = prompt.lower()
    
    # 1. Embeddings
    if "embed" in model.lower():
        return "embeddings"
        
    # 2. Coding
    if any(kw in prompt_lower for kw in ["def ", "class ", "function", "code", "python", "javascript", "react", "html"]):
        if prompt_tokens > 50 or completion_tokens > 50:
            return "coding"
            
    # 3. Summarization
    if any(kw in prompt_lower for kw in ["summarize", "tldr", "tl;dr", "summary", "brief"]):
        # Summarization typically has high prompt tokens, low completion tokens
        if prompt_tokens > completion_tokens and prompt_tokens > 100:
            return "summarization"
            
    # 4. Translation
    if "translate" in prompt_lower or "translation" in prompt_lower:
        return "translation"
        
    # 5. Classification
    if any(kw in prompt_lower for kw in ["classify", "categorize", "sentiment", "extract"]):
        # Classification usually has very small output
        if completion_tokens > 0 and completion_tokens < 20:
            return "classification"
            
    # 6. Support
    if any(kw in prompt_lower for kw in ["help", "support", "ticket", "customer", "issue", "error"]):
        return "support"
        
    # 7. Generation
    if any(kw in prompt_lower for kw in ["generate", "write", "create", "draft", "story"]):
        if completion_tokens > prompt_tokens:
            return "generation"
            
    # 8. Chat
    if prompt_tokens < 100 and completion_tokens < 100:
        return "chat"
        
    return "unknown"
