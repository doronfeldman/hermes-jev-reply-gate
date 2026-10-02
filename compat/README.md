# Matching Hermes host extension

The standalone Jev plugin needs an additive generic ingress surface absent from stock
Hermes 0.21.5. This directory carries the exact reviewed host change, including its tests,
so installing this project does not depend on an unpublished local checkout.

- Base: `34f8ec3b407e50bad3ae27e4cd79d65212061356` (Hermes 0.21.5).
- Host change: `abf9fb542` (`feat/shared-ingress-gate`).
- Artifact: [`hermes-0.21.5-ingress.patch`](hermes-0.21.5-ingress.patch).

Apply only to a clean checkout at that base, on a dedicated branch. Back up runtime
configuration and retain the previous checkout before deploying. Do not apply blindly to
a newer release; check its native capabilities and rerun the integration tests first.

```sh
git switch -c feature/shared-ingress-gate 34f8ec3b407e50bad3ae27e4cd79d65212061356
git apply --check /path/to/hermes-jev-reply-gate/compat/hermes-0.21.5-ingress.patch
git am /path/to/hermes-jev-reply-gate/compat/hermes-0.21.5-ingress.patch
```

The patch adds `PluginContext.register_ingress_policy`, normalized Telegram targeting
metadata, host-owned pre-busy ordering, read-only snapshots, idempotent transcript
observation and standard shutdown recovery. It contains no Jev-specific core behavior.
Its embedded developer guide documents the host contract.

This compatibility patch is an experiment, not an upstream Hermes release or an assurance
of compatibility with future updates. A plugin-only installation on an unmodified host
refuses activation. Disable the plugin before reverting the host patch; preserve existing
transcript data and recovery files.
