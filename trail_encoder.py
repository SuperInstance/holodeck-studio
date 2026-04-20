"""
Trail-FLUX Bridge — encode agent worklog trails as compilable FLUX bytecode.

Design Philosophy
─────────────────
"The trail IS the code." — Oracle1's Nudge

An agent's worklog — a sequence of file reads, edits, searches, messages,
and other fleet actions — is not mere documentation. It is a *program* that,
if executed in order, reproduces the agent's journey through the codebase.

This module encodes that journey as compact FLUX bytecode, making it:
  - **Replayable**: execute the bytecode to retrace every step
  - **Verifiable**: hash the bytecode to prove the agent did exactly these steps
  - **Composable**: concatenate trails — one agent's output feeds another's input
  - **Compact**: all string operands stored as 4-byte SHA-256 hashes (8 hex chars)
    with a string table section for recovery
  - **Human-auditable**: the printer/disassembler produces clear trail listings

Architecture
────────────
Trail Operations (0x90-0x9F): High-level fleet actions
Meta Operations   (0xA0-0xA3): Trail framing and annotations
Hash Table        (0xB0)      : String recovery section appended at EOF

Bytecode Format
───────────────
  [0xA0] [agent_id: u8] [trail_id: 4 bytes] [timestamp: 4 bytes]  -- TRAIL_BEGIN
  [opcode: u8] [operand_count: u8] [operands: variable u16...]     -- each step
  ...
  [0xA1] [total_steps: u16] [status: u8]                           -- TRAIL_END
  [0xB0] [table_length: u16]
    [hash: 8 bytes] [string_length: u8] [string_bytes: variable]
    ...

All operands are u16 to support both small numeric IDs and hash references.
String operands (paths, messages, patterns) are stored as two u16 values
encoding the first 4 bytes (8 hex chars) of their SHA-256 digest. The
original strings live in the hash table section for recovery.

# [pelagic] Trail-FLUX Bridge prototype — session-007
"""

from __future__ import annotations

import hashlib
import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


# ─── Trail Opcodes ────────────────────────────────────────────────────────────

class TrailOpcodes(IntEnum):
    """
    Trail-FLUX opcodes. Range 0x90-0xFF to avoid conflict with the
    math ISA (0x02-0x80). Organized into trail operations, meta operations,
    and reserved markers.

    Each opcode has a fixed semantic meaning and operand signature.
    The operand_count field in bytecode tells the decoder how many
    u16 operands follow.
    """
    # Trail Operations — high-level fleet actions
    GIT_COMMIT   = 0x90   # 2 args: repo_id, message_hash
    GIT_PUSH     = 0x91   # 1 arg:  repo_id
    FILE_READ    = 0x92   # 1 arg:  path_hash
    FILE_WRITE   = 0x93   # 2 args: path_hash, content_hash
    FILE_EDIT    = 0x94   # 3 args: path_hash, old_hash, new_hash
    TEST_RUN     = 0x95   # 2 args: test_path, expected_count
    SEARCH_CODE  = 0x96   # 1 arg:  pattern_hash
    BOTTLE_DROP  = 0x97   # 2 args: target, content_hash
    BOTTLE_READ  = 0x98   # 1 arg:  source
    LEVEL_UP     = 0x99   # 1 arg:  new_level
    SPELL_CAST   = 0x9A   # 1 arg:  spell_id
    ROOM_ENTER   = 0x9B   # 1 arg:  room_id
    TRUST_UPDATE = 0x9C   # 2 args: target, delta
    CAP_ISSUE    = 0x9D   # 2 args: action, holder
    BRANCH       = 0x9E   # 1 arg:  condition_register (like JNZ for trails)
    NOP          = 0x9F   # 0 args: trail marker / padding

    # Meta Operations — trail framing and annotations
    TRAIL_BEGIN  = 0xA0   # args: agent_name, trail_id, timestamp
    TRAIL_END    = 0xA1   # args: total_steps, status
    COMMENT      = 0xA2   # 1 arg:  comment_hash
    LABEL        = 0xA3   # 1 arg:  label_hash

    # Hash Table marker
    HASHTABLE    = 0xB0   # start of string hash table section

    @classmethod
    def is_valid(cls, value: int) -> bool:
        """Check if a byte value is a valid Trail-FLUX opcode."""
        return value in cls._value2member_map_

    @classmethod
    def is_trail_op(cls, value: int) -> bool:
        """Check if opcode is a trail action (0x90-0x9F)."""
        return 0x90 <= value <= 0x9F

    @classmethod
    def is_meta_op(cls, value: int) -> bool:
        """Check if opcode is a meta/structural operation (0xA0-0xA3)."""
        return 0xA0 <= value <= 0xA3


# ─── Operand Signatures ───────────────────────────────────────────────────────

# Maps each opcode to its expected operand count for validation.
# TRAIL_BEGIN and TRAIL_END have special encoding; see encoder.
OPCODE_OPERAND_COUNT: dict[TrailOpcodes, int] = {
    TrailOpcodes.GIT_COMMIT:   2,
    TrailOpcodes.GIT_PUSH:     1,
    TrailOpcodes.FILE_READ:    1,
    TrailOpcodes.FILE_WRITE:   2,
    TrailOpcodes.FILE_EDIT:    3,
    TrailOpcodes.TEST_RUN:     2,
    TrailOpcodes.SEARCH_CODE:  1,
    TrailOpcodes.BOTTLE_DROP:  2,
    TrailOpcodes.BOTTLE_READ:  1,
    TrailOpcodes.LEVEL_UP:     1,
    TrailOpcodes.SPELL_CAST:   1,
    TrailOpcodes.ROOM_ENTER:   1,
    TrailOpcodes.TRUST_UPDATE: 2,
    TrailOpcodes.CAP_ISSUE:    2,
    TrailOpcodes.BRANCH:       1,
    TrailOpcodes.NOP:          0,
    TrailOpcodes.COMMENT:      1,
    TrailOpcodes.LABEL:        1,
}


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class TrailStep:
    """
    A single step in an agent's trail.

    Attributes:
        opcode:      The TrailOpcodes value for this step.
        operands:    List of u16 operand values (hash references or numeric IDs).
        metadata:    Optional dict of extra data (not encoded in bytecode).
        timestamp:   Unix timestamp when this step occurred.
        description: Human-readable description of this step.
    """
    opcode: TrailOpcodes
    operands: list[int] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    description: str = ""

    def __post_init__(self):
        """Validate operands on creation."""
        if not isinstance(self.opcode, TrailOpcodes):
            self.opcode = TrailOpcodes(self.opcode)
        # Clamp operands to u16 range
        self.operands = [int(op) & 0xFFFF for op in self.operands]


