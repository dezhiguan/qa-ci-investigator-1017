import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_execute_normal_flow():
    # Mock context
    ctx = MagicMock()
    ctx.prompt = AsyncMock(return_value=MagicMock(
        compile=MagicMock(return_value="Simulated prompt with CI 433 and PR 20")
    ))
    ctx.llm = MagicMock()
    ctx.llm.chat = AsyncMock(return_value={
        "content": '{"failed_step":"build-container","log_evidence":"Step 5/10 : RUN pip install -r requirements.txt\\nERROR: Could not find a version that satisfies...","pr_changes":"updated requirements.txt adding torch==2.0.0","gate_result":"FAIL (accuracy -2.1%)","root_cause":"torch==2.0.0 requires CUDA 11.8 but CI runner has CUDA 11.7","fix_steps":["Pin torch==1.13.1","Add CUDA version check in setup.sh"],"pending_confirmation":["Validate torch CPU fallback behavior"]}'
    })
    ctx.tools = MagicMock()
    ctx.tools.call = AsyncMock(side_effect=[
        {"raw": "Step 5/10 : RUN pip install -r requirements.txt\nERROR: Could not find a version that satisfies..."},
        {"status": "FAIL", "details": "accuracy -2.1%"},
        {"diff": "diff --git a/requirements.txt b/requirements.txt\\n+ torch==2.0.0"}
    ])

    # Execute
    result = await __import__("role").execute({"text": "CI run 433 container build failed, PR #20 modified requirements.txt"}, ctx)

    # Assert
    assert result["decision"] == "INVESTIGATE"
    assert "result" in result
    assert result["result"]["failed_step"] == "build-container"
    assert "torch==2.0.0" in result["result"]["pr_changes"]
    assert "CUDA 11.7" in result["result"]["root_cause"]


@pytest.mark.asyncio
async def test_execute_missing_both_ids():
    ctx = MagicMock()
    result = await __import__("role").execute({"text": "No IDs given"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "Neither CI run ID nor PR number provided." in result["reason"]


@pytest.mark.asyncio
async def test_execute_invalid_pr_negative():
    ctx = MagicMock()
    result = await __import__("role").execute({"text": "CI run 447, PR #-5"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "Invalid PR number '-5': must be a positive integer." in result["reason"]


@pytest.mark.asyncio
async def test_execute_tool_failure_all_three():
    ctx = MagicMock()
    ctx.prompt = AsyncMock(return_value=MagicMock(
        compile=MagicMock(return_value="prompt")
    ))
    ctx.llm = MagicMock()
    ctx.llm.chat = AsyncMock(return_value={"content": "{\"failed_step\":\"x\"}"})
    ctx.tools = MagicMock()
    # Simulate all three tools failing
    ctx.tools.call = AsyncMock(side_effect=[
        Exception("access denied"),
        Exception("unauthorized"),
        Exception("timeout")
    ])

    result = await __import__("role").execute({"text": "CI run 448, PR #35"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "All three required tools failed" in result["reason"]