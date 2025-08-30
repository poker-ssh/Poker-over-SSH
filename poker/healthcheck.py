"""Healthcheck service for Poker-over-SSH

Runs a small HTTP server on HEALTHCHECK_PORT that returns JSON status for an SSH connect
probe to SERVER_HOST:SERVER_PORT. 
Interval is configurable via HEALTHCHECK_INTERVAL (seconds).
"""
import os
import asyncio
import logging
import time
import json
from typing import Dict, Any

try:
    import asyncssh
except Exception:  # pragma: no cover
    asyncssh = None

from aiohttp import web
from .database import get_database


def load_env():
    env = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    # overlay with REAL env
    for k in ('SERVER_HOST', 'SERVER_PORT', 'HEALTHCHECK_PORT', 'HEALTHCHECK_INTERVAL'):
        if os.getenv(k) is not None:
            env[k] = os.getenv(k)
    return env


class SSHProbe:
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    async def probe(self) -> Dict[str, Any]:
        """Attempt to open an SSH transport and return status info."""
        result: Dict[str, Any] = {
            'host': self.host,
            'port': self.port,
            'tcp_connect': False,
            'ssh_ok': False,
            'error': None,
        }

        if asyncssh is None:
            result['error'] = 'asyncssh not installed'

        # First, try a raw TCP connect - this is a simpler
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=self.timeout)
            result['tcp_connect'] = True
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        except Exception as e:
            # Could not open TCP connection; return 
            result['error'] = f'tcp_connect_failed: {e}'
            return result

        # If asyncssh is available, try an SSH handshake to validate SSH service
        if asyncssh is not None:
            try:
                conn = await asyncio.wait_for(asyncssh.connect(self.host, port=self.port, username='healthcheck', known_hosts=None), timeout=self.timeout)
                # if we get a connection object, handshake succeeded 
                result['ssh_ok'] = True
                conn.close()
                try:
                    await conn.wait_closed()
                except Exception:
                    pass
            except Exception as e:
                # SSH-level error - report but keep tcp_connect True
                result['error'] = str(e)

        return result