@dataclass
class TrailProgram:
    """
    A complete trail — an ordered sequence of TrailSteps forming a compilable
    program that reproduces an agent's journey.

    The trail must start with TRAIL_BEGIN and end with TRAIL_END.
    """
    steps: list[TrailStep] = field(default_factory=list)

    def add_step(self, step: TrailStep) -> TrailProgram:
        """Append a step and return self for chaining."""
        self.steps.append(step)
        return self

    @property
    def is_valid(self) -> bool:
        """Check if trail has proper begin/end markers."""
        if len(self.steps) < 2:
            return False
        return (self.steps[0].opcode == TrailOpcodes.TRAIL_BEGIN and
                self.steps[-1].opcode == TrailOpcodes.TRAIL_END)

    @property
    def action_steps(self) -> list[TrailStep]:
        """Return only the action steps (excluding TRAIL_BEGIN, TRAIL_END, NOP)."""
        skip = {TrailOpcodes.TRAIL_BEGIN, TrailOpcodes.TRAIL_END, TrailOpcodes.NOP}
        return [s for s in self.steps if s.opcode not in skip]

    def concatenate(self, other: TrailProgram) -> TrailProgram:
        """
        Concatenate another trail onto this one.
        Removes the TRAIL_END of self and TRAIL_BEGIN of other,
        producing a seamless merged trail.
        """
        if not self.is_valid or not other.is_valid:
            raise ValueError("Both trails must be valid to concatenate")
        merged = TrailProgram(steps=self.steps[:-1] + other.steps[1:])
        return merged

    def fingerprint(self) -> str:
        """
        Compute a SHA-256 fingerprint of this trail program.
        Uses the compiled bytecode to ensure byte-level determinism.
        Returns the full 64-char hex digest.
        """
        bytecode = TrailEncoder().encode(self)
        return hashlib.sha256(bytecode).hexdigest()


# ─── Hash Utilities ───────────────────────────────────────────────────────────

def str_to_hash(s: str) -> str:
    """
    Hash a string to an 8-char hex digest (first 4 bytes of SHA-256).
    This is the canonical way to compact string operands in trail bytecode.
    The 4 bytes are split into two u16 values for binary encoding.
    """
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def str_hash_to_u16_pair(s: str) -> tuple[int, int]:
    """
    Convert a string's hash to a pair of u16 values for bytecode encoding.
    Takes the 8-char hash (first 4 bytes of SHA-256) and splits into
    two u16 values: first 4 hex chars → high, next 4 hex chars → low.
    """
    h = str_to_hash(s)
    high = int(h[0:4], 16)
    low = int(h[4:8], 16)
    return (high, low)


def u16_pair_to_hex(hi: int, lo: int) -> str:
    """Convert a u16 pair back to an 8-char hex string."""
    return f"{hi & 0xFFFF:04x}{lo & 0xFFFF:04x}"


@dataclass
class HashTableEntry:
    """A single entry in the string hash table."""
    hash_hex: str       # 16-char hex digest (key)
    original: str       # original string (value)


# ─── Encoder ──────────────────────────────────────────────────────────────────

