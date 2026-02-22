# Security Policy — plyra-guard

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

**⚠️ Do NOT open a public GitHub issue for security vulnerabilities.**

Please report security vulnerabilities via email:

📧 **security@plyra.dev**

### Response SLA

| Stage                  | Timeline     |
| ---------------------- | ------------ |
| Acknowledgement        | Within 48 hours |
| Initial assessment     | Within 5 business days |
| Patch for critical     | Within 14 days |
| Patch for non-critical | Within 30 days |

### What Qualifies as a Security Vulnerability

The following are considered security-relevant for ActionGuard:

- **Policy engine bypass** — Any mechanism that allows an action to circumvent a configured policy rule (e.g., crafted condition strings that evaluate incorrectly, action type spoofing).
- **Trust level escalation** — A sub-agent gaining capabilities beyond its assigned trust level, or bypassing the trust ledger to impersonate a higher-trust agent.
- **Audit log tampering** — Any path that allows modification, deletion, or suppression of audit log entries after they have been recorded.
- **Rollback system manipulation** — Exploiting the rollback or snapshot system to restore unauthorized state, delete snapshots, or prevent legitimate rollbacks.
- **Budget or rate limit bypass** — Circumventing per-agent, per-task, or global budget enforcement or rate limiting under any concurrency pattern.
- **Cascade controller evasion** — Bypassing delegation depth limits or concurrent delegation limits in multi-agent chains.

### What Does NOT Qualify

- Bugs that do not have a security impact (use [GitHub Issues](https://github.com/plyra/plyra-guard/issues) instead)
- Feature requests
- Performance issues (unless they enable a denial-of-service attack)

## CVE Process

For confirmed critical vulnerabilities:

1. We will request a CVE identifier through the GitHub Security Advisory process.
2. A patched version will be released before or simultaneously with the public advisory.
3. The advisory will include affected versions, impact assessment, and upgrade instructions.

## Disclosure Policy

We follow **coordinated disclosure**:

1. Reporter notifies us privately.
2. We confirm, assess severity, and develop a patch.
3. We release the patch and publish a security advisory.
4. Reporter is credited (unless they prefer anonymity).

## Security Hall of Fame

We gratefully acknowledge security researchers who help keep plyra-guard safe:

| Reporter | Date | Summary |
| -------- | ---- | ------- |
| *Be the first!* | — | — |

---

Thank you for helping keep plyra-guard and its users secure.
