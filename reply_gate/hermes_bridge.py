"""Hermes ingress policy; the host owns authorization, ordering and persistence."""
import asyncio
from dataclasses import fields
import json
import logging
import time

from .config import Settings
from .engine import GateDecision, ReplyGate

logger = logging.getLogger('hermes.plugins.hermes-jev-reply-gate')


def profile_secret():
    # Lazy import keeps the engine usable without Hermes. The host invokes us
    # inside the event's owning runtime/profile scope, never the ambient profile.
    from agent.secret_scope import get_secret
    return get_secret('TYPESAFE_API_KEY')


def read_settings(ctx):
    defaults = Settings()
    mapping = {field.name: ctx.get_config(field.name, getattr(defaults, field.name))
               for field in fields(Settings) if field.name not in ('group_ids', 'model')}
    mapping['model_version'] = ctx.get_config('model_version', defaults.model)
    mapping['telegram'] = ctx.get_config('telegram', {})
    return Settings.from_mapping(mapping)


class IngressPolicy:
    def __init__(self, ctx, *, gate=None):
        self.ctx = ctx
        self.gate = gate or ReplyGate()
        self.active = True
        self._occupied = set()
        read_settings(ctx)  # Refuse invalid configuration before registration.

    def close(self):
        # Host unregisters this generation and owns task cancellation. Retained
        # calls are inert; request-local clients always close on return/cancel.
        self.active = False

    def _eligible(self, request, settings):
        return (self.active and settings.enabled and request.platform == 'telegram'
                and request.chat_id in settings.group_ids and request.reply_expected is False
                and isinstance(request.text, str) and bool(request.text.strip()))

    async def __call__(self, request):
        started = time.monotonic()
        settings = Settings()
        decision = GateDecision('allow', 'ineligible')
        occupied = False
        try:
            settings = read_settings(self.ctx)
            if self._eligible(request, settings):
                if request.session_key in self._occupied or len(self._occupied) >= settings.max_sessions:
                    decision = GateDecision('allow', 'capacity')
                else:
                    self._occupied.add(request.session_key)
                    occupied = True
                    async with asyncio.timeout(settings.timeout_seconds):
                        key = profile_secret()
                        if not isinstance(key, str) or not key.strip():
                            decision = GateDecision('allow', 'missing_key')
                        else:
                            decision = await self.gate.evaluate(text=request.text, history=request.history,
                                                                settings=settings, api_key=key)
                            current = read_settings(self.ctx)
                            if current != settings or not self._eligible(request, current):
                                decision = GateDecision('allow', 'settings_changed')
        except TimeoutError:
            decision = GateDecision('allow', 'timeout')
        except ValueError:
            decision = GateDecision('allow', 'invalid_settings')
        except Exception:
            # Never log repr(exception): it can carry an API body, content or key.
            decision = GateDecision('allow', 'internal_error')
        finally:
            if occupied:
                self._occupied.discard(request.session_key)
        logger.info(json.dumps({
            'mode': settings.mode, 'model': settings.model, 'action': decision.action,
            'reason': decision.reason,
            'probabilities': dict(decision.classification.probabilities) if decision.classification else None,
            'elapsed_ms': round((time.monotonic() - started) * 1000, 2),
        }, sort_keys=True))
        return {'action': decision.action}


def register(ctx):
    if not callable(getattr(ctx, 'register_ingress_policy', None)):
        raise RuntimeError(
            'hermes-jev-reply-gate requires Hermes with PluginContext.register_ingress_policy; '
            'install the generic ingress extension. Unmodified Hermes 0.21.5 is unsupported.'
        )
    if not callable(getattr(ctx, 'on_unload', None)):
        raise RuntimeError('hermes-jev-reply-gate requires PluginContext.on_unload')
    policy = IngressPolicy(ctx)
    ctx.on_unload(policy.close)
    ctx.register_ingress_policy(policy.__call__)
