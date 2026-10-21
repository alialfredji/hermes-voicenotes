import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def load_cli(self):
        spec = importlib.util.spec_from_file_location('connect_cli', ROOT / 'connect.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_help_is_dependency_free_and_check_flags_are_exclusive(self):
        result = subprocess.run([sys.executable, str(ROOT / 'connect.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--doctor', result.stdout)
        self.assertIn('--check', result.stdout)
        self.assertIn('--reauth', result.stdout)
        result = subprocess.run([sys.executable, str(ROOT / 'connect.py'), '--check', '--reauth'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_bootstrap_never_echoes_internal_output_or_exception(self):
        cli = self.load_cli()
        secret = 'https://api.voicenotes.com/oauth/authorize?code=example-private'
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli.subprocess, 'run', side_effect=OSError(secret)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(['--doctor']), 2)
        self.assertNotIn(secret, out.getvalue() + err.getvalue())
        launch = "import sys,runpy; runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
        results = [subprocess.CompletedProcess([], 0, json.dumps(['python', '-I', '-c', launch]), secret),
                   subprocess.CompletedProcess([], 1, secret, secret)]
        with patch.object(cli.subprocess, 'run', side_effect=results), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(['--doctor']), 2)
        self.assertNotIn(secret, out.getvalue() + err.getvalue())

    def test_reauth_requires_exact_destructive_confirmation(self):
        cli = self.load_cli()
        with patch('builtins.input', return_value='no'), patch.object(cli.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['--reauth']), 1)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
