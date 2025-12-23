#!/usr/bin/env python3
"""Check valid parameters for OpenAI chat completions."""
from openai import OpenAI
import inspect

client = OpenAI()
sig = inspect.signature(client.chat.completions.create)

print("Valid parameters for chat.completions.create():")
for param_name, param in sig.parameters.items():
    if param_name == "self":
        continue
    default = "" if param.default == inspect.Parameter.empty else f" = {param.default}"
    print(f"  - {param_name}{default}")

