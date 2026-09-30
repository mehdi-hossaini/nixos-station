# Security reporting

This configuration manages disk formatting, boot, credentials and persistent
data. Report unsafe target selection, credential exposure, or filesystem
operations that can affect unintended data as security defects.

Use the repository's **Security → Report a vulnerability** option when available.
If it is unavailable, open an issue asking for a private reporting channel,
without disclosing the vulnerability. This follows
[GitHub's private reporting guidance](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).

Privately include the affected commit, relevant dependency pins, expected and
observed behavior, and a reproduction using synthetic data or disposable disks.
Remove passwords, tokens, age identities, SSH keys and personal disk contents
from logs. Never reproduce a destructive failure against a disk containing
valuable data.

For ordinary bugs, open an issue with the commit, sanitized error output and
the relevant check results. Hardware reports should follow the
[acceptance procedure](docs/hardware-testing.md).
