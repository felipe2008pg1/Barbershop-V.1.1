"""
Rate limiting configuration, shared across routers.

Uses slowapi (a thin wrapper around the well-established `limits`
library) keyed by client IP address. This protects public-facing
endpoints — booking, lookup, login — from being spammed or brute-forced,
without requiring any external infrastructure like Redis for a
single-process deployment.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
