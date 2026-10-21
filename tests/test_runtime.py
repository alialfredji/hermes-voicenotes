import unittest
from contextlib import nullcontext
from types import SimpleNamespace as NS


class AdapterTests(unittest.TestCase):
    def make_adapter(self):
        from hermes_runtime import HermesAdapter
        self.probes = []
        self.present = True
        self.token = NS(access_token='example-only', expires_in=120, token_type='Bearer')
        owner = self
        class Storage:
            def __init__(self, name):
                self.name = name
            def has_cached_tokens(self):
                return owner.present
            async def get_tokens(self):
                return owner.token
        def probe(name, cfg, connect_timeout=None):
            self.probes.append(cfg)
            return [('list_notes', 'example')]
        config = NS(_get_mcp_servers=lambda: {'voicenotes': {'url': 'https://api.voicenotes.com/mcp', 'auth': 'oauth'}},
                    _probe_single_server=probe, cmd_mcp_add=lambda args: None,
                    _reauth_oauth_server=lambda name, cfg, flow=None: True,
                    _choose_tools=lambda *args: None, _confirm=lambda *args, **kwargs: False,
                    _configure_http_auth=lambda name, url, auth, cfg: True)
        oauth = NS(HermesTokenStorage=Storage, _OAUTH_AVAILABLE=True,
                   suppress_interactive_oauth=nullcontext, force_interactive_oauth=nullcontext,
                   _announce_authorization_url=lambda *args: None)
        class Provider:
            async def _perform_authorization(self):
                pass
            def _prepare_token_request(self, request):
                return request
        provider = NS(HermesProviderMixin=Provider, stamp_default_user_agent=lambda request: request)
        return HermesAdapter(config, oauth, provider, lambda url: True)

    def test_execute_doctor_uses_runtime_modules_without_network(self):
        from hermes_runtime import execute
        adapter = self.make_adapter()
        args = NS(doctor=True, check=False, reauth=False, browser='default')
        code, message = execute(args, modules=(adapter.cli, adapter.oauth, adapter.provider))
        self.assertEqual(code, 0)
        self.assertIn('No network', message)
        self.assertEqual(self.probes, [])

    def test_browser_selection_never_uses_a_shell_or_logs_url(self):
        from hermes_runtime import browser_opener
        from unittest.mock import patch
        with patch('webbrowser.open', return_value=True) as opened:
            self.assertTrue(browser_opener('default')('https://api.voicenotes.com/oauth/authorize?state=example'))
            opened.assert_called_once()
        with patch('sys.platform', 'darwin'), patch('subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertTrue(browser_opener('chrome')('https://api.voicenotes.com/oauth/authorize?state=example'))
            self.assertEqual(run.call_args.args[0][:3], ['open', '-a', 'Google Chrome'])
            self.assertTrue(run.call_args.kwargs['capture_output'])
        with patch('sys.platform', 'linux'), self.assertRaises(RuntimeError):
            browser_opener('chrome')

    def test_registration_installs_compat_before_discovery_and_enables_all(self):
        from test_compat import FakeRequest
        adapter = self.make_adapter()
        events = []
        original = adapter.provider.stamp_default_user_agent
        def configure(name, url, auth, cfg):
            self.assertEqual(cfg['oauth']['cimd'], False)
            return True
        adapter.cli._configure_http_auth = configure
        def add(args):
            self.assertEqual(args.name, 'voicenotes')
            self.assertEqual(args.auth, 'oauth')
            cfg = {}
            self.assertTrue(adapter.cli._configure_http_auth(args.name, args.url, args.auth, cfg))
            r = FakeRequest('GET', 'https://api.voicenotes.com/.well-known/oauth-authorization-server')
            adapter.provider.stamp_default_user_agent(r)
            self.assertEqual(r.headers['accept'], '*/*')
            self.assertEqual(adapter.cli._choose_tools('voicenotes', [('a', ''), ('b', '')], cfg), 2)
            self.assertFalse(adapter.cli._confirm('Save failed configuration?', default=True))
            events.append('discovery-with-compat')
        adapter.cli.cmd_mcp_add = add
        adapter.cli._get_mcp_servers = lambda: {}
        self.present = False
        adapter.register()
        self.assertEqual(events, ['discovery-with-compat'])
        self.assertIs(adapter.provider.stamp_default_user_agent, original)
        self.assertIs(adapter.cli._configure_http_auth, configure)

    def test_login_without_tokens_never_calls_destructive_reauth(self):
        adapter = self.make_adapter()
        calls = []
        adapter.cli._probe_single_server = lambda name, cfg, connect_timeout=None: calls.append((cfg, connect_timeout)) or [('a', '')]
        adapter.cli._reauth_oauth_server = lambda *args, **kwargs: self.fail('must not clear state')
        cfg = adapter.config()
        self.assertTrue(adapter.login(cfg))
        self.assertEqual(calls[0][1], 960)
        self.assertFalse(calls[0][0]['oauth']['cimd'])
        self.assertNotIn('oauth', cfg)
        adapter.cli._reauth_oauth_server = lambda name, cfg, flow=None: flow == 'browser'
        self.assertTrue(adapter.login(cfg, reauth=True))

    def test_incompatible_internal_api_fails_closed(self):
        from hermes_runtime import validate_apis
        adapter = self.make_adapter()
        validate_apis(adapter.cli, adapter.oauth, adapter.provider)
        adapter.cli._probe_single_server = lambda different: None
        with self.assertRaises(RuntimeError):
            validate_apis(adapter.cli, adapter.oauth, adapter.provider)

    def test_saved_check_uses_static_bearer_no_oauth_no_refresh_no_notes(self):
        adapter = self.make_adapter()
        cfg = {'url': 'https://api.voicenotes.com/mcp', 'auth': 'oauth', 'oauth': {'timeout': 900}}
        self.assertEqual(adapter.check(cfg), 1)
        sent = self.probes[0]
        self.assertNotIn('auth', sent)
        self.assertNotIn('oauth', sent)
        self.assertEqual(sent['headers'], {'Authorization': 'Bearer example-only'})
        self.assertEqual(cfg['auth'], 'oauth')
        self.token.expires_in = 0
        self.assertEqual(adapter.check(cfg), 0)
        self.assertEqual(len(self.probes), 1)
        self.assertTrue(adapter.has_tokens())
        self.assertEqual(adapter.config()['auth'], 'oauth')


if __name__ == '__main__':
    unittest.main()
