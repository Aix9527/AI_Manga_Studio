---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_209d611186a911f18766525400f8a581
    ReservedCode1: tRzshCJB4jGatalOAC7UoYM7DyLn2sPPuBYEZKtZcY2iRWIbX4qwgqsmmjpH6oy/dUloCJNRaIMwrWc6AHInJVg8s5UGoC86qPiQWimTAA1OVtXTMjTLnlGOR+2F/q2C9bGNplYBIxk3d4C/dyEtlPI1NNL7aOmkiUeiw3UK643Eaok9+F4akklXumA=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_209d611186a911f18766525400f8a581
    ReservedCode2: tRzshCJB4jGatalOAC7UoYM7DyLn2sPPuBYEZKtZcY2iRWIbX4qwgqsmmjpH6oy/dUloCJNRaIMwrWc6AHInJVg8s5UGoC86qPiQWimTAA1OVtXTMjTLnlGOR+2F/q2C9bGNplYBIxk3d4C/dyEtlPI1NNL7aOmkiUeiw3UK643Eaok9+F4akklXumA=
---

# Security Policy

## Supported Versions

AI_Manga_Studio is currently in early development (alpha stage). Security updates will be provided for the latest release only.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability within AI_Manga_Studio, please follow these steps:

1. **Do NOT open a public issue.** Public disclosure could put users at risk.
2. Send a detailed report to the project maintainers via GitHub's [Security Advisories](https://github.com/YOUR_USERNAME/AI_Manga_Studio/security/advisories) feature.
3. Include the following in your report:
   - A clear description of the vulnerability
   - Steps to reproduce
   - Affected versions
   - Potential impact
   - Suggested fixes (if available)

## Response Timeline

- **Acknowledgment**: Within 48 hours of submission
- **Status Update**: Within 5 business days
- **Resolution**: We aim to release patches within 30 days, depending on severity

## Security Considerations for AI_Manga_Studio

### API Keys & Credentials

- Never commit API keys, tokens, or credentials to the repository
- Use environment variables (`.env` file or system environment) for all secrets
- The `.env` file is listed in `.gitignore` and should never be committed

### ComfyUI Integration

- When connecting to local ComfyUI instances, ensure the API endpoint is not exposed to the public internet
- Use `127.0.0.1` binding for local-only access
- Consider using ComfyUI's built-in authentication if exposing to a network

### Plugin System

- Third-party plugins run with the same privileges as the main application
- Only install plugins from trusted sources
- Review plugin code before installation when possible

### Model Files

- Downloaded model weights may contain malicious pickles; use safe loading mechanisms
- Verify checksums when available
- Do not download models from untrusted sources

## Scope

This security policy applies to:

- The AI_Manga_Studio core codebase
- Official plugins and SDK
- Documentation and configuration defaults

This policy does NOT cover:

- User-generated content (novels, prompts, outputs)
- Third-party plugins and integrations
- External AI model providers (OpenAI, ComfyUI, Ollama, etc.)

## Disclosure Policy

- We follow a 90-day coordinated disclosure policy
- Credit will be given to security researchers who responsibly disclose vulnerabilities
- We support CVE assignment for significant vulnerabilities
*（内容由AI生成，仅供参考）*
