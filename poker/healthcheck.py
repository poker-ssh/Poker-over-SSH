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
        # History thingy removed (not needed anymore)
        self._probe = SSHProbe(self.server_host, self.server_port)
        self._task: asyncio.Task | None = None
        # Try to get database manager if initialized
        try:
            self._db = get_database()
        except Exception:
            self._db = None

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

                # Only log to DB if available, no history
                if self._db and hasattr(self._db, 'log_health_entry'):
                    try:
                        getattr(self._db, 'log_health_entry')(self._latest['last_probe'], self._latest['status'], res)
                    except Exception:
                        logging.exception('Failed to write health entry to database')

            except Exception as e:
                logging.exception('Healthcheck probe failed')
                self._latest['status'] = 'error'
                self._latest['probe'] = {'error': str(e)}

                # Only log to DB if available, no history
                if self._db and hasattr(self._db, 'log_health_entry'):
                    try:
                        getattr(self._db, 'log_health_entry')(int(time.time()), 'error', {'error': str(e)})
                    except Exception:
                        logging.exception('Failed to write error health entry to database')

            await asyncio.sleep(self.interval)

    async def status_handler(self, request):
        return web.json_response(self._latest)

    # history_handler removed

    async def start(self):
        # start background probe
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._background_probe())

        app = web.Application()
        app.router.add_get('/health', self.status_handler)
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
    
    # Suppress AsyncSSH's verbose window change messages
    asyncssh_logger = logging.getLogger('asyncssh')
    asyncssh_logger.setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    asyncio.run(HealthcheckService(host=args.host).start())