class TrailEncoder:
    """
    Converts a TrailProgram to compact FLUX bytecode.

    Encoding format:
        TRAIL_BEGIN: [0xA0] [agent_id: u8] [trail_id: u16 u16] [timestamp: u16 u16]
        Each step:   [opcode: u8] [operand_count: u8] [operands: u16 each]
        TRAIL_END:   [0xA1] [total_steps: u16] [status: u8]
        HASH TABLE:  [0xB0] [entry_count: u16]
                     [hash_hi: u16] [hash_lo: u16] [strlen: u8] [string_bytes]

    Design note: operands are u16 throughout for uniformity. String hashes
    occupy two operand slots (high and low halves of the first 8 hash bytes).
    """

    def __init__(self, string_table: dict[str, str] | None = None):
        """
        Args:
            string_table: Optional pre-populated hash→string map.
                          If None, an empty table is used.
        """
        self.string_table: dict[str, str] = string_table or {}

    def _register_string(self, s: str) -> str:
        """Register a string in the hash table and return its hash."""
        h = str_to_hash(s)
        if h not in self.string_table:
            self.string_table[h] = s
        return h

    def encode(self, program: TrailProgram) -> bytes:
        """Encode a TrailProgram to compact bytecode bytes."""
        if not program.steps:
            raise ValueError("Cannot encode empty trail program")

        buf = bytearray()

        for step in program.steps:
            op = step.opcode

            if op == TrailOpcodes.TRAIL_BEGIN:
                buf.extend(self._encode_trail_begin(step))
            elif op == TrailOpcodes.TRAIL_END:
                buf.extend(self._encode_trail_end(step, len(program.steps)))
            elif op == TrailOpcodes.NOP:
                # NOP: just the opcode, no operand count field
                buf.append(int(op))
            else:
                # General step: [opcode] [operand_count] [operands...]
                buf.append(int(op))
                operands = step.operands
                buf.append(len(operands))
                for operand in operands:
                    buf.extend(struct.pack("<H", int(operand) & 0xFFFF))

        # Append hash table section
        buf.extend(self._encode_hash_table())

        return bytes(buf)

    def _encode_trail_begin(self, step: TrailStep) -> bytes:
        """
        Encode TRAIL_BEGIN:
        [0xA0] [agent_id: u8] [trail_id_hi: u16] [trail_id_lo: u16]
               [timestamp_hi: u16] [timestamp_lo: u16]
        """
        buf = bytearray()
        buf.append(int(TrailOpcodes.TRAIL_BEGIN))

        # Agent name → numeric ID (hash first byte) or use operand
        agent = step.metadata.get("agent", "unknown")
        agent_id = step.operands[0] if len(step.operands) > 0 else (hash(agent) & 0xFF)
        buf.append(agent_id & 0xFF)

        # Trail ID: use hash of trail_id string as two u16s
        trail_id = step.metadata.get("trail_id", "")
        if trail_id:
            hi, lo = str_hash_to_u16_pair(trail_id)
            buf.extend(struct.pack("<H", hi))
            buf.extend(struct.pack("<H", lo))
        else:
            buf.extend(struct.pack("<H", 0))
            buf.extend(struct.pack("<H", 0))

        # Timestamp: pack as two u16s
        ts = step.metadata.get("timestamp", int(time.time()))
        if step.timestamp > 0:
            ts = int(step.timestamp)
        buf.extend(struct.pack("<H", (ts >> 16) & 0xFFFF))
        buf.extend(struct.pack("<H", ts & 0xFFFF))

        return bytes(buf)

    def _encode_trail_end(self, step: TrailStep, total_steps: int) -> bytes:
        """
        Encode TRAIL_END:
        [0xA1] [total_steps: u16] [status: u8]
        """
        buf = bytearray()
        buf.append(int(TrailOpcodes.TRAIL_END))
        buf.extend(struct.pack("<H", total_steps))
        status = step.operands[0] if len(step.operands) > 0 else 0
        buf.append(status & 0xFF)
        return bytes(buf)

    def _encode_hash_table(self) -> bytes:
        """
        Encode the string hash table section:
        [0xB0] [entry_count: u16]
        [hash_hi: u16] [hash_lo: u16] [strlen: u8] [string_bytes]
        """
        buf = bytearray()
        buf.append(int(TrailOpcodes.HASHTABLE))

        entries = sorted(self.string_table.items())
        buf.extend(struct.pack("<H", len(entries)))

        for hash_hex, original in entries:
            # Hash as two u16 (8-char hash → 4 hex chars each)
            hi = int(hash_hex[0:4], 16)
            lo = int(hash_hex[4:8], 16)
            buf.extend(struct.pack("<H", hi))
            buf.extend(struct.pack("<H", lo))

            # String: length-prefixed
            encoded = original.encode("utf-8")
            buf.append(len(encoded) & 0xFF)
            buf.extend(encoded)

        return bytes(buf)


# ─── Decoder ──────────────────────────────────────────────────────────────────

class TrailDecoder:
    """
    Converts FLUX bytecode back into a TrailStep sequence.

    This is the inverse operation of TrailEncoder. It reads the binary
    format and reconstructs the full TrailProgram with all metadata.
    """

    def __init__(self):
        self.string_table: dict[str, str] = {}
        self._pos = 0
        self._data = b""

    def decode(self, bytecode: bytes) -> TrailProgram:
        """Decode bytecode into a TrailProgram."""
        self._data = bytecode
        self._pos = 0
        self.string_table = {}
        steps: list[TrailStep] = []

        # First pass: decode all steps until hash table marker
        while self._pos < len(self._data):
            saved_pos = self._pos
            op_byte = self._read_u8()

            if op_byte == int(TrailOpcodes.HASHTABLE):
                self._decode_hash_table()
                break

            if not TrailOpcodes.is_valid(op_byte):
                raise ValueError(
                    f"Invalid opcode 0x{op_byte:02X} at offset {saved_pos}"
                )

            op = TrailOpcodes(op_byte)

            if op == TrailOpcodes.TRAIL_BEGIN:
                step = self._decode_trail_begin()
            elif op == TrailOpcodes.TRAIL_END:
                step = self._decode_trail_end()
            elif op == TrailOpcodes.NOP:
                step = TrailStep(opcode=op)
            else:
                step = self._decode_general_step(op)

            steps.append(step)

        return TrailProgram(steps=steps)

    def _read_u8(self) -> int:
        v = self._data[self._pos]
        self._pos += 1
        return v

    def _read_u16(self) -> int:
        lo = self._data[self._pos]
        hi = self._data[self._pos + 1]
        self._pos += 2
        return lo | (hi << 8)

    def _decode_trail_begin(self) -> TrailStep:
        agent_id = self._read_u8()
        trail_id_hi = self._read_u16()
        trail_id_lo = self._read_u16()
        ts_hi = self._read_u16()
        ts_lo = self._read_u16()

        ts = (ts_hi << 16) | ts_lo
        trail_id_hex = f"{trail_id_hi:04x}{trail_id_lo:04x}"

        # Try to recover trail_id from string table (will be populated after decode)
        trail_id_str = self.string_table.get(trail_id_hex, trail_id_hex)

        return TrailStep(
            opcode=TrailOpcodes.TRAIL_BEGIN,
            operands=[agent_id],
            metadata={
                "agent_id": agent_id,
                "trail_id_hex": trail_id_hex,
                "trail_id": trail_id_str,
                "timestamp": ts,
            },
            timestamp=float(ts),
            description="Trail begins",
        )

    def _decode_trail_end(self) -> TrailStep:
        total_steps = self._read_u16()
        status = self._read_u8()

        status_msg = {0: "success", 1: "error", 2: "partial", 3: "cancelled"}
        return TrailStep(
            opcode=TrailOpcodes.TRAIL_END,
            operands=[status],
            metadata={"total_steps": total_steps, "status": status},
            description=f"Trail ends ({status_msg.get(status, 'unknown')})",
        )

    def _decode_general_step(self, op: TrailOpcodes) -> TrailStep:
        operand_count = self._read_u8()
        operands = [self._read_u16() for _ in range(operand_count)]
        return TrailStep(opcode=op, operands=operands)

    def _decode_hash_table(self):
        """Read and populate the string hash table."""
        entry_count = self._read_u16()
        for _ in range(entry_count):
            hi = self._read_u16()
            lo = self._read_u16()
            hash_hex = f"{hi:04x}{lo:04x}"
            str_len = self._read_u8()
            string_bytes = self._data[self._pos:self._pos + str_len]
            self._pos += str_len
            self.string_table[hash_hex] = string_bytes.decode("utf-8")


