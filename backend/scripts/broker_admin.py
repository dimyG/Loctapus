"""RabbitMQ vhost provisioning through the management HTTP API.

``ensure_broker_vhost`` creates the vhost named in ``broker_url`` and grants its
user full permissions on it, both idempotently, so each environment (dev, pytest,
e2e) gets its own isolated vhost. The pytest conftest and the e2e bootstrap call
it. Run directly::

    python scripts/broker_admin.py amqp://guest:guest@localhost:5672/rag_test
"""

import base64
import json
import sys
import urllib.request
from urllib.parse import quote, urlsplit


def _vhost_from_broker_url(*, broker_url: str) -> str:
    """Return the vhost segment of ``broker_url``, defaulting to the root vhost."""

    vhost = urlsplit(broker_url).path.lstrip("/")
    return vhost or "/"


def _put_json(*, url: str, credentials: tuple[str, str], body: bytes) -> None:
    """PUT ``body`` to ``url`` with basic auth; any HTTP error raises, any 2xx is success."""

    username, password = credentials
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    request = urllib.request.Request(url, data=body, method="PUT")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request) as response:
        response.read()


def ensure_broker_vhost(*, broker_url: str, management_url: str = "http://localhost:15672") -> None:
    """Create the vhost in ``broker_url`` and grant its user full permissions, idempotently.

    A newly created vhost grants no permissions by default, so the user that connects
    through ``broker_url`` needs the explicit configure/write/read rights before it
    can open a connection.
    """

    parsed = urlsplit(broker_url)
    if parsed.username is None or parsed.password is None:
        raise ValueError(f"broker_url must carry user:password credentials: {broker_url!r}")
    credentials = (parsed.username, parsed.password)
    base = management_url.rstrip("/")
    vhost = quote(_vhost_from_broker_url(broker_url=broker_url), safe="")
    _put_json(
        url=f"{base}/api/vhosts/{vhost}",
        credentials=credentials,
        body=json.dumps({}).encode("utf-8"),
    )
    permissions = {"configure": ".*", "write": ".*", "read": ".*"}
    user = quote(parsed.username, safe="")
    _put_json(
        url=f"{base}/api/permissions/{vhost}/{user}",
        credentials=credentials,
        body=json.dumps(permissions).encode("utf-8"),
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: broker_admin.py <broker_url>")
    ensure_broker_vhost(broker_url=sys.argv[1])
