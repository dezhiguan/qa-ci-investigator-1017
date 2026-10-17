import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_execute_normal_flow():
    # Mock context
    ctx = MagicMock()
    ctx.prompt = AsyncMock(return_value=MagicMock(
        compile=AsyncMock(return_value="Simulated prompt with CI 433 and PR 20")
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
async def test_execute_invalid_pr_negative():
    ctx = MagicMock()
    result = await __import__("role").execute({"text": "CI run 447, PR #-5"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "Invalid PR number '-5'" in result["reason"]


@pytest.mark.asyncio
async def test_execute_tool_failure_one_required():
    ctx = MagicMock()
    ctx.prompt = AsyncMock(return_value=MagicMock(
        compile=AsyncMock(return_value="prompt")
    ))
    ctx.llm = MagicMock()
    ctx.llm.chat = AsyncMock(return_value={"content": "{\"failed_step\":\"x\"}"})
    ctx.tools = MagicMock()
    # Simulate only ci.log.fetch failing
    ctx.tools.call = AsyncMock(side_effect=[
        Exception("access denied"),
        {"status": "PASS"},
        {"diff": "dummy"}
    ])

    result = await __import__("role").execute({"text": "CI run 448, PR #35"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "ci.log.fetch" in result["reason"]


@pytest.mark.asyncio
async def test_execute_missing_both_ids():
    ctx = MagicMock()
    result = await __import__("role").execute({"text": "No IDs given"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "Neither CI run ID nor PR number provided." in result["reason"]


@pytest.mark.asyncio
async def test_execute_only_ci_id():
    ctx = MagicMock()
    result = await __import__("role").execute({"text": "CI run 446"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "Both CI run ID and PR number are required" in result["reason"]


@pytest.mark.asyncio
async def test_execute_leading_zero_pr():
    ctx = MagicMock()
    result = await __import__("role").execute({"text": "CI run 450, PR #007"}, ctx)
    assert result["decision"] == "BLOCKED"
    assert "without leading zeros" in result["reason"]