class HealthcheckService:
    def __init__(self, host: str = '0.0.0.0'):
        env = load_env()
        self.server_host = env.get('SERVER_HOST', 'localhost')
        self.server_port = int(env.get('SERVER_PORT', '22222'))
        self.port = int(env.get('HEALTHCHECK_PORT', '22223'))
        self.interval = int(env.get('HEALTHCHECK_INTERVAL', '60'))
        self.host = host
        self._latest: Dict[str, Any] = {
            'status': 'unknown',
            'last_probe': None,
            'probe': None,
        }
        # History configuration - store recent probe results for UI/metrics
        # HISTORY_SIZE controls how many entries to keep (default ~ 1440 = 24h at 1m interval)
        self.history_size = int(env.get('HEALTHCHECK_HISTORY_SIZE', '1440'))
        # Optional file to persist history across restarts
        self.history_file = env.get('HEALTHCHECK_HISTORY_FILE')
        self.history: list[Dict[str, Any]] = []
        if self.history_file:
            try:
                with open(self.history_file, 'r') as hf:
                    self.history = json.load(hf) or []
            except Exception:
                logging.exception('Failed to load history file, starting with empty history')
        self._probe = SSHProbe(self.server_host, self.server_port)
        self._task: asyncio.Task | None = None
        # Try to get database manager if initialized
        try:
            self._db = get_database()
        except Exception:
            self._db = None
        # CORS origin config (default allow all)
        self.cors_origin = env.get('HEALTHCHECK_CORS_ORIGIN', '*')

    async def _background_probe(self):
        while True:
            try:
                res = await self._probe.probe()
                self._latest['probe'] = res
                # use epoch seconds for last_probe
                self._latest['last_probe'] = int(time.time())

                tcp_ok = bool(res.get('tcp_connect'))
                ssh_ok = bool(res.get('ssh_ok'))
                if tcp_ok and ssh_ok:
                    self._latest['status'] = 'ok'
                elif tcp_ok and not ssh_ok:
                    # Service reachable on TCP but SSH handshake failed/unauthenticated
                    self._latest['status'] = 'warn'
                else:
                    self._latest['status'] = 'fail'

                # Record history via DB if available, else fall back to in-memory/file
                if self._db and hasattr(self._db, 'log_health_entry'):
                    try:
                        getattr(self._db, 'log_health_entry')(self._latest['last_probe'], self._latest['status'], res)
                    except Exception:
                        logging.exception('Failed to write health entry to database')
                else:
                    entry = {
                        'ts': self._latest['last_probe'],
                        'status': self._latest['status'],
                        'probe': res,
                    }
                    self.history.append(entry)
                    # trim history
                    if len(self.history) > self.history_size:
                        self.history = self.history[-self.history_size:]
                    # persist if configured
                    if self.history_file:
                        try:
                            with open(self.history_file, 'w') as hf:
                                json.dump(self.history, hf)
                        except Exception:
                            logging.exception('Failed to persist history to file')

            except Exception as e:
                logging.exception('Healthcheck probe failed')
                self._latest['status'] = 'error'
                self._latest['probe'] = {'error': str(e)}

                # record failure in history as well
                if self._db and hasattr(self._db, 'log_health_entry'):
                    try:
                        getattr(self._db, 'log_health_entry')(int(time.time()), 'error', {'error': str(e)})
                    except Exception:
                        logging.exception('Failed to write error health entry to database')
                else:
                    entry = {
                        'ts': int(time.time()),
                        'status': 'error',
                        'probe': {'error': str(e)},
                    }
                    self.history.append(entry)
                    if len(self.history) > self.history_size:
                        self.history = self.history[-self.history_size:]
                    if self.history_file:
                        try:
                            with open(self.history_file, 'w') as hf:
                                json.dump(self.history, hf)
                        except Exception:
                            logging.exception('Failed to persist history to file')

            await asyncio.sleep(self.interval)

    async def status_handler(self, request):
        return web.json_response(self._latest)

    async def history_handler(self, request):
        """Return recent probe history. Optional query param `limit` to cap results."""
        try:
            limit = int(request.query.get('limit', '0'))
        except Exception:
            limit = 0
        # If DB is available, pull from DB; otherwise use in-memory history
        if self._db and hasattr(self._db, 'get_health_history'):
            try:
                if limit <= 0:
                    limit = self.history_size
                data = getattr(self._db, 'get_health_history')(limit)
                return web.json_response({'history': data, 'count': len(data)})
            except Exception:
                logging.exception('Failed to fetch history from database')
                # fall through to in-memory

        if limit <= 0:
            data = list(self.history)
        else:
            data = list(self.history[-limit:])

        return web.json_response({'history': data, 'count': len(data)})

    async def start(self):
        # start background probe
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._background_probe())

        # CORS middleware
        @web.middleware
        async def cors_middleware(request, handler):
            # Handle preflight
            if request.method == 'OPTIONS':
                resp = web.Response(text='')
            else:
                resp = await handler(request)

            origin = request.headers.get('Origin')
            allowed = self.cors_origin
            # If allowed is '*' allow any; otherwise echo the Origin if it matches allowed
            if allowed == '*':
                resp.headers['Access-Control-Allow-Origin'] = '*'
            else:
                # If allowed contains the request origin or is exactly the origin, set it; otherwise leave unset
                if origin and (allowed == origin or origin == allowed):
                    resp.headers['Access-Control-Allow-Origin'] = origin

            resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
            # Allow credentials only when not wildcard
            if resp.headers.get('Access-Control-Allow-Origin') and resp.headers['Access-Control-Allow-Origin'] != '*':
                resp.headers['Access-Control-Allow-Credentials'] = 'true'

            return resp

        app = web.Application(middlewares=[cors_middleware])
        app.router.add_get('/health', self.status_handler)
        app.router.add_get('/history', self.history_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=self.host, port=self.port)
        await site.start()
        logging.info(f'Healthcheck HTTP server listening on {self.host}:{self.port}, probing {self.server_host}:{self.server_port} every {self.interval}s')


async def start_healthcheck_in_background():
    svc = HealthcheckService()
    await svc.start()


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    asyncio.run(HealthcheckService(host=args.host).start())
