#!/usr/bin/env python3
"""
FLUX-LCAR Scheduler — Scheduling as Intelligence

Not one smart model doing everything, but the right model 
at the right time in the right room.

Cost optimization: cheap models for bulk work at night,
expensive models for critical decisions during the day.
"""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ModelTier(Enum):
    CHEAP = "cheap"       # glm-4.7-flash — bulk spray
    GOOD = "good"         # glm-4.7 — solid mid-tier
    RUNNER = "runner"     # glm-5-turbo — daily driver
    EXPERT = "expert"     # glm-5.1 — complex reasoning
    REASONER = "reasoner" # deepseek-reasoner — deep thinking


@dataclass
class ModelProfile:
    """Profile of an AI model with performance characteristics.
    
    Attributes:
        name: Model identifier
        tier: Model tier classification
        cost_per_1k_tokens: Cost per 1000 tokens in USD
        speed_tokens_per_sec: Token generation speed
        quality_score: Quality rating (0-1)
        best_for: List of use cases this model excels at
    """
    name: str
    tier: ModelTier
    cost_per_1k_tokens: float
    speed_tokens_per_sec: float
    quality_score: float
    best_for: List[str]


@dataclass
class ScheduleSlot:
    """A time slot with model assignment.
    
    Attributes:
        start_hour: UTC hour when slot starts
        end_hour: UTC hour when slot ends
        model: AI model to use during this slot
        reason: Why this model was chosen for this slot
        rooms: List of room IDs where this slot applies ('*' for all rooms)
    """
    start_hour: int  # UTC hour
    end_hour: int
    model: str
    reason: str
    rooms: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class ScheduledTask:
    """A task waiting for the right time to run.
    
    Attributes:
        task_id: Unique task identifier
        room_id: Room where task should run
        description: Human-readable task description
        required_tier: Minimum model tier needed for this task
        estimated_tokens: Estimated tokens required
        deadline: Optional Unix timestamp when task is due
        priority: Task priority (higher = more important)
        created_at: Unix timestamp when task was submitted
        assigned_model: Model assigned to execute this task
        status: Current task state
    """
    task_id: str
    room_id: str
    description: str
    required_tier: ModelTier
    estimated_tokens: int
    deadline: Optional[float] = None  # unix timestamp
    priority: int = 0  # higher = more important
    created_at: float = field(default_factory=time.time)
    assigned_model: Optional[str] = None
    status: str = "pending"  # pending, scheduled, running, done


# Fleet model profiles
FLEET_MODELS = {
    "glm-4.7-flash": ModelProfile("glm-4.7-flash", ModelTier.CHEAP, 0.0001, 500, 0.6, ["bulk", "sweep"]),
    "glm-4.7": ModelProfile("glm-4.7", ModelTier.GOOD, 0.0005, 200, 0.75, ["coding", "review"]),
    "glm-5-turbo": ModelProfile("glm-5-turbo", ModelTier.RUNNER, 0.002, 150, 0.85, ["coding", "planning"]),
    "glm-5.1": ModelProfile("glm-5.1", ModelTier.EXPERT, 0.005, 80, 0.95, ["architecture", "strategy"]),
    "deepseek-reasoner": ModelProfile("deepseek-reasoner", ModelTier.REASONER, 0.003, 30, 0.90, ["deep_thinking"]),
    "deepseek-chat": ModelProfile("deepseek-chat", ModelTier.GOOD, 0.0003, 300, 0.70, ["iteration", "spreading"]),
}


