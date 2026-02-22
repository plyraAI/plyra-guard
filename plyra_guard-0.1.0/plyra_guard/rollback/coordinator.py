"""
Rollback Coordinator
~~~~~~~~~~~~~~~~~~~~

Orchestrates multi-action and multi-agent rollback operations,
executing handlers in reverse chronological order.
"""

from __future__ import annotations

import logging

from plyra_guard.core.intent import AuditEntry, RollbackReport
from plyra_guard.exceptions import SnapshotNotFoundError
from plyra_guard.rollback.registry import RollbackRegistry
from plyra_guard.rollback.snapshot_manager import SnapshotManager

__all__ = ["RollbackCoordinator"]

logger = logging.getLogger(__name__)


class RollbackCoordinator:
    """
    Coordinates rollback operations across actions and agents.

    Handles:
    - Single action rollback by action_id
    - Batch rollback of last N actions
    - Task-level rollback across all agents
    """

    def __init__(
        self,
        registry: RollbackRegistry,
        snapshot_manager: SnapshotManager,
    ) -> None:
        self._registry = registry
        self._snapshot_manager = snapshot_manager
        # Track action_ids by agent and task for cross-agent rollback
        self._action_log: list[AuditEntry] = []

    def record_action(self, entry: AuditEntry) -> None:
        """Record an executed action for potential future rollback."""
        self._action_log.append(entry)

    def rollback_action(self, action_id: str) -> bool:
        """
        Roll back a single action by ID.

        Args:
            action_id: The action to roll back.

        Returns:
            True if rollback succeeded, False otherwise.
        """
        try:
            snapshot = self._snapshot_manager.get(action_id)
        except SnapshotNotFoundError:
            logger.warning("No snapshot found for action %s", action_id)
            return False

        if snapshot is None:
            logger.warning("No snapshot found for action %s", action_id)
            return False

        if not self._registry.has_handler(snapshot.action_type):
            logger.warning(
                "No rollback handler for action type %s",
                snapshot.action_type,
            )
            return False

        handler = self._registry.get_handler(snapshot.action_type)
        try:
            success = handler.restore(snapshot)
            if success:
                self._snapshot_manager.remove(action_id)
                logger.info("Rolled back action %s", action_id)
            else:
                logger.error("Rollback failed for action %s", action_id)
            return success
        except Exception as exc:
            logger.error("Rollback error for action %s: %s", action_id, exc)
            return False

    def rollback_last(
        self,
        n: int = 1,
        agent_id: str | None = None,
    ) -> list[bool]:
        """
        Roll back the last N actions, optionally filtered by agent.

        Args:
            n: Number of recent actions to roll back.
            agent_id: Filter to a specific agent's actions.

        Returns:
            List of boolean results for each rollback attempt.
        """
        entries = list(reversed(self._action_log))
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]

        entries = entries[:n]
        results: list[bool] = []

        for entry in entries:
            success = self.rollback_action(entry.action_id)
            results.append(success)
            if success:
                entry.rolled_back = True

        return results

    def rollback_task(self, task_id: str) -> RollbackReport:
        """
        Roll back all actions for a given task across all agents.

        Actions are rolled back in reverse chronological order.

        Args:
            task_id: The task whose actions to roll back.

        Returns:
            A RollbackReport summarizing the results.
        """
        report = RollbackReport(task_id=task_id)

        # Collect all actions for this task, sorted by timestamp desc
        task_entries = [e for e in self._action_log if e.task_id == task_id]
        task_entries.sort(key=lambda e: e.timestamp, reverse=True)

        report.total_actions = len(task_entries)

        for entry in task_entries:
            if entry.rolled_back:
                report.skipped.append(entry.action_id)
                continue

            if not self._registry.has_handler(entry.action_type):
                report.skipped.append(entry.action_id)
                continue

            success = self.rollback_action(entry.action_id)
            if success:
                report.rolled_back.append(entry.action_id)
                entry.rolled_back = True
            else:
                report.failed.append(entry.action_id)

        return report

    def clear_log(self) -> None:
        """Clear the action log."""
        self._action_log.clear()
