# Native Hermes integration: Voicenotes MCP

Research snapshot: 2026-10-21. Design only; no Hermes source/config changes, login, token reset, fork, PR, or publication performed by this research task.

## Recommendation

Use Hermes' existing native remote MCP client, not a Voicenotes REST wrapper or a second token store. A clean upstream contribution has **two parts**:

1. A reviewed `optional-mcps/voicenotes/manifest.yaml` for catalog/picker installation.
2. OAuth request compatibility in the shared Hermes OAuth provider, with regression tests. **A catalog entry alone does not fix the observed OAuth/WAF failures.**

Prefer a provider-side WAF fix that accepts ordinary standards-conformant OAuth requests. If Hermes must accommodate it, scope callback-parameter adaptation to the exact official Voicenotes endpoint and retain every OAuth validation. Do not make a process-wide Python monkeypatch the permanent integration.

## What was checked

- Installed checkout HEAD: `5b147ab036d6d19131bff8d20701b5001eab844a`.
- Upstream `main` observed via `git ls-remote`: `1438d0ea25f893d54ea553f49f9d5c76556348c3`. The installed checkout is not assumed to be current. Relevant upstream files were read at that immutable ref with `gh api`, without fetching or changing the checkout.
- At that upstream ref, `tools/mcp_oauth_provider.py` supplies a default User-Agent but not the additional default Accept header. The manifest OAuth allowlist is unchanged from the installed version. Reading `optional-mcps/voicenotes/manifest.yaml` returned HTTP 404.
- The installed checkout already contained an uncommitted `Accept: */*` repair in `tools/mcp_oauth_provider.py` and an untracked `tests/tools/test_mcp_oauth_accept_header.py` before this task. They were left untouched; final status matched initial status.
- Live official Hermes docs confirm remote MCP, catalog installation and review through `optional-mcps/`. The Voicenotes guide confirms the official endpoint, browser OAuth, no manual API key/client secret, and HTTP/Streamable HTTP support.
- Earlier successful setup evidence supplied to this research task: single registered callback, state/PKCE/client authentication retained, redundant `redirect_uri` omitted from both authorization URL and authorization-code token form; stored tokens, four tools and a read-only call succeeded. This task did **not** repeat login or read private notes. Refresh-token renewal remains unverified end-to-end.

## Proposed upstream patch

### A. Normal default headers

In `tools/mcp_oauth_provider.py`, extend `stamp_default_user_agent()` (or rename it to describe both defaults) to fill only missing `User-Agent` and `Accept: */*` on SDK-generated OAuth discovery/registration/token requests. Bare SDK requests sent through `client.send()` do not inherit client default headers. Preserve explicit header values; do not impersonate a browser or change unrelated MCP resource requests.

This small generic HTTP-default fix is separable from the provider-specific callback workaround.

### B. Exact-endpoint OAuth compatibility

Use existing `prepare_oauth_config()` / `build_provider_kwargs()` plumbing and `HermesProviderMixin`, which serve both the legacy provider builder and `MCPOAuthManager`. If maintainers choose an explicit setting, add a narrowly named, validated compatibility option there; it is **not a currently supported configuration key**. Provider defaults may select it only for the exact HTTPS official MCP endpoint, never from the server label `voicenotes` alone.

Suggested behavior:

- Check the discovered authorization issuer and endpoint identities against a reviewed exact Voicenotes allowlist. Do not accept suffix/lookalike hosts, a different scheme, custom port or arbitrary token URL merely because the MCP entry is named Voicenotes.
- Register and retain exactly one complete callback URI. Before authorization, require the active callback to match the sole registered callback; do not omit callback registration or change the listener's routing/validation.
- Remove `redirect_uri` from the outgoing authorization URL only in this bounded mode. Track that decision on the individual authorization attempt, not as a module/global flag. Preserve state, PKCE challenge/method, client ID, scope and resource, including repeated parameters.
- For that same attempt only, adapt an authorization-code form POST to the exact discovered-and-approved token endpoint. Require its original `redirect_uri` to equal the registered callback before removing it. Preserve code, PKCE verifier, client authentication, resource and other form fields; do not apply this rewrite to refresh/device grants.
- Rebuild using `type(request)` rather than an imported `httpx.Request`: the installed SDK can produce `httpx2.Request`. Preserve headers/extensions, omit stale Content-Length and let the concrete request class recalculate it. Reject malformed or ambiguous inputs rather than silently relaxing checks.
- Leave issuer checks, token audience/resource binding, state validation, refresh fencing, storage permissions and profile isolation intact. Do not clear valid existing tokens just to activate compatibility.

