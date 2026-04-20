"""
Tabula Rasa Persistence Layer
Saves and restores agent budgets, permission levels, ship state, and trust scores
to JSON files so state survives server restarts.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any


class TabulaRasaStore:
    """JSON-backed persistence for tabula rasa game state."""

    def __init__(self, data_dir: str = "world/tabula_rasa"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "budgets").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "trust").mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ── Agent Budget persistence ───────────────────────────────

    def save_budget(self, agent_name: str, budget_data: dict) -> None:
        """Save an agent's budget to disk."""
        path = self.data_dir / "budgets" / f"{agent_name}.json"
        budget_data["_saved_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(budget_data, indent=2, default=str))
        self._cache[f"budget:{agent_name}"] = budget_data

    def load_budget(self, agent_name: str) -> Optional[dict]:
        """Load an agent's budget from disk. Returns None if not found."""
        cached = self._cache.get(f"budget:{agent_name}")
        if cached is not None:
            return cached
        path = self.data_dir / "budgets" / f"{agent_name}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        self._cache[f"budget:{agent_name}"] = data
        return data

    def delete_budget(self, agent_name: str) -> bool:
        """Delete an agent's budget. Returns True if existed."""
        key = f"budget:{agent_name}"
        self._cache.pop(key, None)
        path = self.data_dir / "budgets" / f"{agent_name}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_budgets(self) -> Dict[str, dict]:
        """List all saved budgets."""
        result = {}
        budgets_dir = self.data_dir / "budgets"
        for f in sorted(budgets_dir.glob("*.json")):
            agent_name = f.stem
            result[agent_name] = self.load_budget(agent_name)
        return result

    # ── Permission Level persistence ───────────────────────────

    def save_permission(self, agent_name: str, level: int) -> None:
        """Save an agent's permission level."""
        # Permissions are stored inside the budget file for co-location
        budget = self.load_budget(agent_name)
        if budget is not None:
            budget["permission_level"] = level
            self.save_budget(agent_name, budget)
        else:
            # Standalone permission file if no budget yet
            perm_path = self.data_dir / "budgets" / f"{agent_name}.json"
            data = {"agent": agent_name, "permission_level": level,
                    "_saved_at": datetime.now(timezone.utc).isoformat()}
            perm_path.write_text(json.dumps(data, indent=2))
            self._cache[f"budget:{agent_name}"] = data

    def load_permission(self, agent_name: str) -> Optional[int]:
        """Load an agent's permission level."""
        budget = self.load_budget(agent_name)
        if budget is not None and "permission_level" in budget:
            return budget["permission_level"]
        return None

    # ── Ship State persistence ─────────────────────────────────

    def save_ship(self, ship_data: dict) -> None:
        """Save the shared ship state."""
        ship_data["_saved_at"] = datetime.now(timezone.utc).isoformat()
        path = self.data_dir / "ship.json"
        path.write_text(json.dumps(ship_data, indent=2, default=str))
        self._cache["ship"] = ship_data

    def load_ship(self) -> Optional[dict]:
        """Load the shared ship state."""
        cached = self._cache.get("ship")
        if cached is not None:
            return cached
        path = self.data_dir / "ship.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        self._cache["ship"] = data
        return data

    # ── Trust History (JSONL for append-only) ──────────────────

    def record_trust_event(self, agent_name: str, event_type: str, details: dict = None) -> None:
        """Record a trust-related event (task_complete, task_fail, review_pass, etc.)."""
        trust_dir = self.data_dir / "trust"
        trust_dir.mkdir(parents=True, exist_ok=True)
        path = trust_dir / f"{agent_name}.jsonl"
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent_name,
            "event_type": event_type,
            "details": details or {},
        }
        with open(path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def get_trust_history(self, agent_name: str, limit: int = 100) -> list:
        """Get trust event history for an agent."""
        path = self.data_dir / "trust" / f"{agent_name}.jsonl"
        if not path.exists():
            return []
        events = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        # Return most recent first, limited
        return list(reversed(events))[:limit]

    # ── Audit Log (JSONL for append-only) ──────────────────────

    def log_audit(self, agent_name: str, action: str, details: dict = None) -> None:
        """Log an auditable action for compliance/review."""
        path = self.data_dir / "audit.jsonl"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent_name,
            "action": action,
            "details": details or {},
        }
        with open(path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def get_audit_log(self, agent_name: str = None, limit: int = 50) -> list:
        """Get audit log entries, optionally filtered by agent."""
        path = self.data_dir / "audit.jsonl"
        if not path.exists():
            return []
        entries = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if agent_name is None or entry.get("agent") == agent_name:
                        entries.append(entry)
        # Return most recent first, limited
        return list(reversed(entries))[:limit]

    # ── Bulk operations ────────────────────────────────────────

    def save_all(self, budgets: dict, permissions: dict, ship: dict = None) -> None:
        """Save all state at once (for periodic snapshots)."""
        for agent_name, budget_obj in budgets.items():
            budget_data = budget_obj.to_dict() if hasattr(budget_obj, "to_dict") else budget_obj
            budget_data["permission_level"] = permissions.get(agent_name, 0)
            self.save_budget(agent_name, budget_data)
        if ship is not None:
            ship_data = ship.to_dict() if hasattr(ship, "to_dict") else ship
            self.save_ship(ship_data)
        self.log_audit("_system", "snapshot_save", {
            "agents": len(budgets),
            "has_ship": ship is not None,
        })

    def load_all(self) -> dict:
        """Load all state. Returns {budgets, permissions, ship}."""
        budgets = self.list_budgets()
        permissions = {}
        for agent_name, budget_data in budgets.items():
            if "permission_level" in budget_data:
                permissions[agent_name] = budget_data["permission_level"]
        ship = self.load_ship()
        return {"budgets": budgets, "permissions": permissions, "ship": ship}

    def export_snapshot(self) -> dict:
        """Export complete state snapshot as a dict."""
        all_state = self.load_all()
        all_state["trust_histories"] = {}
        trust_dir = self.data_dir / "trust"
        if trust_dir.exists():
            for f in trust_dir.glob("*.jsonl"):
                agent_name = f.stem
                all_state["trust_histories"][agent_name] = self.get_trust_history(agent_name)
        all_state["audit_log"] = self.get_audit_log(limit=200)
        all_state["exported_at"] = datetime.now(timezone.utc).isoformat()
        return all_state

    # ── Maintenance ────────────────────────────────────────────

    def prune_stale(self, max_age_days: int = 30) -> int:
        """Remove budget data for agents not seen in N days. Returns count pruned."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        pruned = 0
        for agent_name in list(self.list_budgets().keys()):
            budget = self.load_budget(agent_name)
            if budget is None:
                continue
            saved_at_str = budget.get("_saved_at")
            if not saved_at_str:
                continue
            try:
                saved_at = datetime.fromisoformat(saved_at_str)
                if saved_at.tzinfo is None:
                    saved_at = saved_at.replace(tzinfo=timezone.utc)
                if saved_at < cutoff:
                    self.delete_budget(agent_name)
                    # Also remove trust history
                    trust_path = self.data_dir / "trust" / f"{agent_name}.jsonl"
                    if trust_path.exists():
                        trust_path.unlink()
                    pruned += 1
            except (ValueError, TypeError):
                continue
        return pruned

    def get_stats(self) -> dict:
        """Return storage statistics (file counts, total size, etc.)."""
        stats = {
            "data_dir": str(self.data_dir),
            "budget_count": 0,
            "trust_count": 0,
            "audit_entries": 0,
            "has_ship": False,
            "total_size_bytes": 0,
        }
        budgets_dir = self.data_dir / "budgets"
        if budgets_dir.exists():
            for f in budgets_dir.glob("*.json"):
                stats["budget_count"] += 1
                stats["total_size_bytes"] += f.stat().st_size

        trust_dir = self.data_dir / "trust"
        if trust_dir.exists():
            for f in trust_dir.glob("*.jsonl"):
                stats["trust_count"] += 1
                stats["total_size_bytes"] += f.stat().st_size

        audit_path = self.data_dir / "audit.jsonl"
        if audit_path.exists():
            with open(audit_path, "r") as f:
                stats["audit_entries"] = sum(1 for line in f if line.strip())
            stats["total_size_bytes"] += audit_path.stat().st_size

        ship_path = self.data_dir / "ship.json"
        if ship_path.exists():
            stats["has_ship"] = True
            stats["total_size_bytes"] += ship_path.stat().st_size

        return stats
