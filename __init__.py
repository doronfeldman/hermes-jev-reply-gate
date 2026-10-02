"""Hermes directory-plugin entrypoint."""


def register(ctx):
    from .reply_gate import register as register_plugin
    return register_plugin(ctx)
