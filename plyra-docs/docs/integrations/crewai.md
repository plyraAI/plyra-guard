# CrewAI Integration

Plyra Guard wraps CrewAI `@tool` definitions. Blocked actions surface as `ActionGuardExecutionError`, which CrewAI's task loop handles natively.

## Basic Usage

```python
from crewai_tools import tool
from plyra_guard import ActionGuard

guard = ActionGuard()

@tool("Read File")
def read_file(path: str) -> str:
    """Read a file and return its contents."""
    with open(path) as f:
        return f.read()

@tool("Write File")
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)
    return f"Written to {path}"

# Wrap tools
safe_tools = guard.wrap([read_file, write_file])

# Use with CrewAI agents
from crewai import Agent, Task, Crew

analyst = Agent(
    role="Data Analyst",
    goal="Analyse reports and write summaries",
    tools=safe_tools,
    verbose=True,
)
```

## What Happens on a Block

When a blocked tool is called, Plyra Guard raises `ActionGuardExecutionError`. CrewAI's internal task retry logic catches this and surfaces it as a task failure with the block reason included.

The agent's verbose output will show:

```
Action: Write File
Action Input: {"path": "/etc/config", "content": "..."}
Observation: [BLOCKED] System config is off-limits (rule: protect-system)
```

## Custom Policy

```python
from plyra_guard import Policy, Rule

policy = Policy(rules=[
    Rule(pattern=r"^/etc/",    action="block", reason="System config is off-limits"),
    Rule(pattern=r"\.env$",    action="block", reason="No .env access"),
    Rule(pattern=r"^/tmp/",    action="allow"),
    Rule(pattern=r"^/reports/",action="allow"),
])

guard = ActionGuard(policy=policy)
safe_tools = guard.wrap([read_file, write_file])
```

## Multi-Agent Crew

Share one guard across all agents for unified audit logging:

```python
guard = ActionGuard(policy=policy)

researcher_tools = guard.wrap([search_web, read_file])
writer_tools     = guard.wrap([write_file, format_report])

researcher = Agent(role="Researcher", tools=researcher_tools, ...)
writer     = Agent(role="Writer",     tools=writer_tools, ...)

crew = Crew(agents=[researcher, writer], tasks=[...])
crew.kickoff()

# After — see what both agents did
for action in guard.history():
    print(f"{action.agent_hint} | {action.tool_name} | {action.outcome}")
```

## Tips

!!! tip "Tool descriptions matter"
    Plyra Guard uses the tool name + arguments to build the intent string. Clear tool names (e.g. `"Delete File"` not `"df"`) make policy rules easier to write and audit logs easier to read.

!!! tip "Test your policy before running a crew"
    Use `guard.evaluate(intent)` to dry-run your policy against expected tool calls before starting a long crew job.
