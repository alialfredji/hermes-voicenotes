# Hermes × Voicenotes

A small, local connector for the official Voicenotes MCP server. Uses Hermes' existing OAuth storage and Python runtime—no API key, extra pip install, or permanent Hermes source patch.

## Connect

In your **host OS shell**, on the same computer as your browser:

```sh
git clone https://github.com/alialfredji/hermes-voicenotes.git
cd hermes-voicenotes
python3 connect.py
```

Requires Python 3.10+ and an installed `hermes` command with MCP support. Complete approval in your default browser if asked. The command enables all discovered tools on a new installation. Start a new Hermes session and ask it to list your latest Voicenotes.

Already connected? Saved authorization is checked first and preserved. A failed saved connection never automatically clears credentials or starts another login.

```sh
python3 connect.py --doctor          # offline runtime/config diagnosis
python3 connect.py --check           # saved-token connection test; no refresh or writes
python3 connect.py --browser chrome  # macOS Chrome instead of default browser
python3 connect.py --reauth          # destructive replacement, requires typed confirmation
python3 connect.py --help
```

`--reauth` clears this server's saved tokens and client registration before authorization. Cancellation or failure after clearing may leave you disconnected. Do not use it to test a working account.

## What it changes

- New installation: calls Hermes' MCP add flow to register `voicenotes` at `https://api.voicenotes.com/mcp`, authenticate via OAuth Dynamic Client Registration, and enable discovered tools.
- Existing entry with no token file: authorizes without clearing registration.
- Existing entry with tokens: tests a static access token without invoking OAuth or refreshing. Expired tokens fail safely; use normal Hermes to refresh them, or explicitly request reauthorization if needed.
- Existing disabled entry: leaves settings alone. Ask Hermes **“enable the voicenotes MCP connection”**, then rerun `--check`.
- Conflicting endpoints, manually configured OAuth clients, and orphaned token files are not overwritten.

No YAML hand-editing, private note retrieval, credential collection, or permanent source modifications. Hermes owns profile selection and credential persistence. Internal helper output is withheld rather than risking disclosure of authorization URLs, callback codes, or tokens. Browser authorization URLs necessarily reach your local browser and may appear in its history.

## Compatibility and limits

This is an **unofficial, version-sensitive compatibility wrapper**, not a Hermes or Voicenotes product. It inspects required internal API signatures and fails closed if the runtime launcher or APIs differ.

The provider-specific workaround fills missing User-Agent/Accept headers and relies on exactly one complete DCR-registered loopback callback. It omits redundant `redirect_uri` at both authorization and authorization-code exchange while retaining state, PKCE, client authentication, scope, and resource. Other providers retain their existing behavior. Request reconstruction preserves the SDK's concrete request class (including `httpx2`). Compatibility is installed before initial server discovery, not just during reauthorization.

Local validation targets Hermes 0.22.3 on macOS. Offline diagnostics and live stored-token discovery passed; the default command preserved the working login and found four tools. This repository's new CLI has **not** completed a fresh live OAuth flow or authenticated note lookup. Its predecessor workaround did; that does not constitute end-to-end verification of this implementation. Token refresh and other operating systems remain unverified. Runtime/API checks do not prove behavioral compatibility. Remote/headless browser setup is not supported.

## Can this become built into Hermes?

Yes, through an upstream contribution: a reviewed Voicenotes MCP catalog entry plus narrowly scoped OAuth compatibility in Hermes itself. A catalog entry alone does not fix the observed request failures. See [the native integration design](docs/upstream.md) for the proposed manifest, implementation boundaries, and acceptance tests. This repo is an independent helper; no upstream PR has been submitted or merged.

Exit codes: `0` verified connection (or successful offline doctor), `1` connection/auth pending or cancelled, `2` incompatible runtime/configuration, `3` connected but disabled. `--check` proves MCP tool discovery, not note retrieval or every tool's permissions.

## Development

No third-party test dependencies or credentials:

```sh
python3 -m unittest discover -s tests -v
```

Tests use fake providers/requests and mocked process/browser boundaries; they never contact Voicenotes or a real Hermes profile. CI runs the same suite. Tests were developed through observed red → green cycles. OAuth, production refresh, and browser consent must be verified separately with an explicitly authorized disposable/test profile.

MIT licensed. Review [SECURITY.md](SECURITY.md) before sharing diagnostic information.
