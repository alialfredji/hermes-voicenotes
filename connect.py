#!/usr/bin/env python3
"""Guided Voicenotes connector. Run this in the shell on the Hermes host."""
import argparse
import contextlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

# Hermes' isolated Python deliberately does not add this script's directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from connector import runtime_command


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid arguments. Run python3 connect.py --help.\n')


@contextlib.contextmanager
def quiet():
    """Never forward internal helper output, URLs, callback values, or logging."""
    level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    with open(os.devnull, 'w') as sink:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            try:
                yield
            finally:
                logging.disable(level)


def main(argv=None):
    parser = Parser(description='Connect Voicenotes to Hermes using its own OAuth storage and runtime.',
                    epilog='Run on the same computer as your browser. No API key or extra pip install needed.')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='verify saved access without login, refresh, or config changes')
    modes.add_argument('--doctor', action='store_true', help='offline runtime/config compatibility diagnosis; no network')
    modes.add_argument('--reauth', action='store_true', help='explicitly clear and replace saved Voicenotes OAuth state (confirmation required)')
    parser.add_argument('--browser', choices=['default', 'chrome'], default='default', help='authorization browser (Chrome option requires macOS)')
    parser.add_argument('--inside-runtime', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.inside_runtime:
        try:
            with quiet():
                from hermes_runtime import execute
                code, message = execute(args)
        except BaseException:
            code, message = 2, 'Hermes runtime operation failed. Run --doctor; check Hermes/MCP compatibility. Internal output withheld for credential safety.'
        print(json.dumps({'code': code, 'message': message}))
        return code
    if args.reauth:
        try:
            answer = input('This clears saved Voicenotes tokens and client registration before login. Type REAUTHORIZE to continue: ')
        except (EOFError, KeyboardInterrupt):
            answer = ''
        if answer != 'REAUTHORIZE':
            print('Cancelled. Nothing changed.')
            return 1
    if not args.doctor and not args.check:
        print('Checking saved authorization first. If setup is needed, approve Voicenotes in the browser on this computer (up to 15 minutes).', flush=True)
    try:
        found = subprocess.run(['hermes', '--print-runtime-command'], capture_output=True, text=True, timeout=30, check=True)
        forwarded = []
        for flag in ('check', 'doctor', 'reauth'):
            if getattr(args, flag):
                forwarded.append('--' + flag)
        forwarded.extend(['--browser', args.browser])
        command = runtime_command(found.stdout, Path(__file__).resolve(), forwarded)
        result = subprocess.run(command, capture_output=True, text=True, timeout=1050)
        payload = json.loads(result.stdout)
        if (not isinstance(payload, dict) or type(payload.get('code')) is not int
                or payload['code'] not in (0, 1, 2, 3)
                or not isinstance(payload.get('message'), str)
                or result.returncode != payload['code']):
            raise ValueError('Invalid runtime response')
    except KeyboardInterrupt:
        print('Cancelled. If you explicitly requested --reauth, old authorization may already have been cleared.')
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Could not use the Hermes runtime. Ensure hermes is installed with MCP support and on PATH; run hermes --print-runtime-command. Internal output withheld for credential safety.')
        return 2
    print(payload['message'])
    if payload['code'] == 0 and not args.doctor:
        print('Start a new Hermes session, then ask it to list your latest Voicenotes. Tool discovery is verified; note retrieval has not been tested here.')
    return payload['code']


if __name__ == '__main__':
    raise SystemExit(main())