RFC 6749 permits an omitted authorization redirect URI when the server can select the registered URI; §4.1.3 requires it in the token request if included in authorization. Therefore removing it **only** at exchange is not the design. This is not a claim of full OAuth 2.1/MCP conformance: review the applicable MCP/SDK requirements with maintainers and the provider before shipping an exception. An upstream WAF repair is preferable.

### C. Catalog entry

**Example only — parser-validated, not installed, approved or submitted.** Proposed destination: `optional-mcps/voicenotes/manifest.yaml`.

```yaml
manifest_version: 1
name: voicenotes
description: Search, browse, retrieve, and create Voicenotes.
source: https://help.voicenotes.com/en/articles/14336494-voicenotes-mcp
transport:
  type: http
  url: https://api.voicenotes.com/mcp
auth:
  type: oauth
```

Do not set `auth.provider: voicenotes`: that field drives provider-mediated `hermes auth <provider>` guidance, not native MCP OAuth. Do not hardcode a DCR client ID/secret or add an invented compatibility key to this manifest. Current `auth.oauth` allows only `client_id`, `client_secret`, `redirect_host`, `redirect_port`, and `scope`. A new manifest-carried option would require schema and installer tests; endpoint-scoped internal defaults avoid that schema change. Omit `connector_slug` unless a real hosted connector mapping is separately verified.

The minimal example was passed to `_parse_manifest()` with mocked file input and then `_build_server_config()`. Actual output:

```text
VALID manifest_version=1; config: {'url': 'https://api.voicenotes.com/mcp', 'auth': 'oauth'}
```

Catalog installer behavior is already shared: write transport/auth, set explicit enabled state, probe/select tools, show post-install guidance. No git bootstrap, npx/uvx bridge or additional daemon is needed for this hosted endpoint.

## Why not a preset or plugin?

- `_MCP_PRESETS` / `_apply_mcp_preset()` supply transport URL/command/args when omitted. They do not implement OAuth request rewriting or confer catalog approval.
- `PluginContext.call_mcp()` consumes an existing native MCP connection under an allowlist. The inspected `VALID_HOOKS` and provider code expose no dedicated supported OAuth request-transform hook. General lifecycle/tool hooks are not an equivalent replacement for shared provider logic.
- A plugin/portable manifest can package registration, but it does not by itself repair SDK-built OAuth requests across CLI, dashboard, Desktop and background reconnects. Avoid dependence on import timing and private-method monkeypatches.

## Tests and acceptance gates

Proposed coverage:

1. Header defaults and explicit-header preservation for real SDK request classes.
2. Exact-endpoint positive cases; other providers, same-name custom servers, lookalike hosts, unexpected paths/ports/schemes and different issuers unchanged or rejected.
3. Single registered matching callback only; multi-callback, mismatch, duplicate/ambiguous form fields and malformed encodings fail closed.
4. Authorization and exchange coupled per attempt; state/PKCE/client auth/scope/resource preserved; concurrent attempts isolated; concrete request type, extensions and Content-Length correct.
5. Refresh/device requests unchanged; cached-token reconnect and issuer/refresh-fence tests retain existing behavior.
6. Both provider constructors, CLI and dashboard/Desktop authorization routes; HTTP callback modes tested separately from the validated loopback case.
7. Catalog parser, generated config, explicit enabled state and existing tool selections preserved.
8. Opt-in manual test with a fresh test profile: callback received → token exchange successful → enabled → tool discovery → minimal read-only call. Separately exercise renewal; no note contents or credentials in CI fixtures/logs.

