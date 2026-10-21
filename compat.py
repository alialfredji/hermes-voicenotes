"""Process-local, fail-closed Voicenotes OAuth compatibility."""
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@contextmanager
def installed(provider_module, oauth_module, open_browser):
    """Install only in this process, before creating or discovering providers."""
    cls = provider_module.HermesProviderMixin
    original_auth = cls._perform_authorization
    original_token = cls._prepare_token_request
    original_stamp = provider_module.stamp_default_user_agent
    original_announce = oauth_module._announce_authorization_url
    active = ContextVar('voicenotes_authorization', default=False)

    def stamp(request):
        result = original_stamp(request)
        p = urlsplit(str(result.url))
        if p.scheme + '://' + p.netloc == ORIGIN:
            result.headers.setdefault('user-agent', 'Hermes-Voicenotes/1.0')
            result.headers.setdefault('accept', '*/*')
        return result

    async def authorize(self, *args, **kwargs):
        if str(self.context.server_url) != ORIGIN + '/mcp':
            return await original_auth(self, *args, **kwargs)
        inner = self.context.redirect_handler
        self._voicenotes_omitted_callback = None
        async def redirect(url):
            info = self.context.client_info
            registered = getattr(info, 'redirect_uris', None) or []
            result = authorization_url(url, registered)
            self._voicenotes_omitted_callback = str(registered[0])
            return await inner(result)
        self.context.redirect_handler = redirect
        marker = active.set(True)
        try:
            return await original_auth(self, *args, **kwargs)
        finally:
            active.reset(marker)
            self.context.redirect_handler = inner

    def token(self, request):
        result = original_token(self, request)
        if str(self.context.server_url) != ORIGIN + '/mcp':
            return result
        return prepare_token_request(stamp(result), getattr(self, '_voicenotes_omitted_callback', None))

    def announce(url, *args, **kwargs):
        p = urlsplit(url)
        if not active.get() or p.scheme + '://' + p.netloc != ORIGIN or p.path != '/oauth/authorize':
            return original_announce(url, *args, **kwargs)
        if 'redirect_uri' in dict(parse_qsl(p.query)):
            raise ValueError('Authorization callback adaptation was not applied.')
        if not open_browser(url):
            raise RuntimeError('Browser could not be opened; try --browser chrome on macOS.')

    cls._perform_authorization = authorize
    cls._prepare_token_request = token
    provider_module.stamp_default_user_agent = stamp
    oauth_module._announce_authorization_url = announce
    try:
        yield
    finally:
        cls._perform_authorization = original_auth
        cls._prepare_token_request = original_token
        provider_module.stamp_default_user_agent = original_stamp
        oauth_module._announce_authorization_url = original_announce


ORIGIN = 'https://api.voicenotes.com'


def prepare_token_request(request, registered_redirect=None):
    """Omit a redundant redirect only after the matching authorization omitted it."""
    if (not registered_redirect or str(request.url) != ORIGIN + '/oauth/token'
            or request.method != 'POST'):
        return request
    if not request.headers.get('content-type', '').startswith('application/x-www-form-urlencoded'):
        raise ValueError('Unexpected token request encoding.')
    pairs = parse_qsl(request.content.decode('utf-8'), keep_blank_values=True)
    if dict(pairs).get('grant_type') != 'authorization_code':
        return request
    validate_callback(registered_redirect)
    if [v for k, v in pairs if k == 'redirect_uri'] != [registered_redirect]:
        raise ValueError('Token callback differs from authorization registration.')
    body = urlencode([(k, v) for k, v in pairs if k != 'redirect_uri']).encode('utf-8')
    headers = {k: v for k, v in request.headers.items() if k.lower() != 'content-length'}
    return type(request)(request.method, request.url, content=body, headers=headers,
                         extensions=request.extensions.copy())


def validate_callback(value):
    """Accept one complete local callback, never a proxy or wildcard."""
    p = urlsplit(value)
    if (p.scheme != 'http' or p.hostname not in ('127.0.0.1', 'localhost')
            or not p.port or p.username or p.password or p.path != '/callback'
            or p.query or p.fragment or p.netloc != f'{p.hostname}:{p.port}'):
        raise ValueError('Expected one complete registered loopback callback.')
    return value


def authorization_url(url, registered):
    """Rely on the single DCR redirect while retaining state and PKCE."""
    p = urlsplit(url)
    if p.scheme + '://' + p.netloc != ORIGIN or p.path != '/oauth/authorize' or p.fragment:
        raise ValueError('Unexpected authorization endpoint.')
    if len(registered) != 1:
        raise ValueError('Exactly one registered callback is required.')
    callback = validate_callback(str(registered[0]))
    pairs = parse_qsl(p.query, keep_blank_values=True)
    redirects = [v for k, v in pairs if k == 'redirect_uri']
    if redirects != [callback]:
        raise ValueError('Authorization callback does not match registration.')
    return urlunsplit((p.scheme, p.netloc, p.path,
                       urlencode([(k, v) for k, v in pairs if k != 'redirect_uri']), ''))