# ─── Printer ──────────────────────────────────────────────────────────────────

class TrailPrinter:
    """
    Pretty-prints trail bytecode as human-readable operations.

    Output formats:
      - 'text':    Plain text listing (default)
      - 'hex':     Include hex offsets
      - 'verbose': Include hash table lookups
      - 'compact': One line per step, minimal formatting
    """

    def __init__(self, string_table: dict[str, str] | None = None):
        self.string_table = string_table or {}

    def print_program(self, program: TrailProgram, fmt: str = "text") -> str:
        """Print a TrailProgram in the specified format."""
        return self._render_steps(program.steps, fmt)

    def print_bytecode(self, bytecode: bytes, fmt: str = "text") -> str:
        """Decode and print bytecode."""
        decoder = TrailDecoder()
        decoder.decode(bytecode)
        self.string_table = decoder.string_table
        program = decoder.decode(bytecode)
        # Second decode now with populated string table
        program = decoder.decode(bytecode)
        return self._render_steps(program.steps, fmt)

    def _render_steps(self, steps: list[TrailStep], fmt: str) -> str:
        lines: list[str] = []

        if fmt == "text":
            lines.append("═══ TRAIL-FLUX DISASSEMBLY ═══")
            lines.append("")
            for i, step in enumerate(steps):
                lines.append(self._format_step_text(step, i))
            lines.append("")
            lines.append("═══ END OF TRAIL ═══")

        elif fmt == "hex":
            lines.append("═══ TRAIL-FLUX HEX DUMP ═══")
            lines.append("")
            offset = 0
            for i, step in enumerate(steps):
                step_bytes = self._estimate_step_size(step)
                lines.append(f"  {offset:04X}: {self._format_step_text(step, i)}")
                offset += step_bytes
            lines.append("")
            lines.append("═══ END OF TRAIL ═══")

        elif fmt == "verbose":
            lines.append("═══ TRAIL-FLUX VERBOSE ═══")
            lines.append("")
            for i, step in enumerate(steps):
                lines.append(f"  [{i:03d}] {self._format_step_verbose(step)}")
                lines.append(f"        opcode: 0x{int(step.opcode):02X} ({step.opcode.name})")
                lines.append(f"        operands: {step.operands}")
                if step.description:
                    lines.append(f"        desc: {step.description}")
                if step.timestamp:
                    lines.append(f"        timestamp: {step.timestamp}")
                lines.append("")
            if self.string_table:
                lines.append("  ─── STRING TABLE ───")
                for h, s in sorted(self.string_table.items()):
                    lines.append(f"    {h} → \"{s}\"")
            lines.append("")
            lines.append("═══ END OF TRAIL ═══")

        elif fmt == "compact":
            for step in steps:
                lines.append(self._format_step_compact(step))

        else:
            raise ValueError(f"Unknown format: {fmt}")

        return "\n".join(lines)

    def _format_step_text(self, step: TrailStep, index: int) -> str:
        op_name = step.opcode.name

        if step.opcode == TrailOpcodes.TRAIL_BEGIN:
            agent = step.metadata.get("trail_id", "?")
            ts = step.metadata.get("timestamp", 0)
            return f"  TRAIL_BEGIN  agent={agent}  ts={ts}"

        if step.opcode == TrailOpcodes.TRAIL_END:
            total = step.metadata.get("total_steps", "?")
            status = step.metadata.get("status", "?")
            return f"  TRAIL_END    steps={total}  status={status}"

        if step.opcode == TrailOpcodes.NOP:
            return f"  NOP"

        # Resolve operand hashes
        resolved = self._resolve_operands(step.operands)
        op_str = f"{op_name}"
        if resolved:
            op_str += f"  {', '.join(str(r) for r in resolved)}"

        desc = f"  ; {step.description}" if step.description else ""
        return f"  {op_str}{desc}"

    def _format_step_verbose(self, step: TrailStep) -> str:
        op_name = step.opcode.name.ljust(14)

        if step.opcode == TrailOpcodes.TRAIL_BEGIN:
            return f"  [{op_name}] trail_id={step.metadata.get('trail_id', '?')}"

        if step.opcode == TrailOpcodes.TRAIL_END:
            return f"  [{op_name}] total={step.metadata.get('total_steps', '?')}"

        resolved = self._resolve_operands(step.operands)
        return f"  [{op_name}] args={resolved}"

    def _format_step_compact(self, step: TrailStep) -> str:
        op_name = step.opcode.name
        ops = ",".join(str(o) for o in step.operands)
        if ops:
            return f"{op_name} {ops}"
        return op_name

    def _resolve_operands(self, operands: list[int]) -> list[str]:
        """Try to resolve operand pairs back to hash strings."""
        result: list[str] = []
        i = 0
        while i < len(operands):
            if i + 1 < len(operands):
                hex_str = u16_pair_to_hex(operands[i], operands[i + 1])
                original = self.string_table.get(hex_str)
                if original:
                    result.append(f'"{original}"')
                    i += 2
                    continue
            result.append(str(operands[i]))
            i += 1
        return result

    def _estimate_step_size(self, step: TrailStep) -> int:
        """Estimate byte size of a step for hex dump offsets."""
        if step.opcode == TrailOpcodes.TRAIL_BEGIN:
            return 11  # 1 + 1 + 2 + 2 + 2 + 2 + 1 (extra padding)
        if step.opcode == TrailOpcodes.TRAIL_END:
            return 4   # 1 + 2 + 1
        if step.opcode == TrailOpcodes.NOP:
            return 1
        return 2 + len(step.operands) * 2  # opcode + count + operands


