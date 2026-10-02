"""Transport-independent Jev reply gate."""


def register(ctx):
    from .hermes_bridge import register as register_plugin
    return register_plugin(ctx)
