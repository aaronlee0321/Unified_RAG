"""
Simple LLM provider wrapper for keyword extractor.
Supports OpenAI-compatible APIs (Qwen/DashScope, OpenAI).
"""
import os
from typing import Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None


class SimpleLLMProvider:
    """Simple LLM provider using OpenAI-compatible API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize LLM provider.
        
        Args:
            api_key: API key (defaults to QWEN_API_KEY, DASHSCOPE_API_KEY, or OPENAI_API_KEY env var)
            base_url: API base URL (defaults to DashScope URL if Qwen key detected)
            model: Model name (defaults to qwen-plus)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package is required. Install with: pip install openai")
        
        # Get API key from env or parameter
        self.api_key = api_key or os.getenv('QWEN_API_KEY') or os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError(
                "API key required. Set QWEN_API_KEY, DASHSCOPE_API_KEY, or OPENAI_API_KEY environment variable"
            )
        
        # Determine base URL
        if base_url:
            self.base_url = base_url
        elif os.getenv('QWEN_API_KEY') or os.getenv('DASHSCOPE_API_KEY'):
            # DashScope international endpoint
            self.base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        else:
            # Default OpenAI endpoint
            self.base_url = None
        
        # Model selection
        self.model = model or os.getenv('LLM_MODEL', 'qwen-plus')
        
        # Initialize client
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
    
    def llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate text using LLM.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (default: 0.3)
            max_tokens: Maximum tokens to generate
        
        Returns:
            Generated text response
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"LLM API error: {str(e)}") from e