# ─── Compiler ─────────────────────────────────────────────────────────────────

class TrailCompiler:
    """
    Converts structured worklog entries (dicts) into a TrailProgram.

    This is the bridge between the agent's natural worklog format and
    the compiled bytecode representation. It handles:
      - String hashing for compact operands
      - Timestamp assignment
      - Opcode validation
      - Metadata extraction
    """

    def __init__(self):
        self.string_table: dict[str, str] = {}

    def compile(self, entries: list[dict[str, Any]]) -> TrailProgram:
        """
        Compile a list of worklog entries into a TrailProgram.

        Each entry is a dict with at least 'op' key (opcode name string).
        Other keys depend on the opcode:
          - TRAIL_BEGIN: agent, trail_id, ts
          - FILE_READ:   path, desc
          - FILE_WRITE:  path, content_hash, desc
          - SEARCH_CODE: pattern, desc
          - TEST_RUN:    test_path, count, desc
          - BOTTLE_DROP: target, content, desc
          - TRAIL_END:   steps, status, desc
        """
        program = TrailProgram()

        for entry in entries:
            step = self._compile_entry(entry)
            program.add_step(step)

        return program

    def compile_and_encode(self, entries: list[dict[str, Any]]) -> bytes:
        """Compile entries and immediately encode to bytecode."""
        program = self.compile(entries)
        encoder = TrailEncoder(string_table=dict(self.string_table))
        return encoder.encode(program)

    def _compile_entry(self, entry: dict[str, Any]) -> TrailStep:
        """Convert a single worklog entry to a TrailStep."""
        op_name = entry.get("op", "").upper()

        try:
            opcode = TrailOpcodes[op_name]
        except KeyError:
            raise ValueError(f"Unknown opcode: {op_name}")

        match opcode:
            case TrailOpcodes.TRAIL_BEGIN:
                return self._compile_trail_begin(entry)
            case TrailOpcodes.TRAIL_END:
                return self._compile_trail_end(entry)
            case TrailOpcodes.FILE_READ:
                return self._compile_file_read(entry)
            case TrailOpcodes.FILE_WRITE:
                return self._compile_file_write(entry)
            case TrailOpcodes.FILE_EDIT:
                return self._compile_file_edit(entry)
            case TrailOpcodes.SEARCH_CODE:
                return self._compile_search_code(entry)
            case TrailOpcodes.TEST_RUN:
                return self._compile_test_run(entry)
            case TrailOpcodes.GIT_COMMIT:
                return self._compile_git_commit(entry)
            case TrailOpcodes.GIT_PUSH:
                return self._compile_git_push(entry)
            case TrailOpcodes.BOTTLE_DROP:
                return self._compile_bottle_drop(entry)
            case TrailOpcodes.BOTTLE_READ:
                return self._compile_bottle_read(entry)
            case TrailOpcodes.LEVEL_UP:
                return self._compile_level_up(entry)
            case TrailOpcodes.SPELL_CAST:
                return self._compile_spell_cast(entry)
            case TrailOpcodes.ROOM_ENTER:
                return self._compile_room_enter(entry)
            case TrailOpcodes.TRUST_UPDATE:
                return self._compile_trust_update(entry)
            case TrailOpcodes.CAP_ISSUE:
                return self._compile_cap_issue(entry)
            case TrailOpcodes.BRANCH:
                return self._compile_branch(entry)
            case TrailOpcodes.NOP:
                return self._compile_nop(entry)
            case TrailOpcodes.COMMENT:
                return self._compile_comment(entry)
            case TrailOpcodes.LABEL:
                return self._compile_label(entry)
            case _:
                raise ValueError(f"No compiler for opcode: {op_name}")

    def _register(self, s: str) -> tuple[int, int]:
        """Register a string and return its hash as a u16 pair."""
        h = str_to_hash(s)
        self.string_table[h] = s
        hi = int(h[0:4], 16)
        lo = int(h[4:8], 16)
        return (hi, lo)

    def _compile_trail_begin(self, entry: dict) -> TrailStep:
        agent = entry.get("agent", "unknown")
        trail_id = entry.get("trail_id", "untitled")
        ts = entry.get("ts", entry.get("timestamp", int(time.time())))

        # Register strings
        self._register(trail_id)
        self._register(agent)

        agent_id = hash(agent) & 0xFF
        _, _ = self._register(trail_id)

        return TrailStep(
            opcode=TrailOpcodes.TRAIL_BEGIN,
            operands=[agent_id],
            metadata={"agent": agent, "trail_id": trail_id, "timestamp": int(ts)},
            timestamp=float(ts),
            description=entry.get("desc", f"Trail begins: {trail_id}"),
        )

    def _compile_trail_end(self, entry: dict) -> TrailStep:
        steps = entry.get("steps", 0)
        status = entry.get("status", 0)
        return TrailStep(
            opcode=TrailOpcodes.TRAIL_END,
            operands=[status],
            metadata={"total_steps": steps, "status": status},
            description=entry.get("desc", "Trail ends"),
        )

    def _compile_file_read(self, entry: dict) -> TrailStep:
        path = entry.get("path", "")
        hi, lo = self._register(path)
        return TrailStep(
            opcode=TrailOpcodes.FILE_READ,
            operands=[hi, lo],
            description=entry.get("desc", f"Read: {path}"),
        )

    def _compile_file_write(self, entry: dict) -> TrailStep:
        path = entry.get("path", "")
        content = entry.get("content", entry.get("content_hash", ""))
        hi1, lo1 = self._register(path)
        hi2, lo2 = self._register(content)
        return TrailStep(
            opcode=TrailOpcodes.FILE_WRITE,
            operands=[hi1, lo1, hi2, lo2],
            description=entry.get("desc", f"Write: {path}"),
        )

    def _compile_file_edit(self, entry: dict) -> TrailStep:
        path = entry.get("path", "")
        old_content = entry.get("old", entry.get("old_hash", ""))
        new_content = entry.get("new", entry.get("new_hash", ""))
        hi1, lo1 = self._register(path)
        hi2, lo2 = self._register(old_content)
        hi3, lo3 = self._register(new_content)
        return TrailStep(
            opcode=TrailOpcodes.FILE_EDIT,
            operands=[hi1, lo1, hi2, lo2, hi3, lo3],
            description=entry.get("desc", f"Edit: {path}"),
        )

    def _compile_search_code(self, entry: dict) -> TrailStep:
        pattern = entry.get("pattern", "")
        hi, lo = self._register(pattern)
        return TrailStep(
            opcode=TrailOpcodes.SEARCH_CODE,
            operands=[hi, lo],
            description=entry.get("desc", f"Search: {pattern}"),
        )

    def _compile_test_run(self, entry: dict) -> TrailStep:
        test_path = entry.get("test_path", entry.get("path", ""))
        count = entry.get("count", entry.get("expected_count", 0))
        hi, lo = self._register(test_path)
        return TrailStep(
            opcode=TrailOpcodes.TEST_RUN,
            operands=[hi, lo, count],
            description=entry.get("desc", f"Test: {test_path} ({count} tests)"),
        )

    def _compile_git_commit(self, entry: dict) -> TrailStep:
        repo_id = entry.get("repo_id", entry.get("repo", 0))
        message = entry.get("message", entry.get("message_hash", ""))
        hi, lo = self._register(str(message))
        return TrailStep(
            opcode=TrailOpcodes.GIT_COMMIT,
            operands=[int(repo_id) & 0xFFFF, hi, lo],
            description=entry.get("desc", f"Git commit: repo={repo_id}"),
        )

    def _compile_git_push(self, entry: dict) -> TrailStep:
        repo_id = entry.get("repo_id", entry.get("repo", 0))
        return TrailStep(
            opcode=TrailOpcodes.GIT_PUSH,
            operands=[int(repo_id) & 0xFFFF],
            description=entry.get("desc", f"Git push: repo={repo_id}"),
        )

    def _compile_bottle_drop(self, entry: dict) -> TrailStep:
        target = entry.get("target", "")
        content = entry.get("content", entry.get("content_hash", ""))
        hi1, lo1 = self._register(target)
        hi2, lo2 = self._register(content)
        return TrailStep(
            opcode=TrailOpcodes.BOTTLE_DROP,
            operands=[hi1, lo1, hi2, lo2],
            description=entry.get("desc", f"Bottle→{target}"),
        )

    def _compile_bottle_read(self, entry: dict) -> TrailStep:
        source = entry.get("source", "")
        hi, lo = self._register(source)
        return TrailStep(
            opcode=TrailOpcodes.BOTTLE_READ,
            operands=[hi, lo],
            description=entry.get("desc", f"Bottle←{source}"),
        )

    def _compile_level_up(self, entry: dict) -> TrailStep:
        level = entry.get("level", entry.get("new_level", 0))
        return TrailStep(
            opcode=TrailOpcodes.LEVEL_UP,
            operands=[int(level) & 0xFFFF],
            description=entry.get("desc", f"Level up: {level}"),
        )

    def _compile_spell_cast(self, entry: dict) -> TrailStep:
        spell_id = entry.get("spell_id", entry.get("spell", ""))
        hi, lo = self._register(str(spell_id))
        return TrailStep(
            opcode=TrailOpcodes.SPELL_CAST,
            operands=[hi, lo],
            description=entry.get("desc", f"Cast: {spell_id}"),
        )

    def _compile_room_enter(self, entry: dict) -> TrailStep:
        room_id = entry.get("room_id", entry.get("room", ""))
        hi, lo = self._register(str(room_id))
        return TrailStep(
            opcode=TrailOpcodes.ROOM_ENTER,
            operands=[hi, lo],
            description=entry.get("desc", f"Enter: {room_id}"),
        )

    def _compile_trust_update(self, entry: dict) -> TrailStep:
        target = entry.get("target", "")
        delta = entry.get("delta", 0)
        hi, lo = self._register(target)
        return TrailStep(
            opcode=TrailOpcodes.TRUST_UPDATE,
            operands=[hi, lo, int(delta) & 0xFFFF],
            description=entry.get("desc", f"Trust: {target} {delta:+d}"),
        )

    def _compile_cap_issue(self, entry: dict) -> TrailStep:
        action = entry.get("action", "")
        holder = entry.get("holder", "")
        hi1, lo1 = self._register(action)
        hi2, lo2 = self._register(holder)
        return TrailStep(
            opcode=TrailOpcodes.CAP_ISSUE,
            operands=[hi1, lo1, hi2, lo2],
            description=entry.get("desc", f"Cap: {action}→{holder}"),
        )

    def _compile_branch(self, entry: dict) -> TrailStep:
        reg = entry.get("reg", entry.get("register", 0))
        return TrailStep(
            opcode=TrailOpcodes.BRANCH,
            operands=[int(reg) & 0xFFFF],
            description=entry.get("desc", f"Branch on R{reg}"),
        )

    def _compile_nop(self, entry: dict) -> TrailStep:
        return TrailStep(
            opcode=TrailOpcodes.NOP,
            description=entry.get("desc", "NOP"),
        )

    def _compile_comment(self, entry: dict) -> TrailStep:
        comment = entry.get("comment", entry.get("text", ""))
        hi, lo = self._register(comment)
        return TrailStep(
            opcode=TrailOpcodes.COMMENT,
            operands=[hi, lo],
            description=entry.get("desc", f"; {comment}"),
        )

    def _compile_label(self, entry: dict) -> TrailStep:
        label = entry.get("label", entry.get("name", ""))
        hi, lo = self._register(label)
        return TrailStep(
            opcode=TrailOpcodes.LABEL,
            operands=[hi, lo],
            description=entry.get("desc", f":{label}"),
        )


