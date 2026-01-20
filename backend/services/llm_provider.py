"""
Simple LLM provider wrapper for keyword extractor.
Defaults to Google Gemini (free tier). Falls back to OpenAI-compatible APIs if Gemini isn't configured.
"""
import os
from typing import Optional

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
        
        Args:
            api_key: Optional API key (used for Gemini if provided; otherwise read from env)
            base_url: OpenAI-compatible API base URL (only used if Gemini isn't configured)
            model: Model name (Gemini model if using Gemini; otherwise OpenAI-compatible model)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Prefer Gemini always if configured
        gemini_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            if not GEMINI_AVAILABLE:
                raise RuntimeError(
                    "Gemini is configured (GEMINI_API_KEY set) but Gemini provider is not available. "
                    "Ensure `google-genai` is installed: pip install google-genai"
                )
            self._mode = "gemini"
            self._gemini = GeminiProvider(api_key=gemini_key, llm_model=model or os.getenv("DEFAULT_LLM_MODEL") or "gemini-1.5-flash")  # type: ignore
            self.model = getattr(self._gemini, "llm_model", model or "gemini-1.5-flash")
            logger.info(f"[LLM Provider] Using Gemini model: {self.model}")
            return

        # Fallback: OpenAI-compatible provider (only if Gemini isn't configured)
        self._mode = "openai_compatible"
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package is required for OpenAI-compatible mode. Install with: pip install openai")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No Gemini key found and no OpenAI-compatible key found. "
                "Set GEMINI_API_KEY (recommended) or OPENAI_API_KEY/QWEN_API_KEY/DASHSCOPE_API_KEY."
            )

        # Determine base URL (OpenAI-compatible)
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"

        self.model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        logger.info(f"[LLM Provider] Using OpenAI-compatible endpoint: {self.base_url} model={self.model}")
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





