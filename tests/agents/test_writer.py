"""Writer Agent: end-to-end with a fake LLM.

Asserts that all 4 nodes run, output is written to runtime/, audit is
populated, and the api key never leaks to stdout/logs.
"""

from __future__ import annotations

import json
import logging

import pytest

from agens_novel.agents.writer.nodes import run_writer_agent


@pytest.mark.usefixtures("temp_project_root", "set_api_key")
def test_writer_agent_end_to_end(fake_llm, caplog) -> None:
    mock_call, canned = fake_llm
    caplog.set_level(logging.INFO, logger="agens_novel")

    result = run_writer_agent(user_input="用 50 字写一段都市修仙的开头,主角叫许满")

    # 1. LLM stub was called.
    assert mock_call.await_count == 1

    # 2. Final state has output and audit paths.
    assert "许满" in result["output_text"] or canned in result["output_text"]
    assert result["output_path"].endswith("output.md")
    assert result["audit_path"].endswith("audit.json")

    # 3. Audit file is well-formed JSON with expected keys.
    audit = json.loads(open(result["audit_path"], encoding="utf-8").read())
    assert audit["agent"] == "writer"
    assert audit["model"] == "agnes-2.0-flash"
    assert audit["usage"]["total_tokens"] == 150
    assert not audit["llm_error"]

    # 4. Output file exists and has the right content.
    output_path = result["output_path"]
    content = open(output_path, encoding="utf-8").read()
    assert content == canned

    # 5. CRITICAL: the api key must not appear anywhere in the logs.
    full_log = caplog.text
    assert "sk-test-fixture" not in full_log
