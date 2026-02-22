# Rollback Guide

## Overview

ActionGuard can undo actions by capturing pre-execution state and restoring it on demand.

## How It Works

1. Before execution, the `SnapshotManager` calls the appropriate `RollbackHandler.capture()`
2. The captured `Snapshot` is stored in memory (with disk overflow)
3. If rollback is requested, `RollbackHandler.restore()` undoes the change

## Built-in Handlers

| Handler | Action Types | Strategy |
|---------|-------------|----------|
| `FileRollbackHandler` | `file.delete`, `file.write`, `file.create` | Copy/restore files |
| `DbRollbackHandler` | `db.insert`, `db.update`, `db.delete` | Row-level undo |
| `HttpRollbackHandler` | `http.post`, `http.put`, `http.patch` | Compensation URL |

## Rolling Back

```python
# Single action
guard.rollback(action_id)

# Last N actions
guard.rollback_last(n=3)

# Last N for a specific agent
guard.rollback_last(n=2, agent_id="email-agent")

# All actions for a task (cross-agent)
report = guard.rollback_task("task-001")
```

## Custom Handlers

```python
from actionguard import BaseRollbackHandler, Snapshot, ActionIntent

@guard.rollback_handler("myapp.create_user")
class CreateUserHandler(BaseRollbackHandler):
    @property
    def action_types(self) -> list[str]:
        return ["myapp.create_user"]

    def capture(self, intent: ActionIntent) -> Snapshot:
        user_id = intent.parameters.get("user_id")
        return Snapshot(
            action_id=intent.action_id,
            action_type=intent.action_type,
            state={"user_id": user_id},
        )

    def restore(self, snapshot: Snapshot) -> bool:
        user_id = snapshot.state["user_id"]
        # Delete the created user
        db.delete_user(user_id)
        return True
```
