"""
Vercel Python entrypoint.

Exposes a top-level `app` object discoverable by Vercel without changing
existing onboarding application logic.
"""

from onboarding.app import app

