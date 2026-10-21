"""Small, standard-library bootstrap and connection policy."""
import json

ENDPOINT = 'https://api.voicenotes.com/mcp'
NAME = 'voicenotes'


def connect(adapter, mode='connect', reauth=False):
    """Keep decisions separate from the version-specific Hermes implementation."""
    cfg = adapter.config()
    if cfg is not None and (cfg.get('url') != ENDPOINT or cfg.get('auth') != 'oauth'
            or cfg.get('command') or cfg.get('headers')
            or any((cfg.get('oauth') or {}).get(k) for k in
                   ('client_id', 'client_secret', 'redirect_uri', 'redirect_port', 'redirect_host', 'client_metadata_url'))):
        return 2, 'Conflicting Voicenotes configuration; left unchanged. Use the official endpoint and automatic OAuth registration.'
    cached = adapter.has_tokens()
    if mode == 'doctor':
        return 0, f'Runtime compatible. Registered: {cfg is not None}. Cached authorization: {cached}. No network request made.'
    count = adapter.check(cfg) if cached and cfg is not None else 0
    changed = False
    if mode == 'connect':
        if cfg is None:
            if cached:
                return 2, 'Orphaned cached authorization found; no server was added or tokens cleared. Resolve registration in Hermes first.'
            adapter.register()
            cfg = adapter.config()
            if not cfg or cfg.get('url') != ENDPOINT or cfg.get('auth') != 'oauth':
                return 1, 'Registration did not complete. No success claimed; run --doctor before retrying.'
            changed = True
        elif reauth or not cached:
            if not adapter.login(cfg, reauth=reauth):
                return 1, 'Authorization did not complete. Retry only after checking --doctor; no credentials are printed.'
            changed = True
        if changed:
            cached = adapter.has_tokens()
            count = adapter.check(cfg) if cached else 0
    if not count:
        return 1, 'Saved connection could not be verified. No automatic reauthorization was attempted. Use --reauth only to explicitly replace it.'
    if cfg.get('enabled', True) is not True:
        return 3, f'Connected: {count} tools, but not enabled. In Hermes ask: enable the voicenotes MCP connection. Then rerun --check.'
    suffix = 'Authorization verified.' if changed else 'Existing authorization preserved.'
    return 0, f'Connected: {count} tools available. {suffix}'


def runtime_command(raw, script, args):
    """Reuse Hermes' own environment initialization; reject unknown launchers."""
    command = json.loads(raw)
    old = "runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
    if (not isinstance(command, list) or len(command) < 3
            or not all(isinstance(x, str) for x in command)
            or command[-2] != '-c' or command[-1].count(old) != 1):
        raise ValueError('Unsupported Hermes runtime launcher; update Hermes or report compatibility.')
    command = command.copy()
    command[-1] = command[-1].replace(old, "runpy.run_path(sys.argv.pop(1), run_name='__main__')")
    return command + [str(script), '--inside-runtime'] + list(args)
