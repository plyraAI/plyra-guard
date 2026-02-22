"""
ActionGuard — Main Guard Class
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The primary entry point for ActionGuard. Assembles the full pipeline
and exposes the public API for protecting, evaluating, and rolling
back agent actions.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from plyra_guard.adapters.registry import AdapterRegistry
from plyra_guard.config.defaults import DEFAULT_CONFIG
from plyra_guard.config.loader import load_config, load_config_from_dict
from plyra_guard.config.schema import GuardConfig
from plyra_guard.core.execution_gate import ExecutionGate
from plyra_guard.core.intent import (
    ActionIntent,
    ActionResult,
    AuditEntry,
    AuditFilter,
    EvaluatorResult,
    GuardMetrics,
    RollbackReport,
)
from plyra_guard.core.interceptor import Interceptor
from plyra_guard.core.verdict import RiskLevel, TrustLevel, Verdict
from plyra_guard.evaluators.base import BaseEvaluator
from plyra_guard.evaluators.cost_estimator import CostEstimator
from plyra_guard.evaluators.human_gate import HumanGate
from plyra_guard.evaluators.policy_engine import PolicyEngine
from plyra_guard.evaluators.rate_limiter import RateLimiter
from plyra_guard.evaluators.risk_scorer import RiskScorer
from plyra_guard.evaluators.schema_validator import SchemaValidator
from plyra_guard.exceptions import ExecutionBlockedError
from plyra_guard.multiagent.cascade_controller import CascadeController
from plyra_guard.multiagent.global_budgeter import GlobalBudgetManager
from plyra_guard.multiagent.trust_ledger import TrustLedger
from plyra_guard.observability.audit_log import AuditLog
from plyra_guard.observability.exporters.stdout_exporter import StdoutExporter
from plyra_guard.observability.metrics import MetricsCollector
from plyra_guard.rollback.coordinator import RollbackCoordinator
from plyra_guard.rollback.handlers.db_handler import DbRollbackHandler
from plyra_guard.rollback.handlers.file_handler import FileRollbackHandler
from plyra_guard.rollback.handlers.http_handler import HttpRollbackHandler
from plyra_guard.rollback.registry import RollbackRegistry
from plyra_guard.rollback.snapshot_manager import SnapshotManager

__all__ = ["ActionGuard", "EvaluationPipeline"]

logger = logging.getLogger(__name__)


class EvaluationPipeline:
    """
    Ordered pipeline of evaluators.

    Runs each enabled evaluator in priority order. A BLOCK verdict
    short-circuits the remaining evaluators.
    """

    def __init__(self) -> None:
        self._evaluators: list[BaseEvaluator] = []

    def add(
        self,
        evaluator: BaseEvaluator,
        position: str | int | None = None,
    ) -> None:
        """
        Add an evaluator to the pipeline.

        Args:
            evaluator: The evaluator to add.
            position: Insert position. Can be an integer index, or a
                string like "after_risk_scorer" to insert relative to
                another evaluator. If None, appends at the end.
        """
        if isinstance(position, int):
            self._evaluators.insert(position, evaluator)
        elif isinstance(position, str) and position.startswith("after_"):
            target_name = position[6:]  # strip "after_"
            for i, ev in enumerate(self._evaluators):
                if ev.name == target_name:
                    self._evaluators.insert(i + 1, evaluator)
                    return
            self._evaluators.append(evaluator)
        elif isinstance(position, str) and position.startswith("before_"):
            target_name = position[7:]
            for i, ev in enumerate(self._evaluators):
                if ev.name == target_name:
                    self._evaluators.insert(i, evaluator)
                    return
            self._evaluators.append(evaluator)
        else:
            self._evaluators.append(evaluator)

        # Re-sort by priority
        self._evaluators.sort(key=lambda e: e.priority)

    def remove(self, evaluator_name: str) -> None:
        """Remove an evaluator by name."""
        self._evaluators = [e for e in self._evaluators if e.name != evaluator_name]

    def evaluate(self, intent: ActionIntent) -> list[EvaluatorResult]:
        """
        Run all enabled evaluators on the intent.

        Short-circuits on BLOCK verdict.

        Returns:
            List of EvaluatorResults from all evaluators that ran.
        """
        results: list[EvaluatorResult] = []

        for evaluator in self._evaluators:
            if not evaluator.enabled:
                continue

            result = evaluator.evaluate(intent)
            results.append(result)

            if result.verdict == Verdict.BLOCK:
                logger.info(
                    "Action %s BLOCKED by %s: %s",
                    intent.action_id,
                    evaluator.name,
                    result.reason,
                )
                break

        return results

    @property
    def evaluators(self) -> list[BaseEvaluator]:
        """Return the ordered list of evaluators."""
        return list(self._evaluators)


class ActionGuard:
    """
    Main ActionGuard class — entry point for all protection operations.

    Provides a decorator-based API, tool wrapping, evaluation,
    rollback, multi-agent support, and observability.
    """

    def __init__(self, config: GuardConfig | None = None) -> None:
        self._config = config or GuardConfig()
        self._default_agent_id = "default"

        # ── Subsystems ────────────────────────────────────────────
        self.pipeline = EvaluationPipeline()
        self._audit_log = AuditLog(
            max_entries=self._config.observability.audit_log_max_entries
        )
        self._metrics = MetricsCollector()
        self._trust_ledger = TrustLedger(block_unknown=False)
        self._cascade_controller = CascadeController(
            max_delegation_depth=self._config.global_config.max_delegation_depth,
            max_concurrent_delegations=self._config.global_config.max_concurrent_delegations,
        )
        self._global_budgeter = GlobalBudgetManager(
            per_task_budget=self._config.budget.per_task,
            per_agent_per_run=self._config.budget.per_agent_per_run,
            currency=self._config.budget.currency,
        )
        self._rollback_registry = RollbackRegistry()
        self._snapshot_manager = SnapshotManager(
            registry=self._rollback_registry,
            max_in_memory=self._config.rollback.max_snapshots,
            storage_dir=self._config.rollback.snapshot_dir,
        )
        self._rollback_coordinator = RollbackCoordinator(
            registry=self._rollback_registry,
            snapshot_manager=self._snapshot_manager,
        )
        self._execution_gate = ExecutionGate()
        self._adapter_registry = AdapterRegistry()

        # ── Initialize ────────────────────────────────────────────
        self._setup_evaluators()
        self._setup_rollback_handlers()
        self._setup_exporters()
        self._load_agents_from_config()
        self._load_policies_from_config()

    # ── Properties ─────────────────────────────────────────────────

    @property
    def version(self) -> str:
        """Return the ActionGuard version string."""
        from plyra_guard import __version__

        return __version__

    # ── Class Methods (constructors) ──────────────────────────────

    @classmethod
    def from_config(cls, path: str) -> ActionGuard:
        """
        Create an ActionGuard instance from a YAML config file.

        Args:
            path: Path to guard_config.yaml.

        Returns:
            Configured ActionGuard instance.
        """
        config = load_config(path)
        return cls(config=config)

    @classmethod
    def default(cls) -> ActionGuard:
        """
        Create an ActionGuard instance with sensible defaults.

        No config file needed — good for quick starts and testing.
        """
        config = load_config_from_dict(DEFAULT_CONFIG)
        return cls(config=config)

    # ── Setup Methods ─────────────────────────────────────────────

    def _setup_evaluators(self) -> None:
        """Initialize the default evaluation pipeline."""
        ev_cfg = self._config.evaluators

        schema = SchemaValidator()
        if ev_cfg.schema_validator.enabled:
            self.pipeline.add(schema)

        policy = PolicyEngine()
        if ev_cfg.policy_engine.enabled:
            self.pipeline.add(policy)
            self._policy_engine = policy

        risk = RiskScorer(max_risk_score=self._config.global_config.max_risk_score)
        if ev_cfg.risk_scorer.enabled:
            self.pipeline.add(risk)
            self._risk_scorer = risk

        rate = RateLimiter(
            default_limit=self._config.rate_limits.default,
            per_tool_limits=self._config.rate_limits.per_tool or None,
        )
        if ev_cfg.rate_limiter.enabled:
            self.pipeline.add(rate)

        cost = CostEstimator(
            per_task_budget=self._config.budget.per_task,
            per_agent_budget=self._config.budget.per_agent_per_run,
            currency=self._config.budget.currency,
        )
        if ev_cfg.cost_estimator.enabled:
            self.pipeline.add(cost)
            self._cost_estimator = cost

        human = HumanGate(enabled=ev_cfg.human_gate.enabled)
        self.pipeline.add(human)

    def _setup_rollback_handlers(self) -> None:
        """Register built-in rollback handlers."""
        if self._config.rollback.enabled:
            self._rollback_registry.register(FileRollbackHandler())
            self._rollback_registry.register(DbRollbackHandler())
            self._rollback_registry.register(HttpRollbackHandler())

    def _setup_exporters(self) -> None:
        """Configure audit log exporters from config."""
        for exporter_name in self._config.observability.exporters:
            if exporter_name == "stdout":
                self._audit_log.add_exporter(StdoutExporter())

    def _load_agents_from_config(self) -> None:
        """Register agents from configuration."""
        for agent_cfg in self._config.agents:
            # Map trust_level float to TrustLevel enum
            if agent_cfg.trust_level >= 0.9:
                tl = TrustLevel.HUMAN
            elif agent_cfg.trust_level >= 0.7:
                tl = TrustLevel.ORCHESTRATOR
            elif agent_cfg.trust_level >= 0.4:
                tl = TrustLevel.PEER
            elif agent_cfg.trust_level > 0.0:
                tl = TrustLevel.SUB_AGENT
            else:
                tl = TrustLevel.UNKNOWN

            self._trust_ledger.register(
                agent_id=agent_cfg.id,
                trust_level=tl,
                can_delegate_to=agent_cfg.can_delegate_to,
                max_actions_per_run=agent_cfg.max_actions_per_run,
            )

    def _load_policies_from_config(self) -> None:
        """Load policies from configuration into the policy engine."""
        if hasattr(self, "_policy_engine") and self._config.policies:
            self._policy_engine.load_policies(
                [p.model_dump() for p in self._config.policies]
            )

    # ── Primary API: Decorator ────────────────────────────────────

    def protect(
        self,
        action_type: str,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        rollback: bool = True,
        tags: list[str] | None = None,
    ) -> Callable[..., Any]:
        """
        Decorator to protect a function with ActionGuard.

        Args:
            action_type: Hierarchical action type (e.g. "file.delete").
            risk_level: Baseline risk level for this action.
            rollback: Whether to enable rollback for this action.
            tags: Optional tags for categorization.

        Returns:
            Decorator function.

        Example::

            @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
            def delete_file(path: str) -> bool:
                os.remove(path)
                return True
        """
        guard = self

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                interceptor = Interceptor(
                    action_type=action_type,
                    risk_level=risk_level,
                    agent_id=guard._default_agent_id,
                    tags=tags or [],
                )
                intent = interceptor.create_intent(func, args, kwargs)

                return guard._run_pipeline(
                    intent=intent,
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    enable_rollback=rollback,
                )

            wrapper._plyra_guard_protected = True  # type: ignore
            return wrapper

        return decorator

    # ── Primary API: Wrap Tools ───────────────────────────────────

    def wrap(self, tools: list[Any]) -> list[Any]:
        """
        Wrap framework-native tools with ActionGuard protection.

        Auto-detects the framework and routes to the right adapter.

        Args:
            tools: List of framework-native tool objects.

        Returns:
            List of wrapped tools in their native format.
        """
        return self._adapter_registry.wrap_tools(tools, self)

    # ── Primary API: Evaluate (dry-run) ───────────────────────────

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """
        Evaluate an ActionIntent without executing (dry-run).

        Args:
            intent: The action to evaluate.

        Returns:
            The final EvaluatorResult (worst verdict wins).
        """
        results = self.pipeline.evaluate(intent)
        return self._worst_verdict(results)

    async def evaluate_async(self, intent: ActionIntent) -> EvaluatorResult:
        """
        Async version of evaluate(). Runs the full evaluation
        pipeline without executing the action.

        Use this in async agent contexts to avoid blocking
        the event loop during pipeline evaluation.

        Args:
            intent: The ActionIntent to evaluate.

        Returns:
            EvaluatorResult with verdict and full reasoning.

        Example::

            result = await guard.evaluate_async(intent)
            if result.verdict == Verdict.ALLOW:
                # proceed with execution
        """
        import asyncio

        return await asyncio.to_thread(self.evaluate, intent)

    # ── Primary API: Rollback ─────────────────────────────────────

    def rollback(self, action_id: str) -> bool:
        """
        Roll back a single action by ID.

        Args:
            action_id: The action to roll back.

        Returns:
            True if rollback succeeded.
        """
        success = self._rollback_coordinator.rollback_action(action_id)
        if success:
            self._metrics.increment("rollbacks")
        else:
            self._metrics.increment("rollback_failures")
        return success

    def rollback_last(self, n: int = 1, agent_id: str | None = None) -> list[bool]:
        """
        Roll back the last N actions.

        Args:
            n: Number of actions to roll back.
            agent_id: Optionally filter to one agent.

        Returns:
            List of rollback results.
        """
        return self._rollback_coordinator.rollback_last(n, agent_id)

    def rollback_task(self, task_id: str) -> RollbackReport:
        """
        Roll back all actions for a task across all agents.

        Args:
            task_id: The task to roll back.

        Returns:
            RollbackReport with per-action results.
        """
        return self._rollback_coordinator.rollback_task(task_id)

    # ── Primary API: Multi-agent ──────────────────────────────────

    def register_agent(self, agent_id: str, trust_level: TrustLevel) -> None:
        """
        Register an agent with a trust level.

        Args:
            agent_id: Unique agent identifier.
            trust_level: Trust classification.
        """
        self._trust_ledger.register(agent_id=agent_id, trust_level=trust_level)

    @contextmanager
    def set_task_context(self, task_id: str, agent_id: str) -> Iterator[None]:
        """
        Context manager to set the active task and agent.

        Args:
            task_id: The task identifier.
            agent_id: The agent identifier.

        Yields:
            None — the context is set for the duration of the block.
        """
        previous_agent = self._default_agent_id
        self._default_agent_id = agent_id
        try:
            yield
        finally:
            self._default_agent_id = previous_agent

    # ── Primary API: Observability ────────────────────────────────

    def add_exporter(self, exporter: Any) -> None:
        """
        Add an audit log exporter.

        Args:
            exporter: An exporter implementing export(AuditEntry).
        """
        self._audit_log.add_exporter(exporter)

    def get_audit_log(self, filters: AuditFilter | None = None) -> list[AuditEntry]:
        """
        Query the audit log.

        Args:
            filters: Optional filter criteria.

        Returns:
            Matching audit entries.
        """
        return self._audit_log.query(filters)

    def get_metrics(self) -> GuardMetrics:
        """
        Get current metrics snapshot.

        Returns:
            GuardMetrics with aggregate statistics.
        """
        return self._audit_log.get_metrics()

    # ── Primary API: Sidecar ──────────────────────────────────────

    def serve(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """
        Start the HTTP sidecar server.

        Args:
            host: Bind address.
            port: Port number.
        """
        try:
            import uvicorn

            from plyra_guard.sidecar.server import create_app

            app = create_app(self)
            uvicorn.run(app, host=host, port=port)
        except ImportError:
            raise ImportError(
                "Sidecar requires FastAPI and uvicorn. "
                "Install with: pip install plyra_guard[sidecar]"
            )

    # ── Rollback Handler Registration ─────────────────────────────

    def rollback_handler(self, action_type: str) -> Callable[..., Any]:
        """
        Decorator to register a custom rollback handler.

        Args:
            action_type: The action type to handle.

        Returns:
            Class decorator.

        Example::

            @guard.rollback_handler("myapp.create_user")
            class CreateUserHandler(BaseRollbackHandler):
                ...
        """

        def decorator(cls: Any) -> Any:
            handler = cls()
            self._rollback_registry.register_for_type(action_type, handler)
            return cls

        return decorator

    # ── Developer Experience Methods ──────────────────────────────

    def explain(self, intent: ActionIntent) -> str:
        """
        Run the full evaluation pipeline in dry-run mode and return
        a rich, human-readable explanation string.

        This never executes the action.

        Args:
            intent: The action to explain.

        Returns:
            Human-readable explanation string.
        """
        from plyra_guard.core.dx import explain_intent

        return explain_intent(self, intent)

    async def explain_async(self, intent: ActionIntent) -> str:
        """
        Async version of explain().

        Args:
            intent: The action to explain.

        Returns:
            Human-readable explanation string.
        """
        from plyra_guard.core.dx import explain_intent_async

        return await explain_intent_async(self, intent)

    def test_policy(
        self,
        yaml_snippet: str,
        sample_intent: ActionIntent,
    ) -> Any:
        """
        Test a YAML policy snippet against a sample intent
        without modifying the guard's config.

        Args:
            yaml_snippet: YAML string defining a policy rule.
            sample_intent: An ActionIntent to test against.

        Returns:
            PolicyTestResult with match status, verdict,
            condition trace, and summary.
        """
        from plyra_guard.core.dx import test_policy_snippet

        return test_policy_snippet(self, yaml_snippet, sample_intent)

    def visualize_pipeline(self) -> str:
        """
        Return an ASCII diagram of the current evaluation pipeline
        with configuration summary.

        Returns:
            Multi-line string with the pipeline visualization.
        """
        from plyra_guard.core.dx import visualize_pipeline

        return visualize_pipeline(self)

    def __str__(self) -> str:
        return self.visualize_pipeline()

    def __repr__(self) -> str:
        return self.visualize_pipeline()

    def _run_pipeline(
        self,
        intent: ActionIntent,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        enable_rollback: bool = True,
    ) -> Any:
        """
        Full pipeline: evaluate → snapshot → execute → audit.

        Returns the function's return value, or raises
        ExecutionBlockedError.
        """
        # Inject agent metadata
        if self._trust_ledger.is_registered(intent.agent_id):
            profile = self._trust_ledger.get(intent.agent_id)
            intent.metadata["agent_error_rate"] = profile.error_rate
            intent.metadata["agent_violations"] = profile.violation_count
            intent.metadata["agent_action_count"] = profile.action_count

        # Check cascade limits
        cascade_result = self._cascade_controller.check(intent)
        if cascade_result and cascade_result.verdict == Verdict.BLOCK:
            self._record_blocked(intent, cascade_result)
            raise ExecutionBlockedError(
                message=cascade_result.reason,
                verdict=cascade_result.verdict.value,
                reason=cascade_result.reason,
            )

        # Check global budget
        budget_result = self._global_budgeter.check(intent)
        if budget_result and budget_result.verdict == Verdict.BLOCK:
            self._record_blocked(intent, budget_result)
            raise ExecutionBlockedError(
                message=budget_result.reason,
                verdict=budget_result.verdict.value,
                reason=budget_result.reason,
            )

        # Run evaluation pipeline
        eval_results = self.pipeline.evaluate(intent)
        final = self._worst_verdict(eval_results)

        # Extract risk score from evaluator results
        risk_score = 0.0
        policy_triggered = None
        for er in eval_results:
            if "risk_score" in er.metadata:
                risk_score = er.metadata["risk_score"]
            if "policy_name" in er.metadata:
                policy_triggered = er.metadata["policy_name"]

        # Handle blocking verdicts
        if final.verdict.is_blocking():
            self._record_blocked(
                intent, final, eval_results, risk_score, policy_triggered
            )
            raise ExecutionBlockedError(
                message=final.reason,
                verdict=final.verdict.value,
                reason=final.reason,
            )

        # Capture snapshot before execution
        if enable_rollback:
            self._snapshot_manager.capture(intent)

        # Execute
        action_result = self._execution_gate.execute(
            intent=intent,
            func=func,
            args=args,
            kwargs=kwargs,
            verdict=final.verdict,
            risk_score=risk_score,
            policy_triggered=policy_triggered,
            evaluator_results=eval_results,
        )

        # Post-execution bookkeeping
        self._post_execution(intent, action_result, risk_score)

        if action_result.error:
            raise action_result.error

        return action_result.output

    def _execute_guarded(
        self,
        intent: ActionIntent,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """
        Internal method used by adapters to execute guarded actions.

        Same as _run_pipeline but called from adapter wrapping.
        """
        return self._run_pipeline(intent=intent, func=func, args=args, kwargs=kwargs)

    def _worst_verdict(self, results: list[EvaluatorResult]) -> EvaluatorResult:
        """Pick the most restrictive verdict from evaluator results."""
        if not results:
            return EvaluatorResult(
                verdict=Verdict.ALLOW,
                reason="No evaluators ran",
                evaluator_name="pipeline",
            )

        # Priority: BLOCK > ESCALATE > DEFER > WARN > ALLOW
        priority = {
            Verdict.BLOCK: 0,
            Verdict.ESCALATE: 1,
            Verdict.DEFER: 2,
            Verdict.WARN: 3,
            Verdict.ALLOW: 4,
        }

        return min(results, key=lambda r: priority.get(r.verdict, 5))

    def _record_blocked(
        self,
        intent: ActionIntent,
        result: EvaluatorResult,
        eval_results: list[EvaluatorResult] | None = None,
        risk_score: float = 0.0,
        policy_triggered: str | None = None,
    ) -> None:
        """Record a blocked action in the audit log."""
        audit = AuditEntry(
            action_id=intent.action_id,
            agent_id=intent.agent_id,
            action_type=intent.action_type,
            verdict=result.verdict,
            risk_score=risk_score,
            task_id=intent.task_id,
            policy_triggered=policy_triggered or result.metadata.get("policy_name"),
            evaluator_results=eval_results or [result],
            instruction_chain=intent.instruction_chain,
            parameters=intent.parameters,
            timestamp=intent.timestamp,
        )
        self._audit_log.write(audit)
        self._metrics.increment("total_actions")
        self._metrics.increment("blocked_actions")

        # Record trust violation
        if self._trust_ledger.is_registered(intent.agent_id):
            self._trust_ledger.record_violation(intent.agent_id)

    def _post_execution(
        self,
        intent: ActionIntent,
        result: ActionResult,
        risk_score: float,
    ) -> None:
        """Post-execution bookkeeping: audit, metrics, budget."""
        if result.audit_entry:
            self._audit_log.write(result.audit_entry)
            self._rollback_coordinator.record_action(result.audit_entry)

        # Update metrics
        self._metrics.increment("total_actions")
        verdict_key = (
            result.audit_entry.verdict.value.lower() + "_actions"
            if result.audit_entry
            else "allowed_actions"
        )
        self._metrics.increment(verdict_key)
        self._metrics.record_risk(risk_score)
        self._metrics.record_duration(result.duration_ms)

        # Record cost
        if intent.estimated_cost > 0:
            self._metrics.add_cost(intent.estimated_cost)
            self._global_budgeter.record_cost(
                intent.agent_id, intent.task_id, intent.estimated_cost
            )
            if hasattr(self, "_cost_estimator"):
                self._cost_estimator.record_cost(
                    intent.agent_id, intent.task_id, intent.estimated_cost
                )

        # Update trust ledger
        if self._trust_ledger.is_registered(intent.agent_id):
            self._trust_ledger.record_action(intent.agent_id, result.success)