class FleetScheduler:
    """Schedule the right model at the right time for cost optimization.
    
    Manages time-based model assignments and task scheduling
    based on model tiers, costs, and budget constraints.
    """
    
    def __init__(self) -> None:
        """Initialize the fleet scheduler with default schedule."""
        self.schedule: List[ScheduleSlot] = []
        self.task_queue: List[ScheduledTask] = []
        self.completed: List[ScheduledTask] = []
        self.daily_budget: float = 1.0  # $/day
        self.spent: float = 0.0
        self._setup_default_schedule()
    
    def _setup_default_schedule(self) -> None:
        """Set up the default cost-optimized schedule."""
        self.schedule = [
            # Night shift (cheap bulk work)
            ScheduleSlot(0, 6, "glm-4.7-flash", "night bulk", ["*"]),
            ScheduleSlot(0, 6, "deepseek-chat", "night iteration", ["engineering", "workshop"]),
            
            # Morning (good models for fresh starts)
            ScheduleSlot(6, 10, "glm-5-turbo", "morning driver", ["*"]),
            ScheduleSlot(6, 10, "deepseek-reasoner", "morning deep think", ["ready-room"]),
            
            # Peak hours (expert for critical decisions)
            ScheduleSlot(10, 14, "glm-5.1", "peak expert", ["bridge", "nav"]),
            ScheduleSlot(10, 14, "glm-5-turbo", "peak runner", ["*"]),
            
            # Afternoon (back to good)
            ScheduleSlot(14, 18, "glm-5-turbo", "afternoon", ["*"]),
            
            # Evening (wind down)
            ScheduleSlot(18, 22, "glm-4.7", "evening review", ["*"]),
            
            # Late night (cheap again)
            ScheduleSlot(22, 24, "glm-4.7-flash", "late night bulk", ["*"]),
        ]
    
    def get_current_model(self, room_id: str = "*") -> tuple[str, str]:
        """Get the best model for right now in this room.
        
        Args:
            room_id: Room identifier ('*' for wildcard)
            
        Returns:
            Tuple of (model_name, schedule_reason)
        """
        hour = datetime.now(timezone.utc).hour
        
        candidates: List[ScheduleSlot] = []
        for slot in self.schedule:
            if slot.start_hour <= hour < slot.end_hour:
                if "*" in slot.rooms or room_id in slot.rooms:
                    candidates.append(slot)
        
        if not candidates:
            return "glm-5-turbo", "fallback"
        
        # Pick most specific match (room-specific over wildcard)
        room_specific = [s for s in candidates if room_id in s.rooms]
        if room_specific:
            best = room_specific[0]
        else:
            best = candidates[0]
        
        return best.model, best.reason
    
    def submit_task(self, task_id: str, room_id: str, description: str,
                    required_tier: ModelTier, est_tokens: int,
                    priority: int = 0, deadline: Optional[float] = None) -> None:
        """Submit a task to be scheduled.
        
        Args:
            task_id: Unique task identifier
            room_id: Room where task should run
            description: Human-readable task description
            required_tier: Minimum model tier required
            est_tokens: Estimated tokens required
            priority: Task priority (higher = more important)
            deadline: Optional Unix timestamp when task is due
        """
        task = ScheduledTask(
            task_id=task_id, room_id=room_id, description=description,
            required_tier=required_tier, estimated_tokens=est_tokens,
            priority=priority, deadline=deadline,
        )
        self.task_queue.append(task)
    
    def schedule_pending(self) -> List[ScheduledTask]:
        """Assign models to pending tasks based on schedule and budget.
        
        Returns:
            List of tasks that were successfully scheduled
        """
        scheduled: List[ScheduledTask] = []
        remaining_budget = self.daily_budget - self.spent
        
        # Sort by priority (high first), then deadline urgency
        self.task_queue.sort(key=lambda t: (
            -t.priority,
            t.deadline if t.deadline else float('inf'),
        ))
        
        for task in self.task_queue:
            if task.status != "pending":
                continue
            
            # Get model for this room and time
            model_name, reason = self.get_current_model(task.room_id)
            model = FLEET_MODELS.get(model_name)
            
            if not model:
                continue
            
            # Check if model meets required tier
            tier_order = [ModelTier.CHEAP, ModelTier.GOOD, ModelTier.RUNNER, 
                         ModelTier.EXPERT, ModelTier.REASONER]
            if tier_order.index(model.tier) < tier_order.index(task.required_tier):
                continue  # model not powerful enough, wait for better slot
            
            # Check budget
            est_cost = (task.estimated_tokens / 1000) * model.cost_per_1k_tokens
            if est_cost > remaining_budget:
                continue  # can't afford it
            
            # Schedule it
            task.assigned_model = model_name
            task.status = "scheduled"
            remaining_budget -= est_cost
            scheduled.append(task)
        
        return scheduled
    
    def complete_task(self, task_id: str, actual_tokens: int) -> None:
        """Mark a task as done and track actual cost.
        
        Args:
            task_id: ID of task to complete
            actual_tokens: Actual tokens used for the task
        """
        for i, task in enumerate(self.task_queue):
            if task.task_id == task_id:
                model = FLEET_MODELS.get(task.assigned_model)
                if model:
                    self.spent += (actual_tokens / 1000) * model.cost_per_1k_tokens
                task.status = "done"
                self.completed.append(self.task_queue.pop(i))
                break
    
    def status(self) -> dict:
        """Get current scheduler status.
        
        Returns:
            Dictionary with current time, model, pending/scheduled/completed
            task counts, and budget information
        """
        now_hour = datetime.now(timezone.utc).hour
        current_model, reason = self.get_current_model()
        
        return {
            "current_time_utc": f"{now_hour}:00",
            "current_model": current_model,
            "schedule_reason": reason,
            "pending_tasks": len([t for t in self.task_queue if t.status == "pending"]),
            "scheduled_tasks": len([t for t in self.task_queue if t.status == "scheduled"]),
            "completed_today": len(self.completed),
            "budget_used": round(self.spent, 4),
            "budget_remaining": round(self.daily_budget - self.spent, 4),
        }


# Demo
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║  FLUX-LCAR Scheduler — Timing IS Intelligence ║")
    print("╚══════════════════════════════════════════════╝\n")
    
    sched = FleetScheduler()
    
    # Submit tasks
    sched.submit_task("T01", "bridge", "Review fleet health", ModelTier.EXPERT, 2000, priority=5)
    sched.submit_task("T02", "engineering", "Run spreader loop on 20 repos", ModelTier.CHEAP, 50000, priority=2)
    sched.submit_task("T03", "nav", "Calculate optimal route", ModelTier.EXPERT, 3000, priority=8)
    sched.submit_task("T04", "workshop", "Generate README files", ModelTier.GOOD, 10000, priority=1)
    sched.submit_task("T05", "ready-room", "Deep analysis of ISA v3", ModelTier.REASONER, 15000, priority=3)
    
    print("Submitted 5 tasks. Scheduling...\n")
    
    scheduled = sched.schedule_pending()
    for task in scheduled:
        print(f"  {task.task_id}: {task.description[:40]} → {task.assigned_model} (P{task.priority})")
    
    print(f"\n{sched.status()['pending_tasks']} tasks waiting for better time slots")
    
    # Complete some tasks
    sched.complete_task("T01", 1800)
    sched.complete_task("T03", 2500)
    
    print(f"\nStatus: {json.dumps(sched.status(), indent=2)}")
    
    # Show schedule table
    print("\n═══ Daily Schedule ═══")
    for slot in sorted(sched.schedule, key=lambda s: s.start_hour):
        rooms = ", ".join(slot.rooms)
        print(f"  {slot.start_hour:02d}:00-{slot.end_hour:02d}:00  "
              f"{slot.model:20s} {slot.reason:20s} [{rooms}]")
    
    print("\n═══════════════════════════════════════════")
    print("Not one smart model doing everything.")
    print("The right model at the right time in the right room.")
    print("Scheduling as intelligence.")
    print("═══════════════════════════════════════════")
