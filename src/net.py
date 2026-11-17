"""Co-op networking: a tiny Supabase Realtime (Phoenix channels) client.

Everything goes over one websocket as "broadcast" messages on a channel
named after the room code. No database tables are needed.

Built on the standard library only (socket + ssl), so the .exe needs no
extra packages. The socket runs on its own thread; the game polls
`Net.poll()` once a frame for messages and sends with `Net.send()`.

Set MOOSE_RELAY=ws://127.0.0.1:PORT to use a local test server instead.
"""
import base64
import json
import os
import random
import socket
import ssl
import string
import struct
import threading
import time
import queue
from urllib.parse import urlparse, quote

# Your Supabase project. The anon/publishable key is meant to ship inside apps.
SUPABASE_URL = "https://ahjhfwucsivhzhqcjyau.supabase.co"
SUPABASE_KEY = "sb_publishable_MUfA7Qcl32e-XmzP9mYYGg_7AKqOzBf"

MAX_PLAYERS = 4


def new_code():
    return ''.join(random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(5))


def new_pid():
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))


def configured():
    return bool(os.environ.get('MOOSE_RELAY') or (SUPABASE_URL and SUPABASE_KEY))


# ---------------------------------------------------------------------- a minimal websocket client
class WebSocket:
    def __init__(self, url, timeout=10.0):
        u = urlparse(url)
        secure = u.scheme == 'wss'
        host = u.hostname
        port = u.port or (443 if secure else 80)
        raw = socket.create_connection((host, port), timeout=timeout)
        if secure:
            raw = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        self.sock = raw
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path or '/'
        if u.query:
            path += '?' + u.query
        req = ("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nUser-Agent: MooseMan\r\n\r\n"
               % (path, host, key))
        self.sock.sendall(req.encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError('handshake closed')
            head += chunk
        head, self.buf = head.split(b'\r\n\r\n', 1)
        status = head.split(b'\r\n', 1)[0]
        if b' 101' not in status:
            raise ConnectionError('handshake refused: %s' % status.decode(errors='replace'))
        self.sock.settimeout(None)
        self.wlock = threading.Lock()

    def send_text(self, text):
        data = text.encode('utf-8')
        n = len(data)
        head = bytearray([0x81])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack('>H', n)
        else:
            head.append(0x80 | 127)
            head += struct.pack('>Q', n)
        mask = os.urandom(4)
        head += mask
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(data))
        with self.wlock:
            self.sock.sendall(bytes(head) + masked)

    def _send_ctrl(self, op, payload=b''):
        mask = os.urandom(4)
        frame = bytes([0x80 | op, 0x80 | len(payload)]) + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        with self.wlock:
            self.sock.sendall(frame)

    def _need(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError('closed')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv_text(self):
        """Blocks until a whole text message arrives. Returns None on close."""
        parts = []
        while True:
            b0, b1 = self._need(2)
            fin, op = b0 & 0x80, b0 & 0x0F
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack('>H', self._need(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._need(8))[0]
            mask = self._need(4) if b1 & 0x80 else None
            data = self._need(n)
            if mask:
                data = bytes(b ^ mask[i & 3] for i, b in enumerate(data))
            if op == 0x8:
                return None
            if op == 0x9:
                self._send_ctrl(0xA, data)
                continue
            if op == 0xA:
                continue
            parts.append(data)
            if fin:
                return b''.join(parts).decode('utf-8', errors='replace')

    def close(self):
        try:
            self._send_ctrl(0x8)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------- one room = one Realtime channel
class Net:
    """Connects to a room. `send(kind, data)` broadcasts to everyone else in it;
    `poll()` returns [(kind, data, from_pid), ...] received since the last poll."""

    def __init__(self, code, pid):
        self.code = code
        self.pid = pid
        self.inbox = queue.Queue()
        self.ws = None
        self.ok = False            # joined the channel
        self.error = ''
        self.closed = False
        self.ref = 0
        self.topic = 'realtime:mooseman-' + code.lower()
        self.sent = 0
        self.dead = False          # gave up for good
        self.refused = False
        self.ever_ok = False
        self.reconnects = 0
        self.drops = []
        self.pending = []
        self.plock = threading.Lock()
        self.rlock = threading.Lock()
        t = threading.Thread(target=self._run, name='net', daemon=True)
        t.start()

    def _url(self):
        relay = os.environ.get('MOOSE_RELAY')
        if relay:
            return relay.rstrip('/') + '/realtime/v1/websocket?vsn=1.0.0'
        base = SUPABASE_URL.rstrip('/').replace('https://', 'wss://').replace('http://', 'ws://')
        return base + '/realtime/v1/websocket?apikey=%s&vsn=1.0.0' % quote(SUPABASE_KEY)

    def _raw(self, topic, event, payload):
        with self.rlock:
            self.ref += 1
            ref = str(self.ref)
        msg = {'topic': topic, 'event': event, 'payload': payload, 'ref': ref}
        if topic == self.topic:
            msg['join_ref'] = '1'
        self.ws.send_text(json.dumps(msg, separators=(',', ':')))

    def _connect(self):
        self.ws = WebSocket(self._url())
        cfg = {'config': {'broadcast': {'self': False, 'ack': False}, 'presence': {'key': ''}, 'private': False}}
        if SUPABASE_KEY.startswith('eyJ'):
            cfg['access_token'] = SUPABASE_KEY
        self.ref = 0
        self._raw(self.topic, 'phx_join', cfg)

    def _run(self):
        """Connect, and if the line drops, quietly reconnect to the same room."""
        fails = 0
        hb = threading.Thread(target=self._heartbeat, name='net-hb', daemon=True)
        hb.start()
        while not self.closed:
            try:
                self._connect()
            except Exception as e:
                fails += 1
                self.drops.append('connect: %s' % e.__class__.__name__)
                if fails >= (3 if not self.ever_ok else 8):
                    self.error = 'could not connect (%s)' % e.__class__.__name__
                    break
                time.sleep(min(4.0, 0.5 * fails))
                continue
            why = self._read()
            self.ok = False
            if self.closed or self.refused:
                break
            self.drops.append(why)
            self.reconnects += 1
            fails = 1
            try:
                self.ws.close()
            except Exception:
                pass
            time.sleep(0.3)
        self.dead = True
        self.closed = True
        self.ok = False

    def _read(self):
        try:
            while not self.closed:
                text = self.ws.recv_text()
                if text is None:
                    return 'closed by server'
                try:
                    msg = json.loads(text)
                except ValueError:
                    continue
                ev = msg.get('event')
                pl = msg.get('payload') or {}
                if ev == 'phx_reply' and msg.get('ref') == '1':
                    if pl.get('status') == 'ok':
                        self.ok = True
                        self.ever_ok = True
                        self._flush()
                    else:
                        self.error = 'the server refused the room'
                        self.refused = True
                        return 'refused'
                elif ev == 'broadcast':
                    inner = pl.get('payload') or {}
                    if inner.get('to') not in (None, self.pid):
                        continue
                    if inner.get('from') == self.pid:
                        continue
                    self.inbox.put((pl.get('event'), inner.get('d'), inner.get('from')))
                elif ev in ('phx_error', 'phx_close') and msg.get('topic') == self.topic:
                    return ev
        except Exception as e:
            return 'read: %s' % e.__class__.__name__
        return 'closed'

    def _heartbeat(self):
        while not self.closed:
            time.sleep(15)
            if self.ok:
                try:
                    self._raw('phoenix', 'heartbeat', {})
                except Exception:
                    pass

    def _flush(self):
        with self.plock:
            pend, self.pending = self.pending, []
        for kind, data, to in pend:
            self.send(kind, data, to)

    def send(self, kind, data, to=None):
        if self.closed:
            return False
        if not self.ok:
            if self.ever_ok:
                # reconnecting: hold on to it for a moment
                with self.plock:
                    if len(self.pending) < 300:
                        self.pending.append((kind, data, to))
            return False
        inner = {'from': self.pid, 'd': data}
        if to:
            inner['to'] = to
        try:
            self._raw(self.topic, 'broadcast', {'type': 'broadcast', 'event': kind, 'payload': inner})
            self.sent += 1
            return True
        except Exception:
            with self.plock:
                if len(self.pending) < 300:
                    self.pending.append((kind, data, to))
            return False

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        if self.ok:
            try:
                self._raw(self.topic, 'phx_leave', {})
            except Exception:
                pass
        self.closed = True
        self.ok = False
        if self.ws:
            self.ws.close()
