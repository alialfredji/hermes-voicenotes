"""Offline regression tests. Never touch a real Hermes profile or network."""
import importlib
import json
import unittest


class BootstrapTests(unittest.TestCase):
    def test_runtime_bootstrap_removes_its_script_argument(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from connector import runtime_command
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            script = Path(folder) / 'probe.py'
            script.write_text('import json,sys; print(json.dumps(sys.argv[1:]))')
            launch = "import sys,runpy; runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
            command = runtime_command(json.dumps([sys.executable, '-I', '-c', launch]), script, ['--doctor'])
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), ['--inside-runtime', '--doctor'])

    def test_runtime_launcher_is_adapted_without_guessing_paths(self):
        c = importlib.import_module('connector')
        launch = "import runpy; runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
        command = c.runtime_command(json.dumps(['python', '-I', '-c', launch]), '/repo/connect.py', ['--doctor'])
        self.assertEqual(command[:3], ['python', '-I', '-c'])
        self.assertIn("runpy.run_path(sys.argv.pop(1), run_name='__main__')", command[3])
        self.assertEqual(command[4:], ['/repo/connect.py', '--inside-runtime', '--doctor'])
        for value in ['{}', '[]', '["python", "-m", "hermes_cli.main"]', '["python", 1]']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                c.runtime_command(value, '/repo/connect.py', [])


class FakeAdapter:
    def __init__(self, config=None, cached=True, connected=True):
        self.entry = config if config is not None else {'url': 'https://api.voicenotes.com/mcp', 'auth': 'oauth', 'enabled': True}
        self.cached, self.connected, self.calls = cached, connected, []
    def config(self):
        self.calls.append('config')
        return self.entry.copy() if self.entry is not None else None
    def has_tokens(self):
        self.calls.append('tokens')
        return self.cached
    def check(self, cfg):
        self.calls.append('check')
        return 4 if self.connected else 0
    def register(self):
        self.calls.append('register')
        self.entry = {'url': 'https://api.voicenotes.com/mcp', 'auth': 'oauth', 'enabled': True}
        self.cached = True
    def login(self, cfg, reauth=False):
        self.calls.append('reauth' if reauth else 'login')
        self.cached, self.connected = True, True
        return True


class PolicyTests(unittest.TestCase):
    def test_new_install_registers_then_reads_back_and_checks(self):
        from connector import connect
        a = FakeAdapter(cached=False)
        a.entry = None
        self.assertEqual(connect(a)[0], 0)
        self.assertEqual(a.calls, ['config', 'tokens', 'register', 'config', 'tokens', 'check'])
        a = FakeAdapter(cached=False)
        a.entry = None
        self.assertEqual(connect(a, mode='check')[0], 1)
        self.assertEqual(a.calls, ['config', 'tokens'])

    def test_existing_missing_tokens_logs_in_without_clearing(self):
        from connector import connect
        a = FakeAdapter(cached=False)
        self.assertEqual(connect(a)[0], 0)
        self.assertEqual(a.calls, ['config', 'tokens', 'login', 'tokens', 'check'])

    def test_explicit_reauth_checks_before_replacing_and_verifies_after(self):
        from connector import connect
        a = FakeAdapter()
        self.assertEqual(connect(a, reauth=True)[0], 0)
        self.assertEqual(a.calls, ['config', 'tokens', 'check', 'reauth', 'tokens', 'check'])

    def test_disabled_connection_requires_manual_enable_without_config_write(self):
        from connector import connect
        a = FakeAdapter()
        a.entry['enabled'] = False
        code, message = connect(a)
        self.assertEqual(code, 3)
        self.assertIn('enable', message)
        self.assertEqual(a.calls, ['config', 'tokens', 'check'])

    def test_failed_cached_connection_never_triggers_login(self):
        from connector import connect
        for mode in ['connect', 'check']:
            a = FakeAdapter(connected=False)
            code, message = connect(a, mode=mode)
            self.assertEqual(code, 1)
            self.assertIn('--reauth', message)
            self.assertEqual(a.calls, ['config', 'tokens', 'check'])

    def test_doctor_is_offline_and_conflicting_config_is_rejected(self):
        from connector import connect
        a = FakeAdapter()
        self.assertEqual(connect(a, mode='doctor')[0], 0)
        self.assertEqual(a.calls, ['config', 'tokens'])
        for cfg in [{'url': 'https://evil.test/mcp', 'auth': 'oauth'},
                    {'url': 'https://api.voicenotes.com/mcp', 'auth': 'header'},
                    {'url': 'https://api.voicenotes.com/mcp', 'auth': 'oauth', 'oauth': {'client_id': 'example'}}]:
            a = FakeAdapter(config=cfg)
            self.assertEqual(connect(a)[0], 2)
            self.assertEqual(a.calls, ['config'])

    def test_healthy_connection_is_checked_before_any_change(self):
        from connector import connect
        a = FakeAdapter()
        code, message = connect(a)
        self.assertEqual(code, 0)
        self.assertIn('4 tools', message)
        self.assertEqual(a.calls, ['config', 'tokens', 'check'])


if __name__ == '__main__':
    unittest.main()
