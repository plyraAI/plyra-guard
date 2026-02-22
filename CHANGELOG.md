# Changelog

All notable changes to ActionGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2024-01-01

### Added
- Initial release of ActionGuard
- Core evaluation pipeline with 6 built-in evaluators
- Policy engine with AST-compiled YAML conditions
- Dynamic risk scoring (0.0-1.0) with 5 weighted signals
- Per-agent and per-tool rate limiting
- Cost estimation and budget enforcement
- Human-in-the-loop approval gate
- Multi-agent trust ledger with delegation tracking
- Cascade controller (depth limits, cycle detection)
- Global budget manager with gaming detection
- Rollback system with file, DB, and HTTP handlers
- Framework adapters for LangChain, LlamaIndex, CrewAI, AutoGen, OpenAI, Anthropic
- Generic adapter for any Python callable
- Structured audit logging with exporters (stdout, OTel, Datadog, webhook)
- HTTP sidecar server (FastAPI) for language-agnostic access
- CLI with `actionguard serve` command
- YAML configuration with Pydantic validation
- Comprehensive test suite (unit + integration)
- Example scripts for all major use cases
- Full documentation