Executed here: `hermes --run-module unittest tests.tools.test_mcp_oauth_accept_header -v` — **2 tests passed**. Existing discovery/user-agent suites could not import because the installed runtime lacks `pytest`; no packages were installed and those suites are not claimed passing. Proposed new compatibility code/tests were not implemented.

## Evidence map (paths relative to the Hermes source checkout)

| Path / symbol | Evidence |
|---|---|
| `hermes_cli/mcp_catalog.py:42-54,195-231` | Auth model and allowed manifest OAuth keys |
| `hermes_cli/mcp_catalog.py:311-345,539-559` | Manifest parser and generated server config |
| `hermes_cli/mcp_catalog.py:772-845` | Install, explicit enable state, auth guidance and probe/checklist |
| `optional-mcps/linear/manifest.yaml` | Existing hosted native OAuth/DCR catalog pattern |
| `tools/mcp_oauth_provider.py:39-54,78-111,196-222,228-287` | Header stamp, shared mixin, authorization/token and SDK flow interception |
| `tools/mcp_oauth_provider.py:609-638` | Shared config preparation and constructor kwargs |
| `tools/mcp_oauth.py:1027-1032,1050-1098,1117-1157` | Token User-Agent option, callback resolution, provider defaults, single-callback metadata |
| `hermes_cli/mcp_config.py:_MCP_PRESETS,_apply_mcp_preset` | Transport-only presets |
| `hermes_cli/plugins.py:VALID_HOOKS,PluginContext.call_mcp` | Existing plugin hooks and MCP consumer API |
| `hermes_cli/subcommands/mcp.py` | CLI add/install/login declarations |
| `tests/tools/test_mcp_oauth_accept_header.py` | Pre-existing local two-test header repair coverage |
| `tests/tools/test_mcp_oauth_discovery_requests.py`, `test_mcp_oauth_user_agent.py`, `test_mcp_oauth_manager.py` | Adjacent OAuth regression suites |
| `tests/hermes_cli/test_mcp_catalog.py`, `test_mcp_catalog_env_boundary.py` | Catalog regression targets |

Line numbers above describe the installed working tree; immutable upstream content differs by the absent three-line Accept repair. For immutable evidence and repeatable read-only checks, run these in a Hermes source checkout (host shell):

```bash
git rev-parse HEAD
git status --short
git diff -- tools/mcp_oauth_provider.py
git ls-remote origin HEAD refs/heads/main
# Snapshot used by this document; no checkout/fetch needed:
REF=1438d0ea25f893d54ea553f49f9d5c76556348c3
gh api "repos/NousResearch/hermes-agent/contents/tools/mcp_oauth_provider.py?ref=$REF" --jq .content | base64 --decode
gh api "repos/NousResearch/hermes-agent/contents/hermes_cli/mcp_catalog.py?ref=$REF" --jq .content | base64 --decode
gh api "repos/NousResearch/hermes-agent/contents/optional-mcps/voicenotes/manifest.yaml?ref=$REF"
hermes mcp add --help
hermes mcp login --help
hermes --run-module unittest tests.tools.test_mcp_oauth_accept_header -v
```

The Voicenotes manifest lookup above is expected to return 404 at the recorded snapshot. None of these commands authorizes or reconfigures a server. Future user-authorized acceptance may use `hermes mcp install voicenotes` only after the upstream entry exists; current custom-server syntax is `hermes mcp add voicenotes --url https://api.voicenotes.com/mcp --auth oauth`. These are state-changing setup commands, **not executed by this task** and not a promise that unpatched OAuth succeeds.

## Public references

- Hermes native MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- Hermes MCP config: https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference
- Voicenotes provider guide: https://help.voicenotes.com/en/articles/14336494-voicenotes-mcp
- OAuth authorization/token parameters: https://www.rfc-editor.org/rfc/rfc6749#section-4.1.1 and https://www.rfc-editor.org/rfc/rfc6749#section-4.1.3

Public docs and fixtures must contain no local account paths, private notes, client secrets, callback codes, tokens, state or PKCE material.
