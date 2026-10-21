# Security

Never include tokens, client secrets, callback URLs/codes, state, PKCE values, authorization URLs, private notes, or your Hermes configuration in reports. The connector intentionally withholds internal stdout/stderr and exception text.

Report only the public error message, operating system, Hermes version, Python version, and whether `--doctor` succeeds. For sensitive bugs, use a private channel with the maintainer rather than a public issue; no dedicated security reporting inbox is established here.

`--doctor` is offline. `--check` uses the saved access token directly, without refresh or OAuth callbacks. Setup and explicitly confirmed `--reauth` can write credentials through Hermes. `--reauth` may disconnect you even if the subsequent login fails. Keep the browser and callback listener on the same machine.

Do not expose the loopback callback listener through a public tunnel, paste callback codes, or use a credential-rewriting proxy. This wrapper does not relax state/PKCE/issuer checks and only omits a redundant redirect after checking the single registered callback.
