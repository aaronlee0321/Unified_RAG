"""
Simple LLM provider wrapper for keyword extractor.
Defaults to OpenAI. Falls back to Gemini if OpenAI isn't configured.
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

try:
    from gdd_rag_backbone.llm_providers import GeminiProvider
    GEMINI_AVAILABLE = True
except Exception:
    GeminiProvider = None  # type: ignore
    GEMINI_AVAILABLE = False


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
        
        Priority: OpenAI > Gemini
        
        Args:
            api_key: Optional API key
            base_url: OpenAI-compatible API base URL
            model: Model name
        """
        # Priority 1: OpenAI (if configured)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and OPENAI_AVAILABLE:
            self._mode = "openai"
            self.api_key = openai_key
            self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            self.model = model or os.getenv("DEFAULT_LLM_MODEL") or "gpt-4o-mini"
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(f"[LLM Provider] Using OpenAI model: {self.model}")
            return

        # Priority 2: Gemini (fallback)
        gemini_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key and GEMINI_AVAILABLE:
            self._mode = "gemini"
            self._gemini = GeminiProvider(
                api_key=gemini_key, 
                llm_model=model or os.getenv("DEFAULT_LLM_MODEL") or "gemini-1.5-flash"
            )
            self.model = getattr(self._gemini, "llm_model", model or "gemini-1.5-flash")
            logger.info(f"[LLM Provider] Using Gemini model: {self.model}")
            return

        # No provider configured - raise error
        raise ValueError(
            "No LLM provider configured. "
            "Set OPENAI_API_KEY (recommended) or GEMINI_API_KEY."
        )
    
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
            if getattr(self, "_mode", None) == "gemini":
                return self._gemini.llm(prompt=prompt, system_prompt=system_prompt, temperature=temperature, max_output_tokens=max_tokens)  # type: ignore

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

