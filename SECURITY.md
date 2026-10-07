# Security Policy

## Supported versions

The latest released version receives security fixes. `repo-ready` is pre-1.0, so older versions are not patched — please upgrade before reporting.

| Version | Supported |
| --- | --- |
| 0.1.x | ✅ |

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's [security advisory form](https://github.com/rodny90/pr-policy/security/advisories/new) rather than in a public issue.

Include what you can: the version, the steps to reproduce, and what an attacker gains. You should get an acknowledgement within 7 days and an assessment within 30. If a fix is warranted it will ship in a patch release, and you will be credited in the advisory unless you would rather not be.

## Threat model

`repo-ready` reads files from a directory you point it at. It makes no network calls, executes nothing it reads, and writes nothing outside stdout — so the realistic risks are limited to path handling and resource exhaustion when it walks a hostile directory tree. Reports in that area are in scope; so is anything that causes the tool to read outside the directory it was given.
