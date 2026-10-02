# Experimental installation

This plugin requires the **unreleased generic Hermes ingress extension** described in
[compatibility](compatibility.md). Unmodified Hermes 0.21.5 cannot load it. Do not install
it into a production gateway until the matching host implementation and review are available.

Use the Python environment that runs the amended Hermes gateway:

```sh
python -m pip install /path/to/hermes-jev-reply-gate
```

The wheel registers `hermes_agent.plugins` entry point `hermes-jev-reply-gate`.
Alternatively, copy this repository into the owning profile's
`plugins/hermes-jev-reply-gate` directory and install its declared `httpx>=0.27,<1`
dependency in the gateway environment. The directory manifest and root `register(ctx)`
entrypoint use relative imports and do not require a separate installed copy.

Store `TYPESAFE_API_KEY` using Hermes's normal **owning profile** secret mechanism
(the profile `.env` or its supported secret provider). Never put it in plugin settings.
The callback reads `agent.secret_scope.get_secret` under the host's resolved profile
scope. It does not read the process environment or a custom secret file itself.

Merge this configuration into that profile's `config.yaml`:

```yaml
plugins:
  enabled:
    - hermes-jev-reply-gate
  entries:
    hermes-jev-reply-gate:
      enabled: true
      settings:
        enabled: false
        mode: shadow
        model_version: jev-1.13.0
        timeout_seconds: 1.0
        ignore_probability: 0.95
        context_messages: 12
        context_characters: 6000
        max_sessions: 128
        telegram:
          group_ids: []
```

Add the intended numeric group IDs and change `settings.enabled` to `true` to begin
shadow evaluation. Empty groups classify nothing. Preserve the profile's existing
plugin enable list, Telegram permissions and participation settings. Loading this plugin
does not grant sender access or enable general group participation.

`model_version` replaces the original design's `model` field: Hermes reserves the
plugin-relative key `model`. Only `jev-1.13.0` is accepted. Modes must be `shadow` or
`suppress`; threshold must be finite and in `(0.5, 1]`; timeout must be positive and
finite; context/session limits must be positive integers (booleans are rejected).
Host snapshot caps are 12 complete entries and 6000 content characters; larger plugin
context settings do not expand those caps. The host can impose an earlier arrival deadline.
Invalid initial settings prevent registration. Invalid runtime settings allow normal handling.

Restart the gateway after installing/updating code or secrets. Inspect the profile's
Hermes logs for load errors and structured decisions from
`hermes.plugins.hermes-jev-reply-gate`. `would_ignore` in shadow means a proposed ignore;
it is not a suppressed message or a correctness measurement. Missing credentials allow
normal processing. No startup network request is made.

For rollback, set `settings.enabled: false`. Each callback re-reads settings before
classification and after the await. Disable or unload the plugin and restart for code or
credential rollback. Hermes owns registry generation invalidation; retained callbacks
also become inert on unload. Existing observations stay in the canonical transcript.

Suppression is experimental and requires a separately evaluated, authorized rollout.
No live shadow deployment or suppression deployment was performed during development.
