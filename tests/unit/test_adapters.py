"""Tests for adapter detection and wrapping."""

from plyra_guard.adapters.anthropic_adapter import AnthropicAdapter
from plyra_guard.adapters.generic_adapter import GenericAdapter
from plyra_guard.adapters.openai_adapter import OpenAIAdapter
from plyra_guard.adapters.registry import AdapterRegistry


class TestAdapterRegistry:
    """Tests for the adapter registry."""

    def test_detects_openai_tool(self):
        registry = AdapterRegistry()
        tool = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                },
            },
        }
        adapter = registry.get_adapter(tool)
        assert isinstance(adapter, OpenAIAdapter)

    def test_detects_anthropic_tool(self):
        registry = AdapterRegistry()
        tool = {
            "name": "search",
            "description": "Search the web",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        }
        adapter = registry.get_adapter(tool)
        assert isinstance(adapter, AnthropicAdapter)

    def test_falls_back_to_generic(self):
        registry = AdapterRegistry()

        def my_func(x: int) -> int:
            return x * 2

        adapter = registry.get_adapter(my_func)
        assert isinstance(adapter, GenericAdapter)

    def test_openai_to_intent(self):
        adapter = OpenAIAdapter()
        tool = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {},
            },
        }
        intent = adapter.to_intent(
            tool,
            {"location": "NYC"},
            agent_id="agent-1",
        )
        assert intent.action_type == "openai.get_weather"
        assert intent.tool_name == "get_weather"
        assert intent.parameters["location"] == "NYC"

    def test_anthropic_to_intent(self):
        adapter = AnthropicAdapter()
        tool = {
            "name": "search",
            "description": "Search",
            "input_schema": {},
        }
        intent = adapter.to_intent(
            tool,
            {"query": "python"},
            agent_id="agent-1",
        )
        assert intent.action_type == "anthropic.search"

    def test_generic_wraps_callable(self):
        adapter = GenericAdapter()

        def add(a: int, b: int) -> int:
            return a + b

        assert adapter.can_handle(add) is True

    def test_registry_custom_adapter(self):
        registry = AdapterRegistry()

        class CustomAdapter(GenericAdapter):
            @property
            def framework_name(self) -> str:
                return "custom"

            def can_handle(self, tool):
                return hasattr(tool, "_custom_marker")

        registry.register(CustomAdapter())
        # Custom adapter should be checked before generic
        assert len(registry._adapters) > 7