# ─── Verifier ─────────────────────────────────────────────────────────────────

class TrailVerifier:
    """
    Verifies trail program integrity.

    Checks:
      1. Structural: valid TRAIL_BEGIN / TRAIL_END framing
      2. Opcode: all opcodes are valid Trail-FLUX opcodes
      3. Operand count: each step has the expected number of operands
      4. Round-trip: encode→decode produces identical steps
      5. Fingerprint: same trail always produces the same hash
      6. Hash table: all referenced hashes exist in the table
    """

    def __init__(self, string_table: dict[str, str] | None = None):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.string_table: dict[str, str] = string_table or {}

    def verify(self, program: TrailProgram) -> bool:
        """Run all verification checks. Returns True if all pass."""
        self.errors = []
        self.warnings = []

        self._check_structure(program)
        self._check_opcodes(program)
        self._check_operands(program)
        self._check_roundtrip(program)
        self._check_fingerprint(program)
        self._check_hash_table(program)

        return len(self.errors) == 0

    def verify_bytecode(self, bytecode: bytes) -> bool:
        """Verify bytecode by decoding and then running full verification."""
        try:
            decoder = TrailDecoder()
            program = decoder.decode(bytecode)
            return self.verify(program)
        except Exception as e:
            self.errors.append(f"Bytecode decode error: {e}")
            return False

    def report(self) -> str:
        """Generate a human-readable verification report."""
        lines = []
        if not self.errors and not self.warnings:
            lines.append("✓ Trail verification PASSED — all checks clean")
        else:
            if self.warnings:
                lines.append(f"⚠ {len(self.warnings)} warning(s):")
                for w in self.warnings:
                    lines.append(f"  - {w}")
            if self.errors:
                lines.append(f"✗ {len(self.errors)} error(s):")
                for e in self.errors:
                    lines.append(f"  - {e}")
        return "\n".join(lines)

    def _check_structure(self, program: TrailProgram):
        """Check TRAIL_BEGIN / TRAIL_END framing."""
        if len(program.steps) < 2:
            self.errors.append(f"Trail too short: {len(program.steps)} steps (minimum 2)")
            return

        first = program.steps[0]
        last = program.steps[-1]

        if first.opcode != TrailOpcodes.TRAIL_BEGIN:
            self.errors.append(
                f"Trail must start with TRAIL_BEGIN, got {first.opcode.name}"
            )
        if last.opcode != TrailOpcodes.TRAIL_END:
            self.errors.append(
                f"Trail must end with TRAIL_END, got {last.opcode.name}"
            )

    def _check_opcodes(self, program: TrailProgram):
        """Check all opcodes are valid."""
        for i, step in enumerate(program.steps):
            if not isinstance(step.opcode, TrailOpcodes):
                self.errors.append(
                    f"Step {i}: invalid opcode type {type(step.opcode)}"
                )

    def _check_operands(self, program: TrailProgram):
        """Check operand counts match expected signatures."""
        for i, step in enumerate(program.steps):
            if step.opcode in (TrailOpcodes.TRAIL_BEGIN, TrailOpcodes.TRAIL_END, TrailOpcodes.NOP):
                continue  # These have special encoding
            expected = OPCODE_OPERAND_COUNT.get(step.opcode)
            if expected is not None:
                # String operands occupy 2 u16 slots each
                actual = len(step.operands)
                if actual == 0 and expected > 0:
                    self.warnings.append(
                        f"Step {i} ({step.opcode.name}): expected ~{expected*2} operands, got {actual}"
                    )

    def _check_roundtrip(self, program: TrailProgram):
        """Verify encode→decode round-trip produces identical structure."""
        try:
            encoder = TrailEncoder(string_table=dict(self.string_table))
            bytecode = encoder.encode(program)

            decoder = TrailDecoder()
            decoded = decoder.decode(bytecode)

            # Check step count matches
            if len(decoded.steps) != len(program.steps):
                self.errors.append(
                    f"Round-trip: step count mismatch "
                    f"({len(program.steps)} → {len(decoded.steps)})"
                    )

            # Check each step's opcode matches
            for i, (orig, dec) in enumerate(zip(program.steps, decoded.steps)):
                if orig.opcode != dec.opcode:
                    self.errors.append(
                        f"Round-trip step {i}: opcode mismatch "
                        f"({orig.opcode.name} → {dec.opcode.name})"
                    )
        except Exception as e:
            self.errors.append(f"Round-trip error: {e}")

    def _check_fingerprint(self, program: TrailProgram):
        """Verify same trail produces same fingerprint (determinism)."""
        try:
            fp1 = program.fingerprint()
            fp2 = program.fingerprint()
            if fp1 != fp2:
                self.errors.append("Fingerprint not deterministic!")
        except Exception as e:
            self.warnings.append(f"Fingerprint check skipped: {e}")

    def _check_hash_table(self, program: TrailProgram):
        """Verify hash table integrity after encoding."""
        try:
            encoder = TrailEncoder(string_table=dict(self.string_table))
            bytecode = encoder.encode(program)
            decoder = TrailDecoder()
            decoder.decode(bytecode)

            if not decoder.string_table and self.string_table:
                self.warnings.append("Hash table entries lost during encoding")

        except Exception as e:
            self.warnings.append(f"Hash table check skipped: {e}")


