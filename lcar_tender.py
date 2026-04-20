#!/usr/bin/env python3
"""Fleet Liaison Tender — Social vessel for cloud-edge communication."""

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class TenderMessage:
    """A message transmitted via a liaison tender.
    
    Attributes:
        origin: Message origin (cloud or edge)
        target: Target vessel or system name
        type: Message type (research, data, context, priority)
        payload: Message content/data dictionary
        compressed: Whether payload is compressed for edge transmission
        timestamp: Unix timestamp when message was created
    """
    origin: str
    target: str
    type: str
    payload: dict
    compressed: bool = False
    timestamp: float = field(default_factory=time.time)


class LiaisonTender:
    """Base class for fleet liaison tenders.
    
    Manages message queues and processing for a specific
    type of fleet communication (research, data, priority).
    """
    
    def __init__(self, name: str, tender_type: str) -> None:
        """Initialize a liaison tender.
        
        Args:
            name: Unique name for this tender
            tender_type: Type of messages this tender handles
        """
        self.name = name
        self.tender_type = tender_type
        self.queue_in: List[TenderMessage] = []
        self.queue_out: List[TenderMessage] = []
        self.filters: Dict[str, List[str]] = {}  # target -> list of keywords
    
    def receive(self, msg: TenderMessage) -> None:
        """Receive a message and queue for processing.
        
        Args:
            msg: TenderMessage to queue
        """
        self.queue_in.append(msg)
    
    def process(self) -> List[TenderMessage]:
        """Process queue and produce outgoing messages.
        
        Returns:
            List of processed outgoing messages
            
        Raises:
            NotImplementedError: If subclass doesn't implement this method
        """
        raise NotImplementedError
    
    def send(self, msg: TenderMessage) -> None:
        """Queue message for delivery.
        
        Args:
            msg: TenderMessage to send
        """
        self.queue_out.append(msg)
    
    def status(self) -> dict:
        """Get tender status information.
        
        Returns:
            Dictionary with name, type, inbox count, and outbox count
        """
        return {
            "name": self.name,
            "type": self.tender_type,
            "inbox": len(self.queue_in),
            "outbox": len(self.queue_out),
        }


class ResearchTender(LiaisonTender):
    """Carries findings between cloud and edge labs.
    
    Processes research data, converting cloud specs to
    compressed edge action items, and formatting edge findings
    for cloud consumption.
    """
    
    def __init__(self) -> None:
        """Initialize the research tender."""
        super().__init__("research-tender", "research")
    
    def process(self) -> List[TenderMessage]:
        """Process research messages.
        
        Returns:
            List of processed outgoing messages
        """
        results: List[TenderMessage] = []
        while self.queue_in:
            msg = self.queue_in.pop(0)
            if msg.origin == "cloud":
                # Cloud spec → compressed edge action items
                results.append(TenderMessage(
                    origin="cloud", target="jetsonclaw1",
                    type="research",
                    payload=self._compress_spec(msg.payload),
                    compressed=True,
                ))
            elif msg.origin == "edge":
                # Edge findings → formatted for cloud consumption
                results.append(TenderMessage(
                    origin="edge", target="oracle1",
                    type="research",
                    payload=self._format_findings(msg.payload),
                ))
        self.queue_out.extend(results)
        return results
    
    def _compress_spec(self, spec: dict) -> dict:
        """Compress cloud spec for edge consumption.
        
        Args:
            spec: Cloud spec dictionary
            
        Returns:
            Compressed dictionary with only edge-relevant fields
        """
        return {
            "action": spec.get("title", "untitled"),
            "changes": spec.get("changes_affecting_edge", []),
            "ignore": spec.get("changes_not_affecting_edge", []),
            "isa_changes": spec.get("isa_modifications", []),
            "deadline": spec.get("deadline"),
        }
    
    def _format_findings(self, findings: dict) -> dict:
        """Format edge findings for cloud.
        
        Args:
            findings: Edge findings dictionary
            
        Returns:
            Formatted dictionary ready for cloud consumption
        """
        return {
            "source": "jetsonclaw1",
            "benchmarks": findings.get("benchmarks", {}),
            "failure_modes": findings.get("failures", []),
            "timing_data": findings.get("timing", {}),
            "recommendations": findings.get("recommendations", []),
            "reality_check": findings.get("cloud_assumption_vs_reality", {}),
        }


class DataTender(LiaisonTender):
    """Batches and packages big data for edge consumption.
    
    Processes incoming data messages, batching them up to
    a configured size, and transmitting as compressed packages.
    """
    
    def __init__(self, batch_size: int = 50) -> None:
        """Initialize a data tender.
        
        Args:
            batch_size: Number of items to batch before sending
        """
        super().__init__("data-tender", "data")
        self.batch_size = batch_size
        self.buffer: List[dict] = []
    
    def process(self) -> List[TenderMessage]:
        """Process data messages with batching.
        
        Returns:
            List of processed outgoing messages
        """
        results: List[TenderMessage] = []
        while self.queue_in:
            msg = self.queue_in.pop(0)
            if msg.origin == "cloud" and msg.target == "edge":
                self.buffer.append(msg.payload)
                if len(self.buffer) >= self.batch_size:
                    batch = self._package_batch(self.buffer)
                    results.append(TenderMessage(
                        origin="cloud", target="jetsonclaw1",
                        type="data", payload=batch, compressed=True,
                    ))
                    self.buffer = []
        self.queue_out.extend(results)
        return results
    
    def _package_batch(self, items: List[dict]) -> dict:
        """Package a batch of items for transmission.
        
        Args:
            items: List of data items to package
            
        Returns:
            Batch dictionary with metadata
        """
        return {
            "batch_size": len(items),
            "items": items,
            "edge_relevant_only": True,
            "total_cloud_events": sum(i.get("total_events", 1) for i in items),
        }


