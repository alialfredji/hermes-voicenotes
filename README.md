# Hermes × Voicenotes

## What it does

Connects Hermes to your Voicenotes account so you can:
- Search and browse your notes.
- Read voice-note and meeting transcripts.
- Create text notes.

You sign in through your browser. No API key needed. Existing working logins are preserved.

## How to use it

You need Hermes installed and Python 3.10+. Run these in Terminal on the computer running Hermes:

```bash
git clone https://github.com/alialfredji/hermes-voicenotes.git
cd hermes-voicenotes
python3 connect.py
```

Click **Continue** in the browser if prompted. After the command confirms the connection, start a new Hermes chat and try:

> Search my Voicenotes for ideas about my next project.

To check the connection later:

```bash
python3 connect.py --check
```

Tested with an existing login on macOS / Hermes 0.22.3. Fresh-login support is experimental; this is an unofficial connector.
