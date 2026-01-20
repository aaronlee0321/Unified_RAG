"""
Patch for lightrag to export LightRAG and QueryParam for raganything compatibility.

This patch attempts to find LightRAG and QueryParam in various locations
within the lightrag package and export them at the top level.
Also patches missing get_env_value function.
"""
import sys
import importlib
import importlib.util
import os

def patch_lightrag():
    """Patch lightrag module to export LightRAG and QueryParam."""
    try:
        # Check if lightrag is available (may not be installed on Python 3.9)
        try:
            import lightrag
        except ImportError:
            print("[PATCH] Warning: lightrag not installed. RAGAnything features will not be available.")
            print("[PATCH] To use RAGAnything, upgrade to Python 3.10+ and install: pip install lightrag lightrag-hku")
            return
        # First, patch utils to add missing get_env_value
        try:
            import lightrag.utils as utils_module
            if not hasattr(utils_module, 'get_env_value'):
                # Try to import from the old utils.py file
                try:
                    # Check if there's a utils.py (old structure)
                    utils_py_path = os.path.join(os.path.dirname(lightrag.__file__), 'utils.py')
                    if os.path.exists(utils_py_path):
                        spec = importlib.util.spec_from_file_location("lightrag.utils_old", utils_py_path)
                        old_utils = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(old_utils)
                        if hasattr(old_utils, 'get_env_value'):
                            utils_module.get_env_value = old_utils.get_env_value
                            print("[PATCH] Patched get_env_value into lightrag.utils")
                    else:
                        raise ImportError("No utils.py found")
                except:
                    # If that doesn't work, create a simple implementation
                    def get_env_value(env_key: str, default: any = None, value_type: type = str, special_none: bool = False) -> any:
                        """Get value from environment variable with type conversion."""
                        value = os.getenv(env_key)
                        if value is None:
                            return default
                        if special_none and value == "None":
                            return None
                        try:
                            return value_type(value)
                        except (ValueError, TypeError):
                            return default
                    utils_module.get_env_value = get_env_value
                    print("[PATCH] Created get_env_value in lightrag.utils")
        except Exception as e:
            print(f"[PATCH] Could not patch utils: {e}")
        
        # Import lightrag first
        import lightrag
        
        # Patch missing mineru_parser module - raganything tries to import this but it doesn't exist
        try:
            if 'lightrag.mineru_parser' not in sys.modules:
                # Create a stub mineru_parser module
                class MineruParserStub:
                    """Stub for MineruParser when not available."""
                    pass
                
                # Create a fake module
                import types
                mineru_parser_module = types.ModuleType('lightrag.mineru_parser')
                mineru_parser_module.MineruParser = MineruParserStub
                sys.modules['lightrag.mineru_parser'] = mineru_parser_module
                print("[PATCH] Created stub mineru_parser module")
        except Exception as e:
            print(f"[PATCH] Could not patch mineru_parser: {e}")
        import inspect
        
        # Only patch if LightRAG is not already exported
        if not hasattr(lightrag, 'LightRAG'):
            # Try various possible import paths
            possible_paths = [
                'lightrag.lightrag',
                'lightrag.core.lightrag', 
                'lightrag.core',
                'lightrag.components.lightrag',
            ]
            
            for path in possible_paths:
                try:
                    module = importlib.import_module(path)
                    if hasattr(module, 'LightRAG'):
                        lightrag.LightRAG = module.LightRAG
                        print(f"[PATCH] Patched LightRAG from {path}")
                        break
                except (ImportError, AttributeError):
                    continue
            
            # If still not found, search all modules recursively
            if not hasattr(lightrag, 'LightRAG'):
                # Handle namespace packages (where __file__ might be None)
                try:
                    if hasattr(lightrag, '__path__') and lightrag.__path__:
                        lightrag_path = lightrag.__path__[0]
                        for root, dirs, files in os.walk(lightrag_path):
                            for file in files:
                                if file.endswith('.py') and not file.startswith('__'):
                                    rel_path = os.path.relpath(os.path.join(root, file), lightrag_path)
                                    module_path = 'lightrag.' + rel_path.replace(os.sep, '.').replace('.py', '')
                                    try:
                                        module = importlib.import_module(module_path)
                                        if hasattr(module, 'LightRAG'):
                                            lightrag.LightRAG = module.LightRAG
                                            print(f"[PATCH] Patched LightRAG from {module_path}")
                                            break
                                    except (ImportError, AttributeError, ValueError):
                                        continue
                            if hasattr(lightrag, 'LightRAG'):
                                break
                except (AttributeError, IndexError, OSError) as e:
                    print(f"[PATCH] Could not search lightrag path: {e}")
        
        # Try to find QueryParam
        if not hasattr(lightrag, 'QueryParam'):
            possible_paths = [
                'lightrag.lightrag',
                'lightrag.core.query',
                'lightrag.core',
            ]
            
            for path in possible_paths:
                try:
                    module = importlib.import_module(path)
                    if hasattr(module, 'QueryParam'):
                        lightrag.QueryParam = module.QueryParam
                        print(f"✓ Patched QueryParam from {path}")
                        break
                except (ImportError, AttributeError):
                    continue
            
            # If QueryParam still not found, create a minimal TypedDict
            if not hasattr(lightrag, 'QueryParam'):
                from typing import TypedDict
                class QueryParam(TypedDict, total=False):
                    """Minimal QueryParam for compatibility."""
                    pass
                lightrag.QueryParam = QueryParam
                print("✓ Created minimal QueryParam")
        
    except Exception as e:
        # If patching fails, the import error will be raised by raganything
        print(f"[PATCH] Warning: Could not patch lightrag: {e}")

# Apply patch immediately when this module is imported
patch_lightrag()