class PriorityTender(LiaisonTender):
    """Translates urgency between cloud and edge realities.
    
    Manages translation of priority levels between
    cloud (low/medium/high/critical) and edge (nominal/degraded/failing/down)
    contexts.
    """
    
    def __init__(self) -> None:
        """Initialize priority tender."""
        super().__init__("priority-tender", "priority")
        self.priority_map_cloud_to_edge = {
            "low": "ignore",
            "medium": "queue",
            "high": "handle_soon",
            "critical": "immediate",
        }
        self.priority_map_edge_to_cloud = {
            "nominal": "info",
            "degraded": "warning",
            "failing": "high",
            "down": "critical",
        }
    
    def process(self) -> List[TenderMessage]:
        """Process priority messages with translation.
        
        Returns:
            List of processed outgoing messages
        """
        results: List[TenderMessage] = []
        while self.queue_in:
            msg = self.queue_in.pop(0)
            if msg.origin == "cloud":
                cloud_priority = msg.payload.get("priority", "low")
                edge_priority = self.priority_map_cloud_to_edge.get(cloud_priority, "queue")
                if edge_priority != "ignore":
                    results.append(TenderMessage(
                        origin="cloud", target="jetsonclaw1",
                        type="priority",
                        payload={
                            "original": cloud_priority,
                            "translated": edge_priority,
                            "task": msg.payload.get("task"),
                            "reason": msg.payload.get("reason"),
                        },
                    ))
            elif msg.origin == "edge":
                edge_status = msg.payload.get("status", "nominal")
                cloud_alert = self.priority_map_edge_to_cloud.get(edge_status, "info")
                results.append(TenderMessage(
                    origin="edge", target="oracle1",
                    type="priority",
                    payload={
                        "original": edge_status,
                        "translated": cloud_alert,
                        "sensor_data": msg.payload.get("sensors"),
                    },
                ))
        self.queue_out.extend(results)
        return results


class TenderFleet:
    """Manages all liaison tenders.
    
    Central registry for all active tender instances,
    providing methods to run cycles across all tenders.
    """
    
    def __init__(self) -> None:
        """Initialize tender fleet."""
        self.tenders = {
            "research": ResearchTender(),
            "data": DataTender(),
            "priority": PriorityTender(),
        }
    
    def run_cycle(self):
        """Process all tender queues."""
        results = {}
        for name, tender in self.tenders.items():
            processed = tender.process()
            results[name] = len(processed)
        return results
    
    def status(self) -> Dict[str, Dict[str, int]]:
        """Get status of all tenders.
        
        Returns:
            Dictionary mapping tender name to their status dictionary
        """
        return {name: tender.status() for name, tender in self.tenders.items()}


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║  Fleet Liaison Tender — Communication Layer   ║")
    print("╚══════════════════════════════════════════════╝\n")
    
    fleet = TenderFleet()
    
    # Simulate cloud → edge research
    fleet.tenders["research"].receive(TenderMessage(
        origin="cloud", target="edge", type="research",
        payload={
            "title": "ISA v3 Edge Encoding",
            "changes_affecting_edge": ["compact mode opcodes renumbered"],
            "changes_not_affecting_edge": ["cloud-only debug extensions"],
            "isa_modifications": ["OP_COMPACT prefix byte changed from 0xFE to 0xFD"],
            "deadline": "2026-04-15",
        },
    ))
    
    # Simulate edge → cloud findings
    fleet.tenders["research"].receive(TenderMessage(
        origin="edge", target="cloud", type="research",
        payload={
            "benchmarks": {"16K rooms": "25.5us/tick"},
            "failures": ["COBS framing drops bytes at 115200 baud on long cables"],
            "timing": {"model_hot_swap": "42s measured"},
            "recommendations": ["Use shorter serial cables for ESP32 bridge"],
            "cloud_assumption_vs_reality": {
                "assumption": "model swap takes 45s",
                "reality": "42s on Orin, but 68s with fragmented VRAM",
            },
        },
    ))
    
    # Simulate priority translation
    fleet.tenders["priority"].receive(TenderMessage(
        origin="cloud", target="edge", type="priority",
        payload={"priority": "medium", "task": "Update ISA opcodes", "reason": "Fleet-wide convergence"},
    ))
    
    fleet.tenders["priority"].receive(TenderMessage(
        origin="edge", target="cloud", type="priority",
        payload={"status": "degraded", "sensors": {"cpu_temp": "72C", "gpu_util": "95%"}},
    ))
    
    # Run processing cycle
    print("Processing tender queues...")
    results = fleet.run_cycle()
    for name, count in results.items():
        print(f"  {name}: {count} messages processed")
    
    # Show outbound messages
    print("\nOutbound messages:")
    for name, tender in fleet.tenders.items():
        for msg in tender.queue_out:
            print(f"  [{name}] {msg.origin} → {msg.target}: {msg.type}")
            if "reality_check" in str(msg.payload):
                rc = msg.payload.get("reality_check", {})
                print(f"    Reality check: {rc.get('assumption')} → {rc.get('reality')}")
            if "translated" in msg.payload:
                print(f"    Priority: {msg.payload.get('original')} → {msg.payload.get('translated')}")
    
    print("\nTender fleet status:")
    for name, status in fleet.status().items():
        print(f"  {name}: inbox={status['inbox']}, outbox={status['outbox']}")
    
    print("\n═══════════════════════════════════════════")
    print("Social vessels. Information management. Fleet-scale.")
    print("═══════════════════════════════════════════")
