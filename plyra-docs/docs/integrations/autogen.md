# AutoGen Integration

Plyra Guard integrates with AutoGen via `guard.wrap()` on functions registered with `UserProxyAgent`.

## Basic Usage

```python
import autogen
from plyra_guard import ActionGuard

guard = ActionGuard()

# Define tools
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

def delete_file(path: str) -> str:
    import os
    os.remove(path)
    return f"Deleted {path}"

# Wrap with guard
safe_tools = guard.wrap([read_file, delete_file])

# Register with AutoGen agent
user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=10,
)

for tool in safe_tools:
    user_proxy.register_function(
        function_map={tool.__name__: tool}
    )
```

## What Happens on a Block

When a blocked tool is called, Plyra Guard returns an error string (not an exception) into the AutoGen conversation history. This means:

- The conversation continues
- The assistant sees the error and can try a different approach
- No crash, no infinite loop from uncaught exceptions

Example conversation log:

```
user_proxy → assistant: Please clean up /etc/passwd
assistant → user_proxy: [calls delete_file("/etc/passwd")]
user_proxy → assistant: [BLOCKED] System config is off-limits (rule: protect-system)
assistant → user_proxy: I can't delete that file due to policy restrictions. 
                         Is there a different file you'd like me to remove?
```

## With a Custom Policy

```python
from plyra_guard import Policy, Rule

policy = Policy(rules=[
    Rule(pattern=r"/etc/",  action="block",  reason="System config is off-limits"),
    Rule(pattern=r"rm -rf", action="block",  reason="No recursive deletes"),
    Rule(pattern=r"/tmp/",  action="allow"),
])

guard = ActionGuard(policy=policy)
safe_tools = guard.wrap([read_file, delete_file])
```

## Group Chat

For multi-agent group chats, create one guard and share it:

```python
guard = ActionGuard(policy=policy)

coder_tools = guard.wrap([write_code, run_tests])
ops_tools   = guard.wrap([deploy, restart_service])

coder = autogen.AssistantAgent("coder", ...)
ops   = autogen.AssistantAgent("ops", ...)

user_proxy.register_function(function_map={
    **{t.__name__: t for t in coder_tools},
    **{t.__name__: t for t in ops_tools},
})
```

All actions from both agents are logged in the shared guard history.
