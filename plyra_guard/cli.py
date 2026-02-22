"""
plyra-guard CLI
~~~~~~~~~~~~~~~

Command-line interface for plyra-guard.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="plyra-guard",
        description="plyra-guard — Action safety middleware for agentic AI",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the HTTP sidecar server")
    serve_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to guard_config.yaml",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port number (default: 8080)",
    )

    # version command
    subparsers.add_parser("version", help="Show version")

    # explain command
    explain_parser = subparsers.add_parser(
        "explain", help="Explain how the pipeline would evaluate an action"
    )
    explain_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to guard_config.yaml",
    )
    explain_parser.add_argument(
        "--action",
        type=str,
        required=True,
        help="Action type (e.g. file.delete)",
    )
    explain_parser.add_argument(
        "--agent",
        type=str,
        default="default",
        help="Agent ID (default: default)",
    )
    explain_parser.add_argument(
        "--params",
        type=str,
        default="{}",
        help='JSON parameters (e.g. \'{"path": "/etc/hosts"}\')',
    )
    explain_parser.add_argument(
        "--cost",
        type=float,
        default=0.0,
        help="Estimated cost (default: 0.0)",
    )

    # test-policy command
    test_policy_parser = subparsers.add_parser(
        "test-policy", help="Test a policy condition against sample input"
    )
    test_policy_parser.add_argument(
        "--condition",
        type=str,
        required=True,
        help="Condition expression (e.g. \"parameters.path.startswith('/etc')\")",
    )
    test_policy_parser.add_argument(
        "--action-type",
        type=str,
        default="*",
        help="Action type to test (default: *)",
    )
    test_policy_parser.add_argument(
        "--params",
        type=str,
        default="{}",
        help='JSON parameters (e.g. \'{"path": "/etc/hosts"}\')',
    )
    test_policy_parser.add_argument(
        "--verdict",
        type=str,
        default="BLOCK",
        help="Policy verdict (default: BLOCK)",
    )
    test_policy_parser.add_argument(
        "--agent",
        type=str,
        default="default",
        help="Agent ID (default: default)",
    )

    # inspect command
    inspect_parser = subparsers.add_parser(
        "inspect", help="Visualize the evaluation pipeline"
    )
    inspect_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to guard_config.yaml",
    )

    args = parser.parse_args()

    if args.version:
        from plyra_guard import __version__

        print(f"plyra-guard {__version__} (Plyra Agentic Infrastructure)")
        return

    if args.command == "serve":
        _run_serve(args)
    elif args.command == "version":
        from plyra_guard import __version__

        print(f"plyra-guard {__version__} (Plyra Agentic Infrastructure)")
    elif args.command == "explain":
        _run_explain(args)
    elif args.command == "test-policy":
        _run_test_policy(args)
    elif args.command == "inspect":
        _run_inspect(args)
    else:
        parser.print_help()
        sys.exit(1)


def _make_guard(config_path: str | None) -> Any:
    """Create an ActionGuard instance from config or defaults."""
    from plyra_guard.core.guard import ActionGuard

    if config_path:
        return ActionGuard.from_config(config_path)
    return ActionGuard.default()


def _run_serve(args: argparse.Namespace) -> None:
    """Start the HTTP sidecar server."""
    guard = _make_guard(args.config)
    print(f"Starting plyra-guard sidecar on {args.host}:{args.port}")
    guard.serve(host=args.host, port=args.port)


def _run_explain(args: argparse.Namespace) -> None:
    """Run the explain command."""
    from plyra_guard.core.intent import ActionIntent

    guard = _make_guard(args.config)

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in --params: {exc}", file=sys.stderr)
        sys.exit(1)

    intent = ActionIntent(
        action_type=args.action,
        tool_name=args.action,
        parameters=params,
        agent_id=args.agent,
        estimated_cost=args.cost,
    )

    output = guard.explain(intent)
    print(output)


def _run_test_policy(args: argparse.Namespace) -> None:
    """Run the test-policy command."""
    from plyra_guard.core.intent import ActionIntent

    guard = _make_guard(None)

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in --params: {exc}", file=sys.stderr)
        sys.exit(1)

    yaml_snippet = f"""
- name: "cli_test_policy"
  action_types: ["{args.action_type}"]
  condition: "{args.condition}"
  verdict: "{args.verdict}"
"""

    intent = ActionIntent(
        action_type=args.action_type if args.action_type != "*" else "test.action",
        tool_name="cli_test",
        parameters=params,
        agent_id=args.agent,
    )

    result = guard.test_policy(yaml_snippet, intent)

    print(f"Matched:    {result.matched}")
    print(f"Verdict:    {result.verdict.value}")
    print(f"Time:       {result.evaluation_time_ms:.2f}ms")
    print()
    if result.parse_error:
        print(f"Parse Error: {result.parse_error}")
    print(f"Summary:    {result.summary}")
    print()
    if result.condition_trace:
        print("Condition Trace:")
        for step in result.condition_trace:
            sym = "✅" if step.result else "❌"
            print(f"  {sym} {step.expression} → {step.value}")


def _run_inspect(args: argparse.Namespace) -> None:
    """Run the inspect command."""
    guard = _make_guard(args.config)
    print(guard.visualize_pipeline())


if __name__ == "__main__":
    main()
