"""
Token counting utilities for markdown chunking.

Uses tiktoken for accurate token counting, with fallback to approximation.
"""

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Count tokens in text using tiktoken.
    
    Args:
        text: Text to count tokens for
        model: Model name for tokenizer (default: gpt-3.5-turbo)
    
    Returns:
        Number of tokens
    """
    if not TIKTOKEN_AVAILABLE:
        return estimate_tokens(text)
    
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # Fallback to estimation if tiktoken fails
        return estimate_tokens(text)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count using simple approximation.
    
    Approximation: ~4 characters per token (conservative estimate)
    
    Args:
        text: Text to estimate tokens for
    
    Returns:
        Estimated number of tokens
    """
    # Conservative estimate: ~4 chars per token
    # This works reasonably well for English and Vietnamese
    return len(text) // 4


def get_token_count(text: str) -> int:
    """
    Get token count for text, using best available method.
    
    Args:
        text: Text to count tokens for
    
    Returns:
        Number of tokens
    """
    return count_tokens(text)

