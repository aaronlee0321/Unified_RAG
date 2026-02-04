"""
Token counting utilities.
"""


def token_count(text: str) -> int:
    """
    Simple token counter (approximate).
    Counts words as tokens.
    """
    return len(text.split())
