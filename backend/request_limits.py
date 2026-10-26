"""Instance-local simulation limit for the single-instance staging service.

Multi-instance production requires a shared gateway/Redis limiter.
"""
from collections import deque
from threading import Lock
from time import monotonic
from fastapi import HTTPException
_lock=Lock()
_requests={}


def allow_action(identity,scope,label='requests'):
    now=monotonic()
    with _lock:
        if len(_requests)>10000:
            for key in [k for k,v in _requests.items() if not v or v[-1]<now-60]: del _requests[key]
            if len(_requests)>10000: raise HTTPException(503,'Request capacity reached. Retry shortly.')
        queue=_requests.setdefault((identity,scope),deque())
        while queue and queue[0]<now-60: queue.popleft()
        if len(queue)>=20: raise HTTPException(429,f'At most 20 {label} per minute. Please wait.',headers={'Retry-After':'60'})
        queue.append(now)


def allow_simulation(identity,organization_id):
    allow_action(identity,'simulation:'+organization_id,'simulations')
