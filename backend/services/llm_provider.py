"""
Simple LLM provider wrapper for keyword extractor.
Uses OpenAI-compatible APIs.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None


class SimpleLLMProvider:
    """Simple LLM provider used by Keyword Finder / Deep Search."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize LLM provider.

        Args:
            api_key: Optional API key (read from env if not provided)
            base_url: OpenAI-compatible API base URL
            model: Model name (OpenAI-compatible model)
        """
        import logging
        logger = logging.getLogger(__name__)

        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package is required. Install with: pip install openai")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv(
            "QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No OpenAI-compatible API key found. "
                "Set OPENAI_API_KEY, QWEN_API_KEY, or DASHSCOPE_API_KEY."
            )

        # Determine base URL (OpenAI-compatible)
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = os.getenv(
                "OPENAI_BASE_URL") or "https://api.openai.com/v1"

        self.model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        logger.info(
            f"[LLM Provider] Using OpenAI-compatible endpoint: {self.base_url} model={self.model}")
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
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"LLM API error: {str(e)}") from e
