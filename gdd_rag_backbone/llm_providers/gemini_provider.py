"""
Google Gemini provider implementation using google-genai package.
"""
import os
from typing import List, Optional, Dict, Any
from gdd_rag_backbone.config import GEMINI_API_KEY, DEFAULT_LLM_MODEL, DEFAULT_EMBEDDING_MODEL
from gdd_rag_backbone.llm_providers.base import LlmProvider, EmbeddingProvider


class GeminiProvider(LlmProvider, EmbeddingProvider):
    """
    Google Gemini provider using the Gemini Developer API.
    
    Requires GEMINI_API_KEY environment variable to be set.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            llm_model: LLM model name (defaults to DEFAULT_LLM_MODEL or "gemini-2.5-flash")
            embedding_model: Embedding model name (defaults to DEFAULT_EMBEDDING_MODEL or "text-embedding-004")
        """
        self.api_key = api_key or GEMINI_API_KEY
        # Always default to a Gemini model, ignore DEFAULT_LLM_MODEL if it's not a Gemini model
        if llm_model:
            model_name = llm_model
        elif DEFAULT_LLM_MODEL and DEFAULT_LLM_MODEL.startswith("gemini"):
            model_name = DEFAULT_LLM_MODEL
        else:
            model_name = "gemini-2.5-flash"
        
        # Ensure model name has 'models/' prefix if not already present
        if not model_name.startswith("models/"):
            self.llm_model = f"models/{model_name}"
        else:
            self.llm_model = model_name
        
        # Same for embedding model - ensure it's a Gemini model
        if embedding_model:
            model_name = embedding_model
        elif DEFAULT_EMBEDDING_MODEL:
            model_name = DEFAULT_EMBEDDING_MODEL
        else:
            model_name = "text-embedding-004"
        
        # Replace invalid models with valid Gemini models
        if "text-embedding-v2" in model_name or "text-embedding-v3" in model_name:
            model_name = "text-embedding-004"  # Use valid Gemini embedding model
        
        # Ensure model name has 'models/' prefix if not already present
        if not model_name.startswith("models/"):
            self.embedding_model = f"models/{model_name}"
        else:
            self.embedding_model = model_name
        
        # Embedding dimension for Gemini models
        # text-embedding-004 has 768 dimensions
        self.embedding_dim = 768
        
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable must be set, "
                "or api_key must be provided"
            )
        
        # Initialize Gemini client
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except ImportError:
            raise RuntimeError(
                "google-genai package is required. Install with: pip install google-genai"
            )
    
    def llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any
    ) -> str:
        """
        Generate text using Google Gemini.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt (combined with user prompt for Gemini)
            history_messages: Optional conversation history
            **kwargs: Additional parameters (temperature, max_output_tokens, etc.)
        
        Returns:
            Generated text response
        """
        try:
            from google.genai import types
            
            # Build contents - combine history and current prompt
            # For simplicity, format history as text (Gemini can handle this)
            prompt_sections = []
            
            # Add history messages if provided
            if history_messages:
                for msg in history_messages:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        role = msg["role"]
                        content = msg["content"]
                        if role == "system":
                            # System messages go to system_instruction in config
                            if not system_prompt:
                                system_prompt = content
                            else:
                                system_prompt = f"{system_prompt}\n{content}"
                        else:
                            prompt_sections.append(f"[{role}] {content}")
            
            # Add current prompt
            prompt_sections.append(f"[user] {prompt}")
            combined_prompt = "\n".join(prompt_sections)
            
            # Build generation config from kwargs
            # Filter valid Gemini parameters
            gemini_valid_params = {
                'temperature', 'top_p', 'top_k', 'max_output_tokens',
                'candidate_count', 'stop_sequences', 'response_mime_type'
            }
            
            config_dict = {}
            for key, value in kwargs.items():
                if key in gemini_valid_params:
                    config_dict[key] = value
                elif key == "max_tokens":  # Map max_tokens to max_output_tokens
                    config_dict["max_output_tokens"] = value
            
            # Set defaults if not provided
            if "temperature" not in config_dict:
                config_dict["temperature"] = kwargs.get("temperature", 0.7)
            if "max_output_tokens" not in config_dict:
                config_dict["max_output_tokens"] = kwargs.get("max_output_tokens", 2048)
            
            # Add system_instruction if provided
            if system_prompt:
                config_dict["system_instruction"] = system_prompt
            
            # Remove None values
            config_dict = {k: v for k, v in config_dict.items() if v is not None}
            
            config = types.GenerateContentConfig(**config_dict) if config_dict else None
            
            # Make API call
            request_kwargs = {
                "model": self.llm_model,
                "contents": [combined_prompt],
            }
            if config:
                request_kwargs["config"] = config
            
            response = self.client.models.generate_content(**request_kwargs)
            
            # Extract text from response
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    return candidate.content.parts[0].text
                elif hasattr(candidate, 'content'):
                    return str(candidate.content)
            else:
                return str(response)
                
        except ImportError:
            raise RuntimeError(
                "google-genai package is required. Install with: pip install google-genai"
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {str(e)}")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using Google Gemini embedding model.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors
        """
        try:
            from google.genai import types
            
            embeddings_list = []
            
            # Process texts - try batch first, then individual if needed
            try:
                # Try batch embedding - pass texts directly as strings
                response = self.client.models.embed_content(
                    model=self.embedding_model,
                    contents=texts,  # Parameter is 'contents', not 'content'
                )
                
                # Extract embeddings from response
                if hasattr(response, 'embeddings'):
                    for embedding in response.embeddings:
                        if hasattr(embedding, 'values'):
                            embeddings_list.append(embedding.values)
                        elif hasattr(embedding, 'embedding'):
                            embeddings_list.append(embedding.embedding.values if hasattr(embedding.embedding, 'values') else embedding.embedding)
                        else:
                            embeddings_list.append(list(embedding) if isinstance(embedding, (list, tuple)) else [float(embedding)])
                elif hasattr(response, 'embedding'):
                    # Single embedding response
                    if hasattr(response.embedding, 'values'):
                        embeddings_list.append(response.embedding.values)
                    else:
                        embeddings_list.append(list(response.embedding) if isinstance(response.embedding, (list, tuple)) else [float(response.embedding)])
                else:
                    # Fall back to individual processing
                    raise ValueError("Batch embedding not supported, falling back to individual")
                    
            except Exception:
                # Fall back to individual embedding requests
                embeddings_list = []
                for text in texts:
                    try:
                        # Pass text as string directly - parameter is 'contents'
                        response = self.client.models.embed_content(
                            model=self.embedding_model,
                            contents=text,  # Parameter is 'contents', not 'content'
                        )
                        
                        # Extract embedding from response
                        if hasattr(response, 'embedding'):
                            if hasattr(response.embedding, 'values'):
                                embeddings_list.append(response.embedding.values)
                            else:
                                embeddings_list.append(list(response.embedding) if isinstance(response.embedding, (list, tuple)) else [float(response.embedding)])
                        elif hasattr(response, 'values'):
                            embeddings_list.append(response.values)
                        else:
                            raise RuntimeError(f"Unexpected embedding response format: {response}")
                            
                    except Exception as e:
                        raise RuntimeError(f"Gemini embedding API call failed for text: {str(e)}")
            
            return embeddings_list
                
        except ImportError:
            raise RuntimeError(
                "google-genai package is required. Install with: pip install google-genai"
            )
        except Exception as e:
            raise RuntimeError(f"Gemini embedding API call failed: {str(e)}")

