"""Provider-scoped OAuth request tests, no HTTP dependencies."""
import importlib
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

CALLBACK = 'http://127.0.0.1:49152/callback'


class CompatibilityTests(unittest.TestCase):
    def test_authorization_uses_only_single_registered_complete_loopback(self):
        c = importlib.import_module('compat')
        query = dict(redirect_uri=CALLBACK, state='example-state', code_challenge='example-challenge',
                     code_challenge_method='S256', client_id='example-client', scope='read', resource='https://api.voicenotes.com/mcp')
        url = 'https://api.voicenotes.com/oauth/authorize?' + urlencode(query)
        result = c.authorization_url(url, [CALLBACK])
        expected = {k: [v] for k, v in query.items() if k != 'redirect_uri'}
        self.assertEqual(parse_qs(urlsplit(result).query), expected)
        for redirects in [[], [CALLBACK, CALLBACK], ['http://localhost:49153/callback']]:
            with self.subTest(redirects=redirects), self.assertRaises(ValueError):
                c.authorization_url(url, redirects)
        for bad in ['http://evil.test:49152/callback', 'http://localhost/callback',
                    'https://localhost:49152/callback', 'http://u@localhost:49152/callback',
                    CALLBACK + '?x=1', CALLBACK + '#x', 'http://localhost:0/callback']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                c.authorization_url(url.replace(urlencode({'redirect_uri': CALLBACK}), urlencode({'redirect_uri': bad})), [bad])
        with self.assertRaises(ValueError):
            c.authorization_url(url.replace('api.voicenotes.com', 'evil.test'), [CALLBACK])
        with self.assertRaises(ValueError):
            c.authorization_url(url + '&redirect_uri=' + CALLBACK, [CALLBACK])


class FakeRequest:
    def __init__(self, method, url, *, content=b'', headers=None, extensions=None):
        self.method, self.url, self.content = method, url, content
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.headers['content-length'] = str(len(content))
        self.extensions = extensions or {}


class TokenTests(unittest.TestCase):
    def test_token_omission_is_bound_to_same_authorization(self):
        from compat import prepare_token_request
        fields = dict(grant_type='authorization_code', redirect_uri=CALLBACK, code='example-code',
                      code_verifier='example-verifier', client_id='example-client', client_secret='example-secret',
                      resource='https://api.voicenotes.com/mcp', scope='read')
        request = FakeRequest('POST', 'https://api.voicenotes.com/oauth/token',
                              content=urlencode(fields).encode(),
                              headers={'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Basic example'},
                              extensions={'trace': 1})
        result = prepare_token_request(request, CALLBACK)
        self.assertIs(type(result), FakeRequest)
        self.assertEqual(parse_qs(result.content.decode()), {k: [v] for k, v in fields.items() if k != 'redirect_uri'})
        self.assertEqual(result.headers['authorization'], 'Basic example')
        self.assertEqual(result.headers['content-length'], str(len(result.content)))
        self.assertEqual(result.extensions, request.extensions)
        self.assertIs(prepare_token_request(request, None), request)
        request.url = 'https://other.example/oauth/token'
        self.assertIs(prepare_token_request(request, CALLBACK), request)
        request.url = 'https://api.voicenotes.com/oauth/token'
        with self.assertRaises(ValueError):
            prepare_token_request(request, 'http://localhost:49153/callback')
        request.content = b'grant_type=refresh_token&refresh_token=example'
        self.assertIs(prepare_token_request(request, CALLBACK), request)
        request.content = urlencode(fields).encode() + b'&redirect_uri=duplicate'
        with self.assertRaises(ValueError):
            prepare_token_request(request, CALLBACK)


class InstallationTests(unittest.IsolatedAsyncioTestCase):
    async def test_hooks_cover_discovery_and_initial_login_then_restore(self):
        from types import SimpleNamespace as NS
        from compat import installed
        opened = []
        announced = []
        async def redirect(url):
            oauth._announce_authorization_url(url, 49152, None)
        class Provider:
            async def _perform_authorization(self):
                await self.context.redirect_handler(self.url)
            def _prepare_token_request(self, request):
                return request
        def stamp(request):
            return request
        def announce(*args):
            announced.append(args)
        module = NS(HermesProviderMixin=Provider, stamp_default_user_agent=stamp)
        oauth = NS(_announce_authorization_url=announce)
        p = Provider()
        p.context = NS(server_url='https://api.voicenotes.com/mcp',
                       client_info=NS(redirect_uris=[CALLBACK]), redirect_handler=redirect)
        p.url = 'https://api.voicenotes.com/oauth/authorize?' + urlencode(dict(redirect_uri=CALLBACK, state='s', code_challenge='c'))
        with installed(module, oauth, lambda url: opened.append(url) or True):
            request = FakeRequest('GET', 'https://api.voicenotes.com/.well-known/oauth-authorization-server')
            module.stamp_default_user_agent(request)
            self.assertEqual(request.headers.get('accept'), '*/*')
            self.assertTrue(request.headers.get('user-agent'))
            other = FakeRequest('GET', 'https://another.example/.well-known/oauth-authorization-server')
            module.stamp_default_user_agent(other)
            self.assertNotIn('accept', other.headers)
            await p._perform_authorization()
            self.assertNotIn('redirect_uri', parse_qs(urlsplit(opened[0]).query))
            token = FakeRequest('POST', 'https://api.voicenotes.com/oauth/token',
                                content=urlencode(dict(grant_type='authorization_code', redirect_uri=CALLBACK, code_verifier='keep')).encode(),
                                headers={'Content-Type': 'application/x-www-form-urlencoded'})
            self.assertNotIn('redirect_uri', parse_qs(p._prepare_token_request(token).content.decode()))
            p.context.server_url = 'https://another.example/mcp'
            await p._perform_authorization()
            self.assertEqual(len(opened), 1)
            self.assertEqual(len(announced), 1)
        self.assertIs(module.stamp_default_user_agent, stamp)
        self.assertIs(oauth._announce_authorization_url, announce)
        self.assertIs(p.context.redirect_handler, redirect)


if __name__ == '__main__':
    unittest.main()
