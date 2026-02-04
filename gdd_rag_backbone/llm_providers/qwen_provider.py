"""
Qwen (Alibaba DashScope) provider implementation.
"""

from typing import Any, Dict, List, Optional

from gdd_rag_backbone.config import (
    DASHSCOPE_REGION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    QWEN_API_KEY,
    QWEN_BASE_URL,
)
from gdd_rag_backbone.llm_providers.base import EmbeddingProvider, LlmProvider


class QwenProvider(LlmProvider, EmbeddingProvider):
    """
    Qwen provider using Alibaba DashScope API.

    Requires QWEN_API_KEY environment variable to be set.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        """
        Initialize Qwen provider.

        Args:
            api_key: DashScope API key (defaults to QWEN_API_KEY env var)
            base_url: API base URL (defaults to QWEN_BASE_URL env var or default)
            llm_model: LLM model name (defaults to DEFAULT_LLM_MODEL)
            embedding_model: Embedding model name (defaults to DEFAULT_EMBEDDING_MODEL)
        """
        self.api_key = api_key or QWEN_API_KEY
        self.base_url = base_url or QWEN_BASE_URL
        self.region = DASHSCOPE_REGION  # Region for DashScope API (e.g., "intl", "cn")
        self.llm_model = llm_model or DEFAULT_LLM_MODEL
        self.embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL

        # Embedding dimension for LightRAG compatibility
        # text-embedding-v3 and v4 have 1024 dimensions
        # text-embedding-v2 has 1536 dimensions (if available)
        if self.embedding_model in ["text-embedding-v3", "text-embedding-v4"]:
            self.embedding_dim = 1024
        elif self.embedding_model == "text-embedding-v2":
            self.embedding_dim = 1536
        else:
            self.embedding_dim = 1024  # Default for newer models

        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY or QWEN_API_KEY environment variable must be set, "
                "or api_key must be provided"
            )

        # Only set DashScope API key if we're using DashScope endpoint (not OpenAI)
        # Check if base_url points to OpenAI - if so, skip DashScope initialization
        is_openai_endpoint = self.base_url and "openai.com" in self.base_url.lower()

        if not is_openai_endpoint:
            # Set DashScope API key for the library (if dashscope is available)
            try:
                import dashscope

                dashscope.api_key = self.api_key
                if self.region:
                    dashscope.region = self.region
            except ImportError:
                pass  # dashscope not installed yet

        # TODO: Initialize DashScope client here
        # Example:
        # from dashscope import Generation, Embeddings
        # self.llm_client = Generation
        # self.embedding_client = Embeddings

    def llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate text using Qwen LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            history_messages: Optional conversation history
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Generated text response
        """
        # Use OpenAI-compatible API endpoint (recommended approach)
        try:
            try:
                from openai import OpenAI
            except ImportError:
                # Fallback to dashscope native API if OpenAI client not available
                import dashscope
                from dashscope import Generation

                # Ensure API key and region are set in dashscope module
                dashscope.api_key = self.api_key
                if self.region:
                    dashscope.region = self.region

                # Build messages list
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                if history_messages:
                    for msg in history_messages:
                        if isinstance(msg, dict) and "role" in msg and "content" in msg:
                            messages.append(msg)
                messages.append({"role": "user", "content": prompt})

                # Filter kwargs for native DashScope API
                # DashScope Generation.call accepts: temperature, top_p, top_k, max_tokens, etc.
                # Filter out LightRAG internal parameters
                dashscope_valid_params = {
                    "temperature",
                    "top_p",
                    "top_k",
                    "max_tokens",
                    "seed",
                    "stop",
                    "incremental_output",
                    "result_format",
                    "enable_search",
                    "repetition_penalty",
                    "stream",
                    "output",
                }

                filtered_kwargs = {k: v for k, v in kwargs.items() if k in dashscope_valid_params}

                # Make API call using native DashScope
                response = Generation.call(
                    model=self.llm_model,
                    messages=messages,
                    result_format="message",
                    **filtered_kwargs,
                )

                if response.status_code == 200:
                    if hasattr(response, "output") and hasattr(response.output, "choices"):
                        return response.output.choices[0].message.content
                    elif hasattr(response, "output"):
                        return str(response.output)
                    else:
                        return str(response)
                else:
                    error_msg = getattr(response, "message", f"Status code: {response.status_code}")
                    raise RuntimeError(f"Qwen API error: {error_msg}")

            # Use OpenAI-compatible API (preferred method)
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

            # Build messages list
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if history_messages:
                for msg in history_messages:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages.append(msg)
            messages.append({"role": "user", "content": prompt})

            # Filter kwargs to only include valid OpenAI API parameters
            # LightRAG may pass internal parameters like 'hashing_kv', 'hashed_query', etc.
            # that should not be passed to the API
            valid_params = {
                "audio",
                "extra_body",
                "extra_headers",
                "extra_query",
                "frequency_penalty",
                "function_call",
                "functions",
                "logit_bias",
                "logprobs",
                "max_completion_tokens",
                "max_tokens",
                "metadata",
                "modalities",
                "n",
                "parallel_tool_calls",
                "prediction",
                "presence_penalty",
                "prompt_cache_key",
                "prompt_cache_retention",
                "reasoning_effort",
                "response_format",
                "safety_identifier",
                "seed",
                "service_tier",
                "stop",
                "store",
                "stream",
                "stream_options",
                "temperature",
                "timeout",
                "tool_choice",
                "tools",
                "top_logprobs",
                "top_p",
                "user",
                "verbosity",
                "web_search_options",
            }

            filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

            # Make API call with filtered parameters
            response = client.chat.completions.create(
                model=self.llm_model, messages=messages, **filtered_kwargs
            )

            # Extract content
            return response.choices[0].message.content

        except ImportError:
            raise RuntimeError(
                "openai or dashscope package is required. Install with: pip install openai dashscope"
            )
        except Exception as e:
            raise RuntimeError(f"Qwen API call failed: {str(e)}")

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using Qwen embedding model.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        # Implement actual DashScope embedding API call
        # Note: Embedding API may require separate access/permissions
        try:
            # Use OpenAI-compatible endpoint (works for text-embedding-v3 and v4)
            try:
                from openai import OpenAI

                client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )

                # Batch process embeddings (OpenAI API can handle batch)
                # Try batch first for efficiency
                try:
                    # For OpenAI models, dimensions parameter is optional
                    # text-embedding-3-small/large support dimensions parameter
                    # text-embedding-ada-002 doesn't support dimensions parameter
                    create_kwargs = {
                        "model": self.embedding_model,
                        "input": texts,  # Send all texts at once
                        "encoding_format": "float",
                    }
                    # Only add dimensions for models that support it (text-embedding-3-*)
                    if "text-embedding-3" in self.embedding_model and hasattr(
                        self, "embedding_dim"
                    ):
                        create_kwargs["dimensions"] = self.embedding_dim

                    response = client.embeddings.create(**create_kwargs)
                    return [item.embedding for item in response.data]
                except Exception:
                    # If batch fails, try individual requests
                    embeddings_list = []
                    for text in texts:
                        create_kwargs = {
                            "model": self.embedding_model,
                            "input": text,
                            "encoding_format": "float",
                        }
                        # Only add dimensions for models that support it
                        if "text-embedding-3" in self.embedding_model and hasattr(
                            self, "embedding_dim"
                        ):
                            create_kwargs["dimensions"] = self.embedding_dim

                        response = client.embeddings.create(**create_kwargs)
                        embeddings_list.append(response.data[0].embedding)
                    return embeddings_list
            except ImportError:
                # Fall back to native DashScope API if OpenAI client not available
                pass
            except Exception as e:
                # If using OpenAI endpoint, don't fall back to DashScope - raise the error
                if self.base_url and "openai.com" in self.base_url.lower():
                    # This is an OpenAI endpoint - don't fall back to DashScope
                    error_msg = str(e)
                    error_type = type(e).__name__

                    # Check for quota/rate limit errors
                    is_quota_error = (
                        "429" in error_msg
                        or "quota" in error_msg.lower()
                        or "insufficient_quota" in error_msg.lower()
                        or "RateLimitError" in error_type
                    )

                    if is_quota_error:
                        raise RuntimeError(
                            f"OpenAI embedding API error: Quota exceeded (429). "
                            f"Your API key is valid but you've exceeded your usage quota. "
                            f"Please add credits at https://platform.openai.com/account/billing "
                            f"or wait for quota to reset. Error: {error_msg}"
                        )
                    elif (
                        "Invalid API-key" in error_msg
                        or "401" in error_msg
                        or "authentication" in error_msg.lower()
                    ):
                        raise RuntimeError(
                            f"OpenAI embedding API error: {error_msg}. "
                            "Please check your OPENAI_API_KEY is valid and has embedding access."
                        )
                    raise RuntimeError(f"OpenAI embedding API error: {error_msg}")

                # If OpenAI-compatible fails for DashScope endpoint, fall back to native API
                # Only fall back if it's not an access denied error (which means model exists)
                if "Access denied" not in str(e) and "does not exist" not in str(e):
                    pass
                else:
                    raise

            # Use native DashScope embeddings API (only if not using OpenAI endpoint)
            if self.base_url and "openai.com" in self.base_url.lower():
                # Should not reach here if OpenAI endpoint is used
                raise RuntimeError(
                    "OpenAI endpoint should use OpenAI-compatible API, not DashScope native API. "
                    "This indicates a configuration error."
                )
            import dashscope
            from dashscope import embeddings

            # Ensure API key and region are set in dashscope module
            dashscope.api_key = self.api_key
            if self.region:
                dashscope.region = self.region

            # Make API call using TextEmbedding
            response = embeddings.TextEmbedding.call(
                model=self.embedding_model,
                input=texts,
            )

            # Check response status
            if response.status_code == 200:
                # Extract embeddings from response
                if hasattr(response, "output") and hasattr(response.output, "embeddings"):
                    return [item["embedding"] for item in response.output["embeddings"]]
                elif hasattr(response, "output"):
                    # Handle different response formats
                    output = response.output
                    if isinstance(output, list):
                        return [item.get("embedding", item) for item in output]
                    elif isinstance(output, dict) and "embeddings" in output:
                        return [item["embedding"] for item in output["embeddings"]]
                    else:
                        raise RuntimeError(f"Unexpected embedding response format: {output}")
                else:
                    raise RuntimeError(f"Unexpected embedding response: {response}")
            else:
                error_msg = getattr(response, "message", f"Status code: {response.status_code}")
                # Provide helpful error message
                if response.status_code == 401:
                    raise RuntimeError(
                        f"Qwen embedding API error: {error_msg}. "
                        "Your API key may not have access to embedding services. "
                        "Please check your DashScope console and enable embedding access."
                    )
                raise RuntimeError(f"Qwen embedding API error: {error_msg}")

        except ImportError:
            raise RuntimeError(
                "openai or dashscope package is required. Install with: pip install openai dashscope"
            )
        except Exception as e:
            raise RuntimeError(f"Qwen embedding API call failed: {str(e)}")
