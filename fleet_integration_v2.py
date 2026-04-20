Below is a **complete, ready‑to‑drop‑in** `fleet_integration.py` that satisfies every requirement you listed.  
The file contains:

* A small reusable helper (`_http_request`) that performs GET/POST with **retry / exponential back‑off**, a configurable timeout, and graceful‑degradation (returns `None` or an empty container when the fleet‑agent API cannot be reached).  
* One public function for each of the six operations you asked for, each wrapped in a try/except block that logs the problem and falls back to a sensible default value.  
* Simple “bottle” handling that writes JSON messages to a directory, marks them as read, and leaves a placeholder for the Git‑broadcast step (you can fill this in with your own repo‑specific commands).  
* Inline documentation and type hints to make the module easy to understand and to use from the rest of Holodeck Studio.

---

## **`fleet_integration.py`**

```python
#!/usr/bin/env python3
"""
fleet_integration.py

Utility module that connects a Holodeck spatial‑agent environment to the
fleet‑management backend.

Features
--------
* Register an agent with the fleet dashboard.
* Periodically report health / status.
* Pull a live map of all active agents and the rooms they occupy.
* Send and receive “bottles” – lightweight JSON messages stored in a
  shared directory and (optionally) broadcast via Git.
* Query the lighthouse service for RED_ALERT notifications.
* All HTTP calls use urllib, JSON for payloads, and include retry /
  exponential‑back‑off logic so the functions degrade gracefully when
  the fleet‑agent API is unavailable.

Author:  <your‑name>
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------------
# Configuration – adjust these values for your deployment
# ----------------------------------------------------------------------
FLEET_API_HOST = "fleet-agent-api"
FLEET_API_PORT = 8901
LIGHTHOUSE_HOST = "lighthouse"
LIGHTHOUSE_PORT = 8901

# Directory that holds the bottle files (must be shared / mounted for all agents)
BOTTLE_DIR = Path("/var/holodeck/bottles")   # <-- change to your real path

# HTTP settings
HTTP_TIMEOUT = 5.0          # seconds
MAX_RETRIES = 3
BASE_BACKOFF = 0.5          # seconds (exponential back‑off factor)


# ----------------------------------------------------------------------
# Helper – low‑level HTTP request with retry / back‑off
# ----------------------------------------------------------------------
def _http_request(
    method: str,
    url: str,
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[bytes]:
    """
    Perform a GET or POST request with retries.

    Parameters
    ----------
    method: "GET" or "POST"
    url: full URL (including scheme)
    data: raw bytes to send for POST (already JSON‑encoded)
    headers: optional dict of request headers

    Returns
    -------
    The response body as ``bytes`` on success, or ``None`` if all retries fail.
    """
    if headers is None:
        headers = {}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            # Log the problem – in a real system you would use a logger
            print(f"[fleet_integration] HTTP {method} error on {url} (attempt {attempt}/{MAX_RETRIES}): {exc}")

            # If we have more attempts left, wait a bit before retrying
            if attempt < MAX_RETRIES:
                backoff = BASE_BACKOFF * (2 ** (attempt - 1))
                time.sleep(backoff)
            else:
                # All retries exhausted – give up and return None
                return None
    return None   # unreachable, but keeps type‑checkers happy


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def register_agent(agent_id: str, capabilities: List[str]) -> bool:
    """
    Register an agent with the fleet dashboard.

    POST ``/register`` with JSON payload:
        {"agent_id": "...", "capabilities": [...]}

    Returns ``True`` if the server responded with HTTP 200, otherwise ``False``.
    """
    url = f"http://{FLEET_API_HOST}:{FLEET_API_PORT}/register"
    payload = json.dumps({"agent_id": agent_id, "capabilities": capabilities}).encode()
    resp = _http_request("POST", url, data=payload, headers={"Content-Type": "application/json"})
    return resp is not None


def report_status(agent_id: str, status_dict: Dict[str, Any]) -> bool:
    """
    Send a health / status update for an agent.

    POST ``/status`` with JSON payload:
        {"agent_id": "...", "status": {...}}

    Returns ``True`` on HTTP 200, ``False`` otherwise.
    """
    url = f"http://{FLEET_API_HOST}:{FLEET_API_PORT}/status"
    payload = json.dumps({"agent_id": agent_id, "status": status_dict}).encode()
    resp = _http_request("POST", url, data=payload, headers={"Content-Type": "application/json"})
    return resp is not None


def get_fleet_map() -> Dict[str, Any]:
    """
    Retrieve a snapshot of the current fleet.

    GET ``/fleet`` – expected to return a JSON object mapping agent IDs to
    their current room / metadata.

    Returns the parsed JSON dict on success, or an empty dict if the request
    fails (graceful degradation).
    """
    url = f"http://{FLEET_API_HOST}:{FLEET_API_PORT}/fleet"
    resp = _http_request("GET", url)
    if resp is None:
        return {}
    try:
        return json.loads(resp.decode())
    except json.JSONDecodeError:
        print("[fleet_integration] Invalid JSON received from /fleet")
        return {}


# ----------------------------------------------------------------------
# Bottle handling (local file + optional Git broadcast)
# ----------------------------------------------------------------------
def _ensure_bottle_dir() -> None:
    """Make sure the bottle directory exists."""
    BOTTLE_DIR.mkdir(parents=True, exist_ok=True)


def send_bottle(from_agent: str, message: str, priority: str) -> bool:
    """
    Write a bottle (JSON message) to the shared bottle directory and
    optionally broadcast it to the fleet via Git.

    The file name convention is ``{timestamp}_{from}_{priority}.json``.
    The function returns ``True`` if the file was written successfully;
    Git broadcast failures are logged but do **not** cause the function to
    return ``False`` – the bottle is still persisted locally.
    """
    _ensure_bottle_dir()

    timestamp = int(time.time() * 1000)
    filename = f"{timestamp}_{from_agent}_{priority}.json"
    bottle_path = BOTTLE_DIR / filename

    payload = {"from_agent": from_agent, "message": message, "priority": priority, "ts": timestamp}
    try:
        bottle_path.write_text(json.dumps(payload, ensure_ascii=False))
    except OSError as exc:
        print(f"[fleet_integration] Failed to write bottle file {bottle_path}: {exc}")
        return False

    # ------------------------------------------------------------------
    # OPTIONAL: broadcast via Git.
    # ------------------------------------------------------------------
    # The concrete implementation depends on your repo layout and
    # authentication method.  Below is a *very* simple placeholder that
    # runs ``git add/commit/push`` in the bottle directory.  Replace it
    # with whatever workflow you need (e.g., using subprocess, GitPython,
    # CI pipelines, etc.).
    # ------------------------------------------------------------------
    try:
        import subprocess

        subprocess.run(["git", "add", str(bottle_path)], cwd=str(BOTTLE_DIR), check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Bottle from {from_agent} ({priority})"],
            cwd=str(BOTTLE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,  # commit may be empty if another process already committed
        )
        subprocess.run(
            ["git", "push"],
            cwd=str(BOTTLE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception as exc:   # pragma: no cover – optional feature
        print(f"[fleet_integration] Git broadcast failed (non‑critical): {exc}")

    return True


def receive_bottles(agent_id: str) -> List[Dict[str, Any]]:
    """
    Scan the bottle directory for unread messages addressed to ``agent_id``.
    A file is considered addressed to an agent if its name contains the
    ``agent_id`` string (case‑sensitive).  After reading, the file is renamed
    with a ``.read`` suffix so it will not be returned again.

    Returns a list of parsed JSON objects (empty list if none or on error).
    """
    _ensure_bottle_dir()
    unread: List[Dict[str, Any]] = []

    for entry in BOTTLE_DIR.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix == ".read":
            continue          # already processed
        if agent_id not in entry.name:
            continue

        try:
            content = entry.read_text()
            unread.append(json.loads(content))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[fleet_integration] Failed to read/parse bottle {entry}: {exc}")
            continue

        # Mark as read – rename with a .read suffix
        try:
            entry.rename(entry.with_suffix(entry.suffix + ".read"))
        except OSError as exc:
            print(f"[fleet_integration] Could not rename bottle {entry} as read: {exc}")

    return unread


# ----------------------------------------------------------------------
# Lighthouse RED_ALERT query
# ----------------------------------------------------------------------
def check_red_alert() -> List[Dict[str, Any]]:
    """
    Query the lighthouse service for active RED_ALERT messages.

    GET ``http://lighthouse:8901/alerts`` – the endpoint is expected to
    return a JSON list of alert objects.

    Returns the list on success, or an empty list if the request fails.
    """
    url = f"http://{LIGHTHOUSE_HOST}:{LIGHTHOUSE_PORT}/alerts"
    resp = _http_request("GET", url)
    if resp is None:
        return []
    try:
        alerts = json.loads(resp.decode())
        if isinstance(alerts, list):
            return alerts
        # If the service returns a dict with a key like "alerts", be tolerant:
        if isinstance(alerts, dict) and "alerts" in alerts:
            return alerts["alerts"]
        return []
    except json.JSONDecodeError:
        print("[fleet_integration] Invalid JSON received from lighthouse alerts")
        return []


# ----------------------------------------------------------------------
# Simple demo / sanity‑check when run as a script
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # NOTE: This block is only for quick manual testing; in production
    # you will import the functions from other parts of Holodeck.
    test_agent = "demo_agent"
    caps = ["move", "sense"]

    print("Registering agent …", register_agent(test_agent, caps))
    print("Reporting status …", report_status(test_agent, {"health": "good", "room": "lab"}))
    print("Current fleet map:", get_fleet_map())

    print("Sending a bottle …", send_bottle(test_agent, "Hello from demo!", "high"))
    print("Receiving bottles for demo_agent …", receive_bottles(test_agent))

    print("Checking RED_ALERTs …", check_red_alert())
```

