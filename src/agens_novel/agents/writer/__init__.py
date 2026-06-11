"""Writer Agent: produces a short prose snippet given a user request.

This is the canonical learning example. To build a second Agent:
  1. Copy this directory to agents/<your_agent_name>/
  2. Replace nodes.py with your own node functions.
  3. Replace graph.py with your own StateGraph assembly.
  4. Update the system prompt at config/prompts/system/<your_agent_name>.md.
"""

from .graph import build_writer_graph

__all__ = ["build_writer_graph"]
