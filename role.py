import json
import re
from typing import Dict, Any, Optional
from collections import defaultdict


async def execute(data: dict, ctx) -> dict:
    # Extract CI run ID and PR number from input text
    text = data.get("text", "")
    if not isinstance(text, str):
        return {
            "decision": "BLOCKED",
            "reason": "Input 'text' must be a string."
        }

    # Parse CI run ID and PR number using robust regex
    ci_match = re.search(r"CI\s+run\s+(\d+)", text, re.IGNORECASE)
    pr_match = re.search(r"PR\s+#?(\d+)", text, re.IGNORECASE)

    ci_run_id: Optional[str] = ci_match.group(1) if ci_match else None
    pr_number: Optional[str] = pr_match.group(1) if pr_match else None

    # Block if both missing
    if not ci_run_id and not pr_number:
        return {
            "decision": "BLOCKED",
            "reason": "Neither CI run ID nor PR number provided."
        }

    # Block if either is invalid (e.g., negative, non-digit, or leading zeros)
    if ci_run_id:
        if not ci_run_id.isdigit() or int(ci_run_id) <= 0 or ci_run_id != str(int(ci_run_id)):
            return {
                "decision": "BLOCKED",
                "reason": f"Invalid CI run ID '{ci_run_id}': must be a positive integer without leading zeros."
            }
    if pr_number:
        if not pr_number.isdigit() or int(pr_number) <= 0 or pr_number != str(int(pr_number)):
            return {
                "decision": "BLOCKED",
                "reason": f"Invalid PR number '{pr_number}': must be a positive integer without leading zeros."
            }

    # Block if only one is present — binding is required per H1 pending item
    if (ci_run_id and not pr_number) or (pr_number and not ci_run_id):
        return {
            "decision": "BLOCKED",
            "reason": "Both CI run ID and PR number are required and must be provided together."
        }

    # Fetch prompt
    try:
        prompt = await ctx.prompt("role")
        compiled = prompt.compile(input={"ci_run_id": ci_run_id, "pr_number": pr_number, "text": text})
    except Exception as e:
        return {
            "decision": "BLOCKED",
            "reason": f"Failed to load or compile prompt: {str(e)}"
        }

    # Call tools sequentially with error handling
    tool_results = {}

    # 1. Fetch CI log
    try:
        log_result = await ctx.tools.call("ci.log.fetch", run_id=ci_run_id)
        tool_results["ci_log"] = log_result
    except Exception as e:
        tool_results["ci_log"] = {"error": str(e)}

    # 2. Read gate report
    try:
        gate_result = await ctx.tools.call("keel.gate.report.read", pr_number=pr_number)
        tool_results["gate_report"] = gate_result
    except Exception as e:
        tool_results["gate_report"] = {"error": str(e)}

    # 3. Get PR diff
    try:
        diff_result = await ctx.tools.call("git.pr.diff", pr_number=pr_number)
        tool_results["pr_diff"] = diff_result
    except Exception as e:
        tool_results["pr_diff"] = {"error": str(e)}

    # Check for critical tool failures: any *required* tool failed → BLOCKED
    # Per H1: “any必需工具失败都返回 BLOCKED” and “至少调用两个需求单已选择的工具”
    # All three are required per spec; failure of any one blocks full evidence-based analysis.
    for key in ["ci_log", "gate_report", "pr_diff"]:
        if key in tool_results and isinstance(tool_results[key], dict) and "error" in tool_results[key]:
            return {
                "decision": "BLOCKED",
                "reason": f"Required tool '{key.replace('_', '.')}' failed: {tool_results[key]['error']}"
            }

    # Delegate to LLM with full context
    try:
        llm_response = await ctx.llm.chat(
            messages=[{"role": "user", "content": compiled}]
        )
        raw = llm_response.get("content", "{}").strip()
        parsed = json.loads(raw)
        # Enforce schema compliance
        required_keys = ["failed_step", "log_evidence", "pr_changes", "gate_result", "root_cause", "fix_steps", "pending_confirmation"]
        if not all(k in parsed for k in required_keys):
            raise ValueError(f"LLM output missing required keys: {required_keys}")
        # Validate types
        if not isinstance(parsed["fix_steps"], list) or not isinstance(parsed["pending_confirmation"], list):
            raise ValueError("'fix_steps' and 'pending_confirmation' must be lists")
        return {
            "decision": "INVESTIGATE",
            "result": parsed
        }
    except json.JSONDecodeError as e:
        return {
            "decision": "BLOCKED",
            "reason": f"LLM returned malformed JSON: {str(e)}"
        }
    except Exception as e:
        return {
            "decision": "BLOCKED",
            "reason": f"LLM invocation or parsing failed: {str(e)}"
        }