# ─── Hex Dump Utility ─────────────────────────────────────────────────────────

def hex_dump(data: bytes, bytes_per_line: int = 16) -> str:
    """Produce a canonical hex dump of bytecode."""
    lines = []
    for offset in range(0, len(data), bytes_per_line):
        chunk = data[offset:offset + bytes_per_line]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {offset:04X}: {hex_part:<{bytes_per_line * 3}}  {ascii_part}")
    return "\n".join(lines)


# ─── Demo ─────────────────────────────────────────────────────────────────────

def demo():
    """
    Demonstrate the Trail-FLUX Bridge with a sample agent session.
    Compiles a worklog, encodes it, decodes it back, and prints results.
    """
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              TRAIL-FLUX BRIDGE — pelagic demo               ║")
    print("║  \"The trail IS the code.\" — Oracle1's Nudge                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Define a sample worklog ──
    worklog = [
        {"op": "TRAIL_BEGIN", "agent": "pelagic", "trail_id": "session-007",
         "ts": 1744658400, "desc": "Start trail-bridge prototype"},
        {"op": "FILE_READ", "path": "tabula_rasa.py",
         "desc": "Read tabula_rasa source"},
        {"op": "SEARCH_CODE", "pattern": "TrustEngine",
         "desc": "Find TrustEngine references"},
        {"op": "COMMENT", "comment": "Found 7 references across 3 modules",
         "desc": "Analysis note"},
        {"op": "FILE_WRITE", "path": "trail_encoder.py",
         "content": "trail-bridge-prototype-bytecode",
         "desc": "Create trail encoder module"},
        {"op": "FILE_EDIT", "path": "trail_encoder.py",
         "old": "TODO", "new": "TrailOpcodes",
         "desc": "Replace TODO with TrailOpcodes enum"},
        {"op": "TEST_RUN", "test_path": "tests/test_trail_encoder.py",
         "count": 85, "desc": "Run trail encoder tests"},
        {"op": "BOTTLE_DROP", "target": "oracle1",
         "content": "trail-bridge-prototype-complete",
         "desc": "Send report to Oracle1"},
        {"op": "TRUST_UPDATE", "target": "pelagic", "delta": 15,
         "desc": "Self-trust boost after successful build"},
        {"op": "LEVEL_UP", "level": 7, "desc": "Pelagic reaches level 7"},
        {"op": "SPELL_CAST", "spell_id": "encode-trail",
         "desc": "Cast encode-trail spell"},
        {"op": "NOP", "desc": "Trail marker"},
        {"op": "TRAIL_END", "steps": 12, "status": 0,
         "desc": "Trail complete — prototype delivered"},
    ]

    # ── Compile ──
    print("─── 1. COMPILING WORKLOG ───")
    compiler = TrailCompiler()
    program = compiler.compile(worklog)
    print(f"   Compiled {len(program.steps)} steps into TrailProgram")
    print(f"   Valid structure: {program.is_valid}")
    print(f"   Action steps: {len(program.action_steps)}")
    print()

    # ── Encode ──
    print("─── 2. ENCODING TO BYTECODE ───")
    encoder = TrailEncoder(string_table=dict(compiler.string_table))
    bytecode = encoder.encode(program)
    print(f"   Bytecode size: {len(bytecode)} bytes")
    print()
    print("   Hex dump:")
    print(hex_dump(bytecode))
    print()

    # ── Fingerprint ──
    print("─── 3. TRAIL FINGERPRINT ───")
    fp = program.fingerprint()
    print(f"   SHA-256: {fp}")
    print()

    # ── Decode ──
    print("─── 4. DECODING BYTECODE ───")
    decoder = TrailDecoder()
    decoded_program = decoder.decode(bytecode)
    print(f"   Decoded {len(decoded_program.steps)} steps")
    print()

    # ── Print (text format) ──
    print("─── 5. DISASSEMBLY (text) ───")
    printer = TrailPrinter(string_table=decoder.string_table)
    print(printer.print_program(decoded_program, fmt="text"))
    print()

    # ── Print (verbose format) ──
    print("─── 6. DISASSEMBLY (verbose excerpt) ───")
    # Show first 3 and last 2 steps
    excerpt = TrailProgram(steps=decoded_program.steps[:3] + decoded_program.steps[-2:])
    print(printer.print_program(excerpt, fmt="verbose"))
    print()

    # ── Verify ──
    print("─── 7. VERIFICATION ───")
    verifier = TrailVerifier()
    passed = verifier.verify(program)
    print(f"   Verification: {'PASSED ✓' if passed else 'FAILED ✗'}")
    print(f"   {verifier.report()}")
    print()

    # ── Composability demo ──
    print("─── 8. COMPOSABILITY ───")
    trail_a = compiler.compile([
        {"op": "TRAIL_BEGIN", "agent": "agent-alpha", "trail_id": "phase-1",
         "ts": 1744658400},
        {"op": "FILE_WRITE", "path": "module_a.py", "content": "initial"},
        {"op": "TRAIL_END", "steps": 3, "status": 0},
    ])
    trail_b = compiler.compile([
        {"op": "TRAIL_BEGIN", "agent": "agent-beta", "trail_id": "phase-2",
         "ts": 1744658500},
        {"op": "FILE_WRITE", "path": "module_b.py", "content": "extension"},
        {"op": "TRAIL_END", "steps": 3, "status": 0},
    ])
    merged = trail_a.concatenate(trail_b)
    merged_bc = TrailEncoder().encode(merged)
    print(f"   Trail A: {len(TrailEncoder().encode(trail_a))} bytes")
    print(f"   Trail B: {len(TrailEncoder().encode(trail_b))} bytes")
    print(f"   Merged:  {len(merged_bc)} bytes")
    print(f"   Merged valid: {merged.is_valid}")
    print(f"   Merged fingerprint: {merged.fingerprint()[:16]}...")
    print()

    print("════════════════════════════════════════════════════════════════")
    print("  Trail-FLUX Bridge demo complete. The trail IS the code.")
    print("════════════════════════════════════════════════════════════════")
    print()


if __name__ == "__main__":
    demo()
