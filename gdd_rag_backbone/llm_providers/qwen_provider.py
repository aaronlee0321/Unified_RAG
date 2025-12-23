"""
Qwen (Alibaba DashScope) provider implementation.
"""
import os
from typing import List, Optional, Dict, Any
from gdd_rag_backbone.config import QWEN_API_KEY, QWEN_BASE_URL, DASHSCOPE_REGION, DEFAULT_LLM_MODEL, DEFAULT_EMBEDDING_MODEL
from gdd_rag_backbone.llm_providers.base import LlmProvider, EmbeddingProvider


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
        if self.embedding_model in ['text-embedding-v3', 'text-embedding-v4']:
            self.embedding_dim = 1024
        elif self.embedding_model == 'text-embedding-v2':
            self.embedding_dim = 1536
        else:
            self.embedding_dim = 1024  # Default for newer models
        
        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY or QWEN_API_KEY environment variable must be set, "
                "or api_key must be provided"
            )
        
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
        **kwargs: Any
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
                from dashscope import Generation
                import dashscope
                
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
                    'temperature', 'top_p', 'top_k', 'max_tokens', 'seed',
                    'stop', 'incremental_output', 'result_format', 'enable_search',
                    'repetition_penalty', 'stream', 'output'
                }
                
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in dashscope_valid_params}
                
                # Make API call using native DashScope
                response = Generation.call(
                    model=self.llm_model,
                    messages=messages,
                    result_format='message',
                    **filtered_kwargs
                )
                
                if response.status_code == 200:
                    if hasattr(response, 'output') and hasattr(response.output, 'choices'):
                        return response.output.choices[0].message.content
                    elif hasattr(response, 'output'):
                        return str(response.output)
                    else:
                        return str(response)
                else:
                    error_msg = getattr(response, 'message', f'Status code: {response.status_code}')
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
                'audio', 'extra_body', 'extra_headers', 'extra_query',
                'frequency_penalty', 'function_call', 'functions', 'logit_bias',
                'logprobs', 'max_completion_tokens', 'max_tokens', 'metadata',
                'modalities', 'n', 'parallel_tool_calls', 'prediction',
                'presence_penalty', 'prompt_cache_key', 'prompt_cache_retention',
                'reasoning_effort', 'response_format', 'safety_identifier', 'seed',
                'service_tier', 'stop', 'store', 'stream', 'stream_options',
                'temperature', 'timeout', 'tool_choice', 'tools', 'top_logprobs',
                'top_p', 'user', 'verbosity', 'web_search_options'
            }
            
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}
            
            # Make API call with filtered parameters
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                **filtered_kwargs
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
                    response = client.embeddings.create(
                        model=self.embedding_model,
                        input=texts,  # Send all texts at once
                    )
                    return [item.embedding for item in response.data]
                except Exception:
                    # If batch fails, try individual requests
                    embeddings_list = []
                    for text in texts:
                        response = client.embeddings.create(
                            model=self.embedding_model,
                            input=text,
                        )
                        embeddings_list.append(response.data[0].embedding)
                    return embeddings_list
            except ImportError:
                # Fall back to native DashScope API if OpenAI client not available
                pass
            except Exception as e:
                # If OpenAI-compatible fails, fall back to native API
                # Only fall back if it's not an access denied error (which means model exists)
                if "Access denied" not in str(e) and "does not exist" not in str(e):
                    pass
                else:
                    raise
            
            # Use native DashScope embeddings API
            from dashscope import embeddings
            import dashscope
            
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
                if hasattr(response, 'output') and hasattr(response.output, 'embeddings'):
                    return [item["embedding"] for item in response.output["embeddings"]]
                elif hasattr(response, 'output'):
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
                error_msg = getattr(response, 'message', f'Status code: {response.status_code}')
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

