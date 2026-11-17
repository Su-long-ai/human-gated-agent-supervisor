# Security

This public repository is intentionally local-first and contains no credentials.

Do not commit:
- API keys or access tokens;
- private conversation or project IDs;
- TLS private keys/certificates;
- machine-specific state directories;
- user conversation logs.

The runtime validates round identity and lease ownership before accepting heartbeat or commit writes.
