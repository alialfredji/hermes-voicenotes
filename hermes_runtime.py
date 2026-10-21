"""Version-sensitive Hermes adapter. No imports of Hermes at module load."""
import asyncio
import inspect
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from compat import installed
from connector import ENDPOINT, NAME, connect


def browser_opener(choice):
    import subprocess
    import sys
    import webbrowser
    if choice == 'default':
        return webbrowser.open
    if choice != 'chrome' or sys.platform != 'darwin':
        raise RuntimeError('The Chrome browser option currently supports macOS only.')
    def chrome(url):
        return subprocess.run(['open', '-a', 'Google Chrome', url], capture_output=True, timeout=15).returncode == 0
    return chrome


def execute(args, modules=None):
    if modules is None:
        from hermes_cli import mcp_config as cli
        from tools import mcp_oauth as oauth, mcp_oauth_provider as provider
        modules = cli, oauth, provider
    validate_apis(*modules)
    adapter = HermesAdapter(*modules, browser_opener(args.browser))
    mode = 'doctor' if args.doctor else 'check' if args.check else 'connect'
    return connect(adapter, mode=mode, reauth=args.reauth)



@contextmanager
def override(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def validate_apis(cli, oauth, provider):
    """Reject changed internal call signatures before a browser or state change."""
    try:
        if not oauth._OAUTH_AVAILABLE:
            raise ValueError('MCP SDK unavailable')
        calls = [
            (cli._get_mcp_servers, (), {}),
            (cli._probe_single_server, (NAME, {}), {'connect_timeout': 30}),
            (cli.cmd_mcp_add, (SimpleNamespace(),), {}),
            (cli._reauth_oauth_server, (NAME, {}), {'flow': 'browser'}),
            (cli._configure_http_auth, (NAME, ENDPOINT, 'oauth', {}), {}),
            (cli._choose_tools, (NAME, [], {}), {}),
            (cli._confirm, ('question',), {'default': False}),
            (oauth.HermesTokenStorage, (NAME,), {}),
            (oauth.HermesTokenStorage.has_cached_tokens, (None,), {}),
            (oauth.HermesTokenStorage.get_tokens, (None,), {}),
            (oauth.suppress_interactive_oauth, (), {}),
            (oauth.force_interactive_oauth, (), {}),
            (oauth._announce_authorization_url, ('url', 1234, None), {}),
            (provider.stamp_default_user_agent, (None,), {}),
            (provider.HermesProviderMixin._perform_authorization, (None,), {}),
            (provider.HermesProviderMixin._prepare_token_request, (None, None), {}),
        ]
        for fn, args, kwargs in calls:
            inspect.signature(fn).bind(*args, **kwargs)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError('Hermes internal APIs are incompatible; update Hermes or report compatibility.') from None



class HermesAdapter:
    def __init__(self, config_module, oauth_module, provider_module, open_browser):
        self.cli = config_module
        self.oauth = oauth_module
        self.provider = provider_module
        self.open_browser = open_browser
        self.storage = oauth_module.HermesTokenStorage(NAME)

    def config(self):
        return self.cli._get_mcp_servers().get(NAME)

    def has_tokens(self):
        return self.storage.has_cached_tokens()

    def register(self):
        """Use the CLI's add/save/enable path, with compatibility active first."""
        if self.config() is not None or self.has_tokens():
            raise RuntimeError('Refusing to overwrite an existing entry or authorization.')
        original_configure = self.cli._configure_http_auth
        def configure(name, url, auth, cfg):
            if name == NAME and url == ENDPOINT and auth == 'oauth':
                cfg['oauth'] = {'cimd': False, 'flow': 'browser', 'timeout': 900}
            return original_configure(name, url, auth, cfg)
        with ExitStack() as stack:
            stack.enter_context(installed(self.provider, self.oauth, self.open_browser))
            stack.enter_context(self.oauth.force_interactive_oauth())
            stack.enter_context(override(self.cli, '_configure_http_auth', configure))
            stack.enter_context(override(self.cli, '_choose_tools', lambda name, tools, cfg: len(tools) or None))
            stack.enter_context(override(self.cli, '_confirm', lambda *args, **kwargs: False))
            self.cli.cmd_mcp_add(SimpleNamespace(name=NAME, url=ENDPOINT, auth='oauth',
                                                connect_timeout=960, mcp_command=None,
                                                args=[], env=[], preset=None))

    def login(self, cfg, reauth=False):
        config = {**cfg, 'oauth': {**(cfg.get('oauth') or {}), 'cimd': False,
                                  'flow': 'browser', 'timeout': 900}}
        with installed(self.provider, self.oauth, self.open_browser), self.oauth.force_interactive_oauth():
            if reauth:
                return self.cli._reauth_oauth_server(NAME, config, flow='browser')
            self.cli._probe_single_server(NAME, config, connect_timeout=960)
            return self.has_tokens()

    def check(self, cfg):
        """Use a static access token: never initialize OAuth, refresh, or fetch notes."""
        token = asyncio.run(self.storage.get_tokens())
        if (token is None or not token.access_token
                or (token.expires_in is not None and token.expires_in <= 0)):
            return 0
        config = {k: v for k, v in cfg.items() if k not in ('auth', 'oauth', 'headers')}
        config['headers'] = {'Authorization': 'Bearer ' + token.access_token}
        try:
            with self.oauth.suppress_interactive_oauth():
                return len(self.cli._probe_single_server(NAME, config, connect_timeout=30))
        except Exception:
            return 0
