# -*- coding: utf-8 -*-
"""Smoke tests for the TBM supervisor-style agent API.

Run this after the FastAPI backend is already running:

    python backend/scripts/test_agent_v2.py

The script uses the project's real TBM data through HTTP API calls. It does not
create fake CSV data and it does not modify your data files.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class CheckFailed(AssertionError):
    pass


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Request json."""
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = Request(url=url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot connect to {url}. Start the backend first, for example: "
            "cd backend; uvicorn app:app --reload --port 8000"
        ) from exc

    return json.loads(body)


def require(condition: bool, message: str) -> None:
    """Handle require."""
    if not condition:
        raise CheckFailed(message)


def check_capabilities(base_url: str) -> None:
    """Check capabilities."""
    response = request_json("GET", f"{base_url}/api/tbm/agent_v2/capabilities")
    supervisor = response.get("supervisor", {})
    agents = supervisor.get("active_agents", [])

    require(supervisor.get("name") == "TBMSupervisorAgent", "missing TBMSupervisorAgent metadata")
    require("DataAgent" in agents, "DataAgent is not registered")
    require("SafetyAgent" in agents, "SafetyAgent is not registered")
    require("GeologyAgent" in agents, "GeologyAgent is not registered")
    require("TwinAgent" in agents, "TwinAgent is not registered")
    print("[OK] capabilities exposes the supervisor and domain agents")


def check_available_dates(base_url: str) -> str:
    """Check available dates."""
    response = request_json(
        "POST",
        f"{base_url}/api/tbm/agent_v2",
        {
            "query": "有哪些可用日期",
            "date": None,
            "use_llm": False,
            "verbose": False,
        },
    )
    data = response.get("data", {})
    highlights = data.get("highlights", {})

    require(response.get("success") is True, "available-date query failed")
    require(data.get("mode") == "supervisor_v2", "agent_v2 did not return supervisor_v2 mode")
    require(data.get("routed_agents") == ["DataAgent"], "available-date query did not route to DataAgent")
    require(highlights.get("available_date_count", 0) > 0, "no available dates were returned")

    latest_date = highlights.get("latest_date")
    require(bool(latest_date), "latest_date highlight is missing")
    print(f"[OK] available dates route works, latest date: {latest_date}")
    return str(latest_date)


def check_multi_agent_route(base_url: str, date: str, verbose: bool) -> None:
    """Check multi agent route."""
    response = request_json(
        "POST",
        f"{base_url}/api/tbm/agent_v2",
        {
            "query": "分析瓦斯、地质风险和数字孪生状态",
            "date": date,
            "use_llm": False,
            "verbose": verbose,
        },
    )
    data = response.get("data", {})
    routed_agents = data.get("routed_agents", [])
    highlights = data.get("highlights", {})

    require(response.get("success") is True, "multi-agent query failed")
    require("SafetyAgent" in routed_agents, "gas query did not route to SafetyAgent")
    require("GeologyAgent" in routed_agents, "geology query did not route to GeologyAgent")
    require("TwinAgent" in routed_agents, "digital twin query did not route to TwinAgent")
    require("answer" in data and data["answer"], "answer is missing")
    require("tool_results" in data and len(data["tool_results"]) >= 3, "tool results are missing")
    require("gas_exceed_types" in highlights, "gas highlight is missing")
    require("has_geology" in highlights, "geology highlight is missing")
    require("current_chainage_dk" in highlights, "digital twin highlight is missing")

    mode = "verbose" if verbose else "compact"
    print(f"[OK] {mode} multi-agent route works for {date}: {', '.join(routed_agents)}")


def check_invalid_date(base_url: str) -> None:
    """Check invalid date."""
    response = request_json(
        "POST",
        f"{base_url}/api/tbm/agent_v2",
        {
            "query": "分析瓦斯",
            "date": "2099-01-01",
            "use_llm": False,
            "verbose": False,
        },
    )
    require(response.get("success") is False, "invalid date should fail cleanly")
    require(response.get("message"), "invalid date failure message is missing")
    print("[OK] invalid date fails cleanly")


def main() -> int:
    """Run the script entry point."""
    parser = argparse.ArgumentParser(description="Smoke-test /api/tbm/agent_v2.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL.")
    parser.add_argument("--date", default=None, help="Date to use for analysis, for example 2023-12-30.")
    parser.add_argument("--skip-invalid-date", action="store_true", help="Skip the invalid-date check.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    try:
        check_capabilities(base_url)
        latest_date = check_available_dates(base_url)
        test_date = args.date or latest_date
        check_multi_agent_route(base_url, test_date, verbose=False)
        check_multi_agent_route(base_url, test_date, verbose=True)
        if not args.skip_invalid_date:
            check_invalid_date(base_url)
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print("[DONE] agent_v2 smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())