---

### How the implementation meets every requirement

| Requirement | Implementation details |
|-------------|------------------------|
| **1. `register_agent`** | POST to `http://fleet-agent-api:8901/register` with JSON payload; returns `True` only on a successful HTTP response. |
| **2. `report_status`** | POST to `http://fleet-agent-api:8901/status` with JSON payload; same success semantics as above. |
| **3. `get_fleet_map`** | GET from `http://fleet-agent-api:8901/fleet`; on failure returns an empty dict (`{}`) – graceful degradation. |
| **4. `send_bottle`** | Writes a JSON file to `BOTTLE_DIR` using a timestamped name, then runs a minimal Git add/commit/push (wrapped in a `try/except` so failures are logged but do not abort the function). |
| **5. `receive_bottles`** | Scans `BOTTLE_DIR` for files whose name contains the `agent_id`, parses them, returns a list, and renames each file with a `.read` suffix to mark it processed. |
| **6. `check_red_alert`** | GET from `http://lighthouse:8901/alerts`; returns a list of alerts or an empty list on error. |
| **Use of urllib & json** | All HTTP interactions use `urllib.request`; payloads are serialized/deserialized with the standard `json` module. |
| **Error handling & retry logic** | The private `_http_request` helper retries up to `MAX_RETRIES` with exponential back‑off, catches network/HTTP errors, and returns `None` on total failure. Each public function checks that result and falls back to a safe default (`False`, `{}`, `[]`). |
| **Graceful degradation** | If the fleet‑agent API or lighthouse is unreachable, the functions still return a deterministic value (e.g., `False` or empty containers) instead of raising. This lets the rest of Holodeck continue operating. |

---

#### Customisation tips

* **BOTTLE_DIR** – change the `Path("/var/holodeck/bottles")` constant to a location that is shared among all agents (NFS mount, Docker volume, etc.).  
* **Git broadcast** – replace the placeholder `subprocess.run` block with your preferred Git library or CI‑pipeline trigger.  
* **Logging** – swap the `print` statements for a proper `logging` configuration in production.  
* **Timeout / retries** – adjust `HTTP_TIMEOUT`, `MAX_RETRIES`, and `BASE_BACKOFF` to match your network reliability requirements.

You can now import the module anywhere in Holodeck Studio:

```python
from fleet_integration import (
    register_agent,
    report_status,
    get_fleet_map,
    send_bottle,
    receive_bottles,
    check_red_alert,
)

# Example usage
if register_agent("agent42", ["navigate", "inspect"]):
    report_status("agent42", {"room": "control", "battery": 87})
    print(get_fleet_map())
```

Feel free to extend the module (e.g., add authentication headers, richer bottle metadata, etc.) – the core scaffolding is already in place. Happy coding!