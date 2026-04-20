"""
Comprehensive test suite for the Trail-FLUX Bridge system.

Test categories:
  1. Opcode encoding/decoding (each opcode round-trips correctly)
  2. TrailStep serialization/deserialization
  3. TrailProgram compilation and round-trip
  4. TrailEncoder: step sequences → bytecode → step sequences
  5. TrailDecoder: bytecode → human-readable output
  6. TrailPrinter: various output formats
  7. TrailCompiler: structured input → TrailProgram
  8. TrailVerifier: integrity checks, hash verification
  9. Hash table: string storage and retrieval
  10. Composability: concatenating trails
  11. Trail fingerprinting: same trail → same hash
  12. Edge cases: empty trail, single step, very long trail, unicode paths

# [pelagic] Trail-FLUX Bridge test suite — session-007
"""

import sys
import os
import unittest

# Ensure the module can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trail_encoder import (
    TrailOpcodes,
    TrailStep,
    TrailProgram,
    TrailEncoder,
    TrailDecoder,
    TrailPrinter,
    TrailCompiler,
    TrailVerifier,
    str_to_hash,
    str_hash_to_u16_pair,
    u16_pair_to_hex,
    hex_dump,
    OPCODE_OPERAND_COUNT,
)


# ─── Helper ───────────────────────────────────────────────────────────────────

def make_minimal_trail(agent: str = "test-agent", trail_id: str = "test-001") -> TrailProgram:
    """Create a minimal valid trail program."""
    return TrailProgram(steps=[
        TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[hash(agent) & 0xFF],
                  metadata={"agent": agent, "trail_id": trail_id, "timestamp": 1000}),
        TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                  metadata={"total_steps": 2, "status": 0}),
    ])


def make_sample_trail() -> TrailProgram:
    """Create a sample trail with various step types."""
    return TrailProgram(steps=[
        TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[42],
                  metadata={"agent": "pelagic", "trail_id": "session-007", "timestamp": 1744658400}),
        TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0x1234, 0x5678]),
        TrailStep(opcode=TrailOpcodes.SEARCH_CODE, operands=[0xABCD, 0xEF01]),
        TrailStep(opcode=TrailOpcodes.FILE_WRITE, operands=[0x1111, 0x2222, 0x3333, 0x4444]),
        TrailStep(opcode=TrailOpcodes.TEST_RUN, operands=[0x5555, 0x6666, 50]),
        TrailStep(opcode=TrailOpcodes.BOTTLE_DROP, operands=[0x7777, 0x8888, 0x9999, 0xAAAA]),
        TrailStep(opcode=TrailOpcodes.NOP),
        TrailStep(opcode=TrailOpcodes.COMMENT, operands=[0xBBBB, 0xCCCC]),
        TrailStep(opcode=TrailOpcodes.LABEL, operands=[0xDDDD, 0xEEEE]),
        TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[7]),
        TrailStep(opcode=TrailOpcodes.SPELL_CAST, operands=[0x1111, 0x2222]),
        TrailStep(opcode=TrailOpcodes.ROOM_ENTER, operands=[0x3333, 0x4444]),
        TrailStep(opcode=TrailOpcodes.TRUST_UPDATE, operands=[0x5555, 0x6666, 15]),
        TrailStep(opcode=TrailOpcodes.CAP_ISSUE, operands=[0x7777, 0x8888, 0x9999, 0xAAAA]),
        TrailStep(opcode=TrailOpcodes.BRANCH, operands=[3]),
        TrailStep(opcode=TrailOpcodes.GIT_COMMIT, operands=[1, 0xBBBB, 0xCCCC]),
        TrailStep(opcode=TrailOpcodes.GIT_PUSH, operands=[1]),
        TrailStep(opcode=TrailOpcodes.BOTTLE_READ, operands=[0xDDDD, 0xEEEE]),
        TrailStep(opcode=TrailOpcodes.FILE_EDIT, operands=[0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666]),
        TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                  metadata={"total_steps": 21, "status": 0}),
    ])


# ═════════════════════════════════════════════════════════════════════════════
# 1. Opcode Encoding/Decoding
# ═════════════════════════════════════════════════════════════════════════════

class TestOpcodes(unittest.TestCase):
    """Test that all Trail-FLUX opcodes are correctly defined and round-trip."""

    def test_trail_operations_range(self):
        """All trail ops should be in 0x90-0x9F."""
        trail_ops = [
            TrailOpcodes.GIT_COMMIT, TrailOpcodes.GIT_PUSH, TrailOpcodes.FILE_READ,
            TrailOpcodes.FILE_WRITE, TrailOpcodes.FILE_EDIT, TrailOpcodes.TEST_RUN,
            TrailOpcodes.SEARCH_CODE, TrailOpcodes.BOTTLE_DROP, TrailOpcodes.BOTTLE_READ,
            TrailOpcodes.LEVEL_UP, TrailOpcodes.SPELL_CAST, TrailOpcodes.ROOM_ENTER,
            TrailOpcodes.TRUST_UPDATE, TrailOpcodes.CAP_ISSUE, TrailOpcodes.BRANCH,
            TrailOpcodes.NOP,
        ]
        for op in trail_ops:
            self.assertTrue(0x90 <= op <= 0x9F, f"{op.name}=0x{op:02X} outside trail range")

    def test_meta_operations_range(self):
        """Meta ops should be in 0xA0-0xA3."""
        meta_ops = [
            TrailOpcodes.TRAIL_BEGIN, TrailOpcodes.TRAIL_END,
            TrailOpcodes.COMMENT, TrailOpcodes.LABEL,
        ]
        for op in meta_ops:
            self.assertTrue(0xA0 <= op <= 0xA3, f"{op.name}=0x{op:02X} outside meta range")

    def test_hashtable_marker(self):
        """Hash table marker should be 0xB0."""
        self.assertEqual(TrailOpcodes.HASHTABLE, 0xB0)

    def test_no_conflict_with_math_isa(self):
        """Trail opcodes should not conflict with FLUX math ISA (0x02-0x80)."""
        for op in TrailOpcodes:
            self.assertFalse(0x02 <= op <= 0x80,
                           f"{op.name}=0x{op:02X} conflicts with math ISA")

    def test_is_valid_true(self):
        """Valid opcodes should pass is_valid check."""
        self.assertTrue(TrailOpcodes.is_valid(0x90))
        self.assertTrue(TrailOpcodes.is_valid(0xA0))
        self.assertTrue(TrailOpcodes.is_valid(0xB0))

    def test_is_valid_false(self):
        """Invalid bytes should fail is_valid check."""
        self.assertFalse(TrailOpcodes.is_valid(0x00))
        self.assertFalse(TrailOpcodes.is_valid(0x50))
        self.assertFalse(TrailOpcodes.is_valid(0xFF))

    def test_is_trail_op(self):
        """Trail ops (0x90-0x9F) should be identified."""
        self.assertTrue(TrailOpcodes.is_trail_op(0x90))
        self.assertTrue(TrailOpcodes.is_trail_op(0x9F))
        self.assertFalse(TrailOpcodes.is_trail_op(0xA0))
        self.assertFalse(TrailOpcodes.is_trail_op(0x80))

    def test_is_meta_op(self):
        """Meta ops (0xA0-0xA3) should be identified."""
        self.assertTrue(TrailOpcodes.is_meta_op(0xA0))
        self.assertTrue(TrailOpcodes.is_meta_op(0xA3))
        self.assertFalse(TrailOpcodes.is_meta_op(0x90))
        self.assertFalse(TrailOpcodes.is_meta_op(0xB0))

    def test_opcode_int_enum_value(self):
        """Each opcode should have correct byte value."""
        self.assertEqual(TrailOpcodes.GIT_COMMIT, 0x90)
        self.assertEqual(TrailOpcodes.NOP, 0x9F)
        self.assertEqual(TrailOpcodes.TRAIL_BEGIN, 0xA0)
        self.assertEqual(TrailOpcodes.TRAIL_END, 0xA1)
        self.assertEqual(TrailOpcodes.HASHTABLE, 0xB0)

    def test_opcode_from_name(self):
        """Should be able to construct opcodes from names."""
        op = TrailOpcodes["FILE_READ"]
        self.assertEqual(op, 0x92)
        self.assertEqual(op.name, "FILE_READ")

    def test_opcode_from_value(self):
        """Should be able to construct opcodes from values."""
        op = TrailOpcodes(0x93)
        self.assertEqual(op.name, "FILE_WRITE")

    def test_all_opcode_names_unique(self):
        """All opcode names should be unique."""
        names = [op.name for op in TrailOpcodes]
        self.assertEqual(len(names), len(set(names)))

    def test_operand_signatures_defined(self):
        """Each trail op should have an operand count defined."""
        for op in TrailOpcodes:
            if op not in (TrailOpcodes.TRAIL_BEGIN, TrailOpcodes.TRAIL_END,
                          TrailOpcodes.HASHTABLE):
                self.assertIn(op, OPCODE_OPERAND_COUNT, f"No operand count for {op.name}")


# ═════════════════════════════════════════════════════════════════════════════
# 2. TrailStep Serialization/Deserialization
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailStep(unittest.TestCase):
    """Test TrailStep dataclass behavior."""

    def test_basic_creation(self):
        """TrailStep should store opcode and operands."""
        step = TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0x1234, 0x5678])
        self.assertEqual(step.opcode, TrailOpcodes.FILE_READ)
        self.assertEqual(step.operands, [0x1234, 0x5678])

    def test_creation_from_int_opcode(self):
        """TrailStep should accept int opcode and convert to enum."""
        step = TrailStep(opcode=0x92, operands=[0, 0])
        self.assertIsInstance(step.opcode, TrailOpcodes)
        self.assertEqual(step.opcode, TrailOpcodes.FILE_READ)

    def test_operands_clamped_to_u16(self):
        """Operands should be clamped to u16 range."""
        step = TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[70000])
        self.assertEqual(step.operands[0], 70000 & 0xFFFF)

    def test_negative_operand_wrapped(self):
        """Negative operands should wrap to u16."""
        step = TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[-1])
        self.assertEqual(step.operands[0], 0xFFFF)

    def test_default_metadata(self):
        """Default metadata should be empty dict."""
        step = TrailStep(opcode=TrailOpcodes.NOP)
        self.assertEqual(step.metadata, {})

    def test_default_timestamp(self):
        """Default timestamp should be 0.0."""
        step = TrailStep(opcode=TrailOpcodes.NOP)
        self.assertEqual(step.timestamp, 0.0)

    def test_default_description(self):
        """Default description should be empty string."""
        step = TrailStep(opcode=TrailOpcodes.NOP)
        self.assertEqual(step.description, "")

    def test_default_operands(self):
        """Default operands should be empty list."""
        step = TrailStep(opcode=TrailOpcodes.NOP)
        self.assertEqual(step.operands, [])

    def test_metadata_stored(self):
        """Metadata dict should be stored as-is."""
        step = TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                        metadata={"agent": "test", "trail_id": "x"})
        self.assertEqual(step.metadata["agent"], "test")


# ═════════════════════════════════════════════════════════════════════════════
# 3. TrailProgram Compilation and Round-Trip
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailProgram(unittest.TestCase):
    """Test TrailProgram dataclass and operations."""

    def test_empty_program(self):
        """Empty program should have no steps."""
        program = TrailProgram()
        self.assertEqual(len(program.steps), 0)

    def test_add_step(self):
        """add_step should append and return self."""
        program = TrailProgram()
        step = TrailStep(opcode=TrailOpcodes.NOP)
        result = program.add_step(step)
        self.assertEqual(len(program.steps), 1)
        self.assertIs(result, program)  # chaining

    def test_is_valid_minimal(self):
        """Minimal valid trail: TRAIL_BEGIN + TRAIL_END."""
        program = make_minimal_trail()
        self.assertTrue(program.is_valid)

    def test_is_valid_no_begin(self):
        """Trail without TRAIL_BEGIN is invalid."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 2, "status": 0}),
        ])
        self.assertFalse(program.is_valid)

    def test_is_valid_no_end(self):
        """Trail without TRAIL_END is invalid."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1]),
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
        ])
        self.assertFalse(program.is_valid)

    def test_is_valid_too_short(self):
        """Trail with only one step is invalid."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1]),
        ])
        self.assertFalse(program.is_valid)

    def test_action_steps_excludes_framing(self):
        """action_steps should exclude TRAIL_BEGIN, TRAIL_END, NOP."""
        program = make_minimal_trail()
        self.assertEqual(len(program.action_steps), 0)

    def test_action_steps_includes_actions(self):
        """action_steps should include non-framing operations."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1]),
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.SEARCH_CODE, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.NOP),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 5, "status": 0}),
        ])
        self.assertEqual(len(program.action_steps), 2)

    def test_concatenate_two_valid_trails(self):
        """Two valid trails can be concatenated."""
        a = make_minimal_trail("agent-a", "trail-a")
        b = make_minimal_trail("agent-b", "trail-b")
        merged = a.concatenate(b)
        self.assertTrue(merged.is_valid)
        # Minimal trails: each has 2 steps (BEGIN+END).
        # Concat drops A's END and B's BEGIN, so 2+2-2=2 steps.
        self.assertEqual(len(merged.steps), 2)

    def test_concatenate_invalid_raises(self):
        """Concatenating invalid trail raises ValueError."""
        a = make_minimal_trail()
        b = TrailProgram()  # invalid
        with self.assertRaises(ValueError):
            a.concatenate(b)

    def test_fingerprint_deterministic(self):
        """Same program should produce same fingerprint."""
        program = make_sample_trail()
        fp1 = program.fingerprint()
        fp2 = program.fingerprint()
        self.assertEqual(fp1, fp2)

    def test_fingerprint_different_programs(self):
        """Different programs should produce different fingerprints."""
        a = make_minimal_trail("agent-a")
        b = make_minimal_trail("agent-b")
        self.assertNotEqual(a.fingerprint(), b.fingerprint())


# ═════════════════════════════════════════════════════════════════════════════
# 4. TrailEncoder: step sequences → bytecode → step sequences
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailEncoder(unittest.TestCase):
    """Test TrailEncoder encoding functionality."""

    def test_encode_minimal_trail(self):
        """Minimal trail should encode to bytes."""
        program = make_minimal_trail()
        encoder = TrailEncoder()
        bytecode = encoder.encode(program)
        self.assertIsInstance(bytecode, bytes)
        self.assertGreater(len(bytecode), 0)

    def test_encode_starts_with_trail_begin(self):
        """Encoded bytecode should start with TRAIL_BEGIN opcode."""
        program = make_minimal_trail()
        encoder = TrailEncoder()
        bytecode = encoder.encode(program)
        self.assertEqual(bytecode[0], int(TrailOpcodes.TRAIL_BEGIN))

    def test_encode_includes_hashtable(self):
        """Encoded bytecode should include hash table marker."""
        program = make_minimal_trail()
        encoder = TrailEncoder()
        bytecode = encoder.encode(program)
        # Hash table marker should be somewhere in the bytecode
        self.assertIn(int(TrailOpcodes.HASHTABLE), bytecode)

    def test_encode_empty_raises(self):
        """Encoding empty program raises ValueError."""
        program = TrailProgram()
        encoder = TrailEncoder()
        with self.assertRaises(ValueError):
            encoder.encode(program)

    def test_encode_nop_single_byte(self):
        """NOP step should encode as a single byte (just the opcode)."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.NOP),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        encoder = TrailEncoder()
        bytecode = encoder.encode(program)
        # Find NOP in bytecode (0x9F not followed by operand count)
        for i in range(len(bytecode)):
            if bytecode[i] == 0x9F:
                # NOP should be followed by TRAIL_END (0xA1) or another valid opcode
                next_byte = bytecode[i + 1]
                self.assertIn(next_byte, [0xA1, 0x90, 0x9F, 0xB0])
                break

    def test_encode_sample_trail(self):
        """Sample trail with all opcodes should encode without error."""
        program = make_sample_trail()
        encoder = TrailEncoder()
        bytecode = encoder.encode(program)
        self.assertGreater(len(bytecode), 50)

    def test_encode_string_table_populated(self):
        """Encoder should populate string table when strings are registered."""
        encoder = TrailEncoder()
        encoder._register_string("hello")
        self.assertIn(str_to_hash("hello"), encoder.string_table)

    def test_encode_string_table_no_duplicates(self):
        """Registering same string twice should not duplicate."""
        encoder = TrailEncoder()
        encoder._register_string("hello")
        encoder._register_string("hello")
        self.assertEqual(len(encoder.string_table), 1)

    def test_encode_preserves_operand_values(self):
        """Operand values should survive encode→decode round trip."""
        step = TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[42])
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            step,
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        # Find the LEVEL_UP step
        for s in decoded.steps:
            if s.opcode == TrailOpcodes.LEVEL_UP:
                self.assertEqual(s.operands, [42])
                return
        self.fail("LEVEL_UP step not found in decoded program")

    def test_encode_three_operand_step(self):
        """FILE_EDIT (3 args) should encode all operands."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.FILE_EDIT,
                     operands=[0x11, 0x22, 0x33, 0x44, 0x55, 0x66]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        for s in decoded.steps:
            if s.opcode == TrailOpcodes.FILE_EDIT:
                self.assertEqual(s.operands, [0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
                return
        self.fail("FILE_EDIT step not found")


# ═════════════════════════════════════════════════════════════════════════════
# 5. TrailDecoder: bytecode → human-readable output
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailDecoder(unittest.TestCase):
    """Test TrailDecoder decoding functionality."""

    def test_decode_minimal_trail(self):
        """Minimal trail should decode to TrailProgram."""
        program = make_minimal_trail()
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        self.assertIsInstance(decoded, TrailProgram)

    def test_decode_step_count(self):
        """Decoded step count should match original."""
        program = make_sample_trail()
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        self.assertEqual(len(decoded.steps), len(program.steps))

    def test_decode_first_step_is_trail_begin(self):
        """First decoded step should be TRAIL_BEGIN."""
        program = make_minimal_trail()
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        self.assertEqual(decoded.steps[0].opcode, TrailOpcodes.TRAIL_BEGIN)

    def test_decode_last_step_is_trail_end(self):
        """Last decoded step should be TRAIL_END."""
        program = make_minimal_trail()
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        self.assertEqual(decoded.steps[-1].opcode, TrailOpcodes.TRAIL_END)

    def test_decode_nop(self):
        """NOP should decode with no operands."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.NOP),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        nop_steps = [s for s in decoded.steps if s.opcode == TrailOpcodes.NOP]
        self.assertEqual(len(nop_steps), 1)
        self.assertEqual(nop_steps[0].operands, [])

    def test_decode_trail_begin_metadata(self):
        """TRAIL_BEGIN should decode with timestamp metadata."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[42],
                      metadata={"agent": "pelagic", "trail_id": "test-001", "timestamp": 1234567890}),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 2, "status": 0}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        begin = decoded.steps[0]
        self.assertEqual(begin.metadata["timestamp"], 1234567890)

    def test_decode_trail_end_metadata(self):
        """TRAIL_END should decode with total_steps and status."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        end = decoded.steps[-1]
        self.assertEqual(end.metadata["total_steps"], 3)
        self.assertEqual(end.metadata["status"], 0)

    def test_decode_invalid_opcode_raises(self):
        """Decoding bytecode with invalid opcode raises ValueError."""
        # Construct invalid bytecode: random byte in the middle
        program = make_minimal_trail()
        encoder = TrailEncoder()
        good_bc = encoder.encode(program)
        # Inject an invalid opcode (0x00 is not a valid trail opcode)
        bad_bc = good_bc[:2] + bytes([0x00]) + good_bc[2:]
        decoder = TrailDecoder()
        with self.assertRaises(ValueError):
            decoder.decode(bad_bc)

    def test_decode_string_table_populated(self):
        """Decoder should populate string_table from hash table section."""
        encoder = TrailEncoder()
        encoder._register_string("test-path.py")
        encoder._register_string("hello world")
        program = make_minimal_trail()
        bytecode = encoder.encode(program)
        decoder = TrailDecoder()
        decoder.decode(bytecode)
        self.assertGreater(len(decoder.string_table), 0)

    def test_decode_all_opcodes(self):
        """All trail opcodes should survive round-trip."""
        program = make_sample_trail()
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)

        original_ops = [s.opcode for s in program.steps]
        decoded_ops = [s.opcode for s in decoded.steps]
        self.assertEqual(original_ops, decoded_ops)


# ═════════════════════════════════════════════════════════════════════════════
# 6. TrailPrinter: various output formats
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailPrinter(unittest.TestCase):
    """Test TrailPrinter formatting functionality."""

    def setUp(self):
        self.program = make_minimal_trail()
        self.printer = TrailPrinter()

    def test_text_format_contains_header(self):
        """Text format should contain TRAIL-FLUX header."""
        output = self.printer.print_program(self.program, fmt="text")
        self.assertIn("TRAIL-FLUX", output)

    def test_text_format_contains_trail_begin(self):
        """Text format should show TRAIL_BEGIN."""
        output = self.printer.print_program(self.program, fmt="text")
        self.assertIn("TRAIL_BEGIN", output)

    def test_text_format_contains_trail_end(self):
        """Text format should show TRAIL_END."""
        output = self.printer.print_program(self.program, fmt="text")
        self.assertIn("TRAIL_END", output)

    def test_hex_format_contains_offsets(self):
        """Hex format should contain hex addresses."""
        output = self.printer.print_program(self.program, fmt="hex")
        self.assertIn("0000:", output)

    def test_verbose_format_contains_opcode_hex(self):
        """Verbose format should show hex opcode values."""
        output = self.printer.print_program(self.program, fmt="verbose")
        self.assertIn("0xA0", output)

    def test_verbose_format_contains_operand_values(self):
        """Verbose format should show operand values."""
        output = self.printer.print_program(self.program, fmt="verbose")
        self.assertIn("operands:", output)

    def test_compact_format_no_header(self):
        """Compact format should not have fancy header."""
        output = self.printer.print_program(self.program, fmt="compact")
        self.assertNotIn("═", output)

    def test_compact_format_one_line_per_step(self):
        """Compact format should have one line per step."""
        output = self.printer.print_program(self.program, fmt="compact")
        lines = [l for l in output.strip().split("\n") if l]
        self.assertEqual(len(lines), len(self.program.steps))

    def test_invalid_format_raises(self):
        """Invalid format string should raise ValueError."""
        with self.assertRaises(ValueError):
            self.printer.print_program(self.program, fmt="nonexistent")

    def test_print_bytecode(self):
        """print_bytecode should decode and print."""
        encoder = TrailEncoder()
        bytecode = encoder.encode(self.program)
        output = self.printer.print_bytecode(bytecode, fmt="text")
        self.assertIn("TRAIL-FLUX", output)

    def test_verbose_with_string_table(self):
        """Verbose format should show string table when present."""
        printer = TrailPrinter(string_table={
            "a1b2c3d4e5f6a7b8": "trail_encoder.py",
        })
        output = printer.print_program(self.program, fmt="verbose")
        self.assertIn("STRING TABLE", output)
        self.assertIn("trail_encoder.py", output)

    def test_text_format_multiline(self):
        """Text output should be multiline."""
        output = self.printer.print_program(self.program, fmt="text")
        lines = output.strip().split("\n")
        self.assertGreater(len(lines), 3)


# ═════════════════════════════════════════════════════════════════════════════
# 7. TrailCompiler: structured input → TrailProgram
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailCompiler(unittest.TestCase):
    """Test TrailCompiler worklog compilation."""

    def setUp(self):
        self.compiler = TrailCompiler()

    def test_compile_minimal_worklog(self):
        """Minimal worklog should compile to valid program."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "TRAIL_END", "steps": 2, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertTrue(program.is_valid)

    def test_compile_file_read(self):
        """FILE_READ entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "FILE_READ", "path": "hello.py", "desc": "Read hello"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(len(program.steps), 3)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.FILE_READ)

    def test_compile_file_write(self):
        """FILE_WRITE entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "FILE_WRITE", "path": "out.py", "content": "data"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.FILE_WRITE)

    def test_compile_search_code(self):
        """SEARCH_CODE entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "SEARCH_CODE", "pattern": "TrustEngine"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.SEARCH_CODE)

    def test_compile_test_run(self):
        """TEST_RUN entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "TEST_RUN", "test_path": "tests/test.py", "count": 50},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.TEST_RUN)

    def test_compile_bottle_drop(self):
        """BOTTLE_DROP entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "BOTTLE_DROP", "target": "oracle1", "content": "report"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.BOTTLE_DROP)

    def test_compile_git_commit(self):
        """GIT_COMMIT entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "GIT_COMMIT", "repo_id": 1, "message": "initial commit"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.GIT_COMMIT)

    def test_compile_git_push(self):
        """GIT_PUSH entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "GIT_PUSH", "repo_id": 1},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.GIT_PUSH)

    def test_compile_level_up(self):
        """LEVEL_UP entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "LEVEL_UP", "level": 5},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.LEVEL_UP)

    def test_compile_spell_cast(self):
        """SPELL_CAST entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "SPELL_CAST", "spell_id": "fireball"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.SPELL_CAST)

    def test_compile_room_enter(self):
        """ROOM_ENTER entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "ROOM_ENTER", "room_id": "tavern"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.ROOM_ENTER)

    def test_compile_trust_update(self):
        """TRUST_UPDATE entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "TRUST_UPDATE", "target": "pelagic", "delta": 10},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.TRUST_UPDATE)

    def test_compile_cap_issue(self):
        """CAP_ISSUE entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "CAP_ISSUE", "action": "deploy", "holder": "pelagic"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.CAP_ISSUE)

    def test_compile_nop(self):
        """NOP entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "NOP"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        nop_steps = [s for s in program.steps if s.opcode == TrailOpcodes.NOP]
        self.assertEqual(len(nop_steps), 1)

    def test_compile_comment(self):
        """COMMENT entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "COMMENT", "comment": "analysis note"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.COMMENT)

    def test_compile_label(self):
        """LABEL entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "LABEL", "label": "loop_start"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.LABEL)

    def test_compile_branch(self):
        """BRANCH entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "BRANCH", "reg": 5},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.BRANCH)

    def test_compile_file_edit(self):
        """FILE_EDIT entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "FILE_EDIT", "path": "file.py", "old": "old_text", "new": "new_text"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.FILE_EDIT)

    def test_compile_bottle_read(self):
        """BOTTLE_READ entry should compile correctly."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "BOTTLE_READ", "source": "oracle1"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = self.compiler.compile(entries)
        self.assertEqual(program.steps[1].opcode, TrailOpcodes.BOTTLE_READ)

    def test_compile_unknown_opcode_raises(self):
        """Unknown opcode name should raise ValueError."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "NONEXISTENT_OPCODE"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        with self.assertRaises(ValueError):
            self.compiler.compile(entries)

    def test_compile_populates_string_table(self):
        """Compiler should populate string table with path/pattern strings."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "FILE_READ", "path": "specific_file.py"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        self.compiler.compile(entries)
        # String table should have entries
        self.assertGreater(len(self.compiler.string_table), 0)

    def test_compile_and_encode(self):
        """compile_and_encode should produce bytes."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "TRAIL_END", "steps": 2, "status": 0},
        ]
        bytecode = self.compiler.compile_and_encode(entries)
        self.assertIsInstance(bytecode, bytes)
        self.assertGreater(len(bytecode), 0)

    def test_full_worklog_compilation(self):
        """Full worklog from spec should compile and round-trip."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "pelagic", "trail_id": "session-007", "ts": 1744658400},
            {"op": "FILE_READ", "path": "tabula_rasa.py", "desc": "Read tabula_rasa source"},
            {"op": "SEARCH_CODE", "pattern": "TrustEngine", "desc": "Find TrustEngine references"},
            {"op": "FILE_WRITE", "path": "trail_encoder.py", "content": "...", "desc": "Create trail encoder"},
            {"op": "TEST_RUN", "test_path": "tests/test_trail_encoder.py", "count": 50, "desc": "Run trail encoder tests"},
            {"op": "BOTTLE_DROP", "target": "oracle1", "content": "trail-bridge-prototype", "desc": "Send report to Oracle1"},
            {"op": "TRAIL_END", "steps": 6, "status": 0, "desc": "Trail complete"},
        ]
        program = self.compiler.compile(entries)
        self.assertTrue(program.is_valid)
        self.assertEqual(len(program.steps), 7)

        # Should round-trip
        encoder = TrailEncoder(string_table=dict(self.compiler.string_table))
        bytecode = encoder.encode(program)
        decoder = TrailDecoder()
        decoded = decoder.decode(bytecode)
        self.assertEqual(len(decoded.steps), 7)


# ═════════════════════════════════════════════════════════════════════════════
# 8. TrailVerifier: integrity checks
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailVerifier(unittest.TestCase):
    """Test TrailVerifier integrity checking."""

    def test_verify_valid_trail(self):
        """Valid trail should pass verification."""
        program = make_minimal_trail()
        verifier = TrailVerifier()
        self.assertTrue(verifier.verify(program))
        self.assertEqual(len(verifier.errors), 0)

    def test_verify_invalid_structure(self):
        """Trail without proper framing should fail."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
        ])
        verifier = TrailVerifier()
        self.assertFalse(verifier.verify(program))
        self.assertGreater(len(verifier.errors), 0)

    def test_verify_missing_trail_end(self):
        """Trail without TRAIL_END should fail structure check."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1]),
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
        ])
        verifier = TrailVerifier()
        self.assertFalse(verifier.verify(program))

    def test_verify_missing_trail_begin(self):
        """Trail without TRAIL_BEGIN should fail structure check."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 2, "status": 0}),
        ])
        verifier = TrailVerifier()
        self.assertFalse(verifier.verify(program))

    def test_verify_roundtrip_preserves_opcodes(self):
        """Round-trip check should catch opcode mismatches."""
        # This tests that the verifier's roundtrip check works
        program = make_sample_trail()
        verifier = TrailVerifier()
        result = verifier.verify(program)
        self.assertTrue(result)

    def test_verify_report_pass(self):
        """Report for passing verification should indicate success."""
        # Use a trail with string table entries to avoid hash table warning
        compiler = TrailCompiler()
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "FILE_READ", "path": "test.py"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = compiler.compile(entries)
        verifier = TrailVerifier(string_table=dict(compiler.string_table))
        verifier.verify(program)
        report = verifier.report()
        self.assertIn("PASSED", report)

    def test_verify_report_fail(self):
        """Report for failing verification should show errors."""
        program = TrailProgram()
        verifier = TrailVerifier()
        verifier.verify(program)
        report = verifier.report()
        self.assertIn("error", report.lower())

    def test_verify_bytecode_valid(self):
        """verify_bytecode should accept valid bytecode."""
        program = make_minimal_trail()
        encoder = TrailEncoder()
        bytecode = encoder.encode(program)
        verifier = TrailVerifier()
        self.assertTrue(verifier.verify_bytecode(bytecode))

    def test_verify_bytecode_invalid(self):
        """verify_bytecode should reject corrupt bytecode."""
        verifier = TrailVerifier()
        self.assertFalse(verifier.verify_bytecode(bytes([0x00, 0x01, 0x02])))

    def test_verify_fingerprint_deterministic(self):
        """Verifier should check that fingerprinting is deterministic."""
        program = make_sample_trail()
        verifier = TrailVerifier()
        result = verifier.verify(program)
        self.assertTrue(result)
        # No errors about non-deterministic fingerprint
        fp_errors = [e for e in verifier.errors if "Fingerprint" in e]
        self.assertEqual(len(fp_errors), 0)


# ═════════════════════════════════════════════════════════════════════════════
# 9. Hash Table: string storage and retrieval
# ═════════════════════════════════════════════════════════════════════════════

class TestHashTable(unittest.TestCase):
    """Test hash table encoding, decoding, and string recovery."""

    def test_str_to_hash_consistent(self):
        """Same string should always produce same hash."""
        h1 = str_to_hash("hello.py")
        h2 = str_to_hash("hello.py")
        self.assertEqual(h1, h2)

    def test_str_to_hash_different_strings(self):
        """Different strings should produce different hashes."""
        h1 = str_to_hash("file_a.py")
        h2 = str_to_hash("file_b.py")
        self.assertNotEqual(h1, h2)

    def test_str_to_hash_length(self):
        """Hash should be exactly 8 hex chars (4 bytes)."""
        h = str_to_hash("anything")
        self.assertEqual(len(h), 8)

    def test_str_to_hash_hex_format(self):
        """Hash should be valid hex."""
        h = str_to_hash("test")
        int(h, 16)  # should not raise

    def test_str_hash_to_u16_pair_roundtrip(self):
        """u16 pair should reconstruct the 8-char hash hex."""
        s = "my_test_file.py"
        hi, lo = str_hash_to_u16_pair(s)
        reconstructed = u16_pair_to_hex(hi, lo)
        # Should match the full 8-char hash
        self.assertEqual(reconstructed, str_to_hash(s))

    def test_u16_pair_to_hex_format(self):
        """u16_pair_to_hex should produce 8-char hex string."""
        result = u16_pair_to_hex(0x1234, 0x5678)
        self.assertEqual(result, "12345678")
        self.assertEqual(len(result), 8)

    def test_hash_table_in_bytecode(self):
        """Hash table section should be present in encoded bytecode."""
        encoder = TrailEncoder()
        encoder._register_string("hello.py")
        encoder._register_string("world.py")
        program = make_minimal_trail()
        bytecode = encoder.encode(program)
        # Hash table marker 0xB0 should be present
        self.assertIn(int(TrailOpcodes.HASHTABLE), bytecode)

    def test_hash_table_decode_recovers_strings(self):
        """Decoding should recover original strings from hash table."""
        original = "trail_encoder.py"
        encoder = TrailEncoder()
        encoder._register_string(original)
        program = make_minimal_trail()
        bytecode = encoder.encode(program)

        decoder = TrailDecoder()
        decoder.decode(bytecode)
        # Find the string in the decoded table
        h = str_to_hash(original)
        self.assertEqual(decoder.string_table.get(h), original)

    def test_hash_table_multiple_strings(self):
        """Multiple strings should all be recoverable."""
        strings = ["file_a.py", "file_b.py", "pattern_x", "oracle1", "tavern"]
        encoder = TrailEncoder()
        for s in strings:
            encoder._register_string(s)
        program = make_minimal_trail()
        bytecode = encoder.encode(program)

        decoder = TrailDecoder()
        decoder.decode(bytecode)
        for s in strings:
            h = str_to_hash(s)
            self.assertEqual(decoder.string_table.get(h), s,
                           f"Failed to recover: {s}")

    def test_hash_table_empty(self):
        """Empty hash table should still produce valid bytecode."""
        encoder = TrailEncoder()  # no strings registered
        program = make_minimal_trail()
        bytecode = encoder.encode(program)
        self.assertGreater(len(bytecode), 0)

        decoder = TrailDecoder()
        decoded = decoder.decode(bytecode)
        self.assertTrue(decoded.is_valid)

    def test_hash_table_unicode_strings(self):
        """Unicode strings should be stored and recovered correctly."""
        original = "你好世界_🎉.py"
        encoder = TrailEncoder()
        encoder._register_string(original)
        program = make_minimal_trail()
        bytecode = encoder.encode(program)

        decoder = TrailDecoder()
        decoder.decode(bytecode)
        h = str_to_hash(original)
        self.assertEqual(decoder.string_table.get(h), original)


# ═════════════════════════════════════════════════════════════════════════════
# 10. Composability: concatenating trails
# ═════════════════════════════════════════════════════════════════════════════

class TestComposability(unittest.TestCase):
    """Test trail concatenation and composability."""

    def test_concatenate_preserves_begin(self):
        """Merged trail should keep first trail's TRAIL_BEGIN."""
        a = make_minimal_trail("agent-a", "trail-a")
        b = make_minimal_trail("agent-b", "trail-b")
        merged = a.concatenate(b)
        self.assertEqual(merged.steps[0].opcode, TrailOpcodes.TRAIL_BEGIN)

    def test_concatenate_preserves_end(self):
        """Merged trail should keep second trail's TRAIL_END."""
        a = make_minimal_trail("agent-a", "trail-a")
        b = make_minimal_trail("agent-b", "trail-b")
        merged = a.concatenate(b)
        self.assertEqual(merged.steps[-1].opcode, TrailOpcodes.TRAIL_END)

    def test_concatenate_step_count(self):
        """Merged step count = len(A) + len(B) - 2."""
        a = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "a", "trail_id": "t1", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.FILE_WRITE, operands=[0, 0, 0, 0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 4, "status": 0}),
        ])
        b = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[2],
                      metadata={"agent": "b", "trail_id": "t2", "timestamp": 2}),
            TrailStep(opcode=TrailOpcodes.SEARCH_CODE, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        merged = a.concatenate(b)
        self.assertEqual(len(merged.steps), 4 + 3 - 2)

    def test_three_way_concatenation(self):
        """Three trails can be concatenated sequentially."""
        a = make_minimal_trail("a", "1")
        b = make_minimal_trail("b", "2")
        c = make_minimal_trail("c", "3")
        merged = a.concatenate(b).concatenate(c)
        self.assertTrue(merged.is_valid)

    def test_concatenate_then_encode(self):
        """Concatenated trail should encode to bytecode."""
        a = make_minimal_trail("a", "1")
        b = make_minimal_trail("b", "2")
        merged = a.concatenate(b)
        encoder = TrailEncoder()
        bytecode = encoder.encode(merged)
        self.assertIsInstance(bytecode, bytes)

    def test_concatenate_different_fingerprints(self):
        """Concatenated trail should have different fingerprint from parts."""
        a = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "a", "trail_id": "1", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.FILE_READ, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        b = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[2],
                      metadata={"agent": "b", "trail_id": "2", "timestamp": 2}),
            TrailStep(opcode=TrailOpcodes.SEARCH_CODE, operands=[0, 0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        merged = a.concatenate(b)
        fp_a = a.fingerprint()
        fp_b = b.fingerprint()
        fp_m = merged.fingerprint()
        self.assertNotEqual(fp_m, fp_a)
        self.assertNotEqual(fp_m, fp_b)


# ═════════════════════════════════════════════════════════════════════════════
# 11. Trail Fingerprinting
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailFingerprinting(unittest.TestCase):
    """Test trail fingerprint generation and properties."""

    def test_fingerprint_is_sha256(self):
        """Fingerprint should be a 64-char hex string (SHA-256)."""
        program = make_minimal_trail()
        fp = program.fingerprint()
        self.assertEqual(len(fp), 64)
        int(fp, 16)  # valid hex

    def test_fingerprint_deterministic(self):
        """Same program should always produce same fingerprint."""
        program = make_minimal_trail()
        fps = {program.fingerprint() for _ in range(10)}
        self.assertEqual(len(fps), 1)

    def test_fingerprint_changes_with_operands(self):
        """Different operands should produce different fingerprint."""
        p1 = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[1]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        p2 = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[99]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        self.assertNotEqual(p1.fingerprint(), p2.fingerprint())

    def test_fingerprint_changes_with_step_count(self):
        """Different number of steps should produce different fingerprint."""
        p1 = make_minimal_trail("a")
        p2 = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "a", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.NOP),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        self.assertNotEqual(p1.fingerprint(), p2.fingerprint())


# ═════════════════════════════════════════════════════════════════════════════
# 12. Edge Cases
# ═════════════════════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_empty_program_encode_raises(self):
        """Empty program should raise on encode."""
        program = TrailProgram()
        encoder = TrailEncoder()
        with self.assertRaises(ValueError):
            encoder.encode(program)

    def test_single_step_invalid(self):
        """Single-step program is not valid."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1]),
        ])
        self.assertFalse(program.is_valid)

    def test_only_nop_between_begin_end(self):
        """Trail with only NOP between begin/end is valid."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.NOP),
            TrailStep(opcode=TrailOpcodes.NOP),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 4, "status": 0}),
        ])
        self.assertTrue(program.is_valid)

    def test_very_long_trail(self):
        """Trail with 100 steps should encode/decode correctly."""
        steps = [
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "long-trail", "timestamp": 1}),
        ]
        for i in range(98):
            steps.append(TrailStep(
                opcode=TrailOpcodes.FILE_READ,
                operands=[i & 0xFFFF, (i * 7) & 0xFFFF],
            ))
        steps.append(TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                               metadata={"total_steps": 100, "status": 0}))

        program = TrailProgram(steps=steps)
        self.assertTrue(program.is_valid)

        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        self.assertEqual(len(decoded.steps), 100)

    def test_unicode_path_in_compiler(self):
        """Compiler should handle unicode paths."""
        compiler = TrailCompiler()
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "FILE_READ", "path": "文件/报告_🎉.py"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = compiler.compile(entries)
        self.assertTrue(program.is_valid)
        # Should encode and decode
        encoder = TrailEncoder(string_table=dict(compiler.string_table))
        bytecode = encoder.encode(program)
        decoder = TrailDecoder()
        decoded = decoder.decode(bytecode)
        # Find the unicode string in the hash table
        recovered = any("文件" in v for v in decoder.string_table.values())
        self.assertTrue(recovered, "Unicode path not recovered from hash table")

    def test_unicode_pattern_in_compiler(self):
        """Compiler should handle unicode search patterns."""
        compiler = TrailCompiler()
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "SEARCH_CODE", "pattern": "検索パターン"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        program = compiler.compile(entries)
        encoder = TrailEncoder(string_table=dict(compiler.string_table))
        bytecode = encoder.encode(program)
        decoder = TrailDecoder()
        decoded = decoder.decode(bytecode)
        self.assertTrue(any("検索" in v for v in decoder.string_table.values()))

    def test_empty_string_hash(self):
        """Empty string should still produce a valid hash."""
        h = str_to_hash("")
        self.assertEqual(len(h), 8)

    def test_max_u16_operand(self):
        """Max u16 operand (65535) should round-trip."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[65535]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        for s in decoded.steps:
            if s.opcode == TrailOpcodes.LEVEL_UP:
                self.assertEqual(s.operands, [65535])
                return
        self.fail("LEVEL_UP not found")

    def test_zero_operand(self):
        """Zero operand should round-trip correctly."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.LEVEL_UP, operands=[0]),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[0],
                      metadata={"total_steps": 3, "status": 0}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        for s in decoded.steps:
            if s.opcode == TrailOpcodes.LEVEL_UP:
                self.assertEqual(s.operands, [0])
                return
        self.fail("LEVEL_UP not found")

    def test_hex_dump_format(self):
        """hex_dump should produce proper format."""
        data = bytes([0xA0, 0x2B, 0x90, 0x00, 0xFF])
        output = hex_dump(data)
        self.assertIn("0000:", output)
        self.assertIn("A0", output)

    def test_hex_dump_empty(self):
        """hex_dump of empty bytes should be empty string."""
        self.assertEqual(hex_dump(b""), "")

    def test_compiler_empty_entries(self):
        """Compiler should handle minimal entries (just begin+end)."""
        compiler = TrailCompiler()
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
            {"op": "TRAIL_END", "steps": 2, "status": 0},
        ]
        program = compiler.compile(entries)
        self.assertTrue(program.is_valid)
        self.assertEqual(len(program.steps), 2)

    def test_trail_end_error_status(self):
        """TRAIL_END with error status should round-trip."""
        program = TrailProgram(steps=[
            TrailStep(opcode=TrailOpcodes.TRAIL_BEGIN, operands=[1],
                      metadata={"agent": "x", "trail_id": "y", "timestamp": 1}),
            TrailStep(opcode=TrailOpcodes.TRAIL_END, operands=[1],
                      metadata={"total_steps": 2, "status": 1}),
        ])
        encoder = TrailEncoder()
        decoder = TrailDecoder()
        bytecode = encoder.encode(program)
        decoded = decoder.decode(bytecode)
        end = decoded.steps[-1]
        self.assertEqual(end.metadata["status"], 1)

    def test_duplicate_string_registration(self):
        """Registering same string multiple times should not cause issues."""
        encoder = TrailEncoder()
        for _ in range(5):
            encoder._register_string("same-file.py")
        self.assertEqual(len(encoder.string_table), 1)

    def test_long_string_in_hash_table(self):
        """Long strings (up to 255 bytes) should be stored correctly in hash table."""
        long_str = "a" * 200
        encoder = TrailEncoder()
        encoder._register_string(long_str)
        program = make_minimal_trail()
        bytecode = encoder.encode(program)
        decoder = TrailDecoder()
        decoder.decode(bytecode)
        h = str_to_hash(long_str)
        self.assertEqual(decoder.string_table.get(h), long_str)


# ═════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestIntegration(unittest.TestCase):
    """End-to-end integration tests across all components."""

    def test_full_pipeline(self):
        """Full compile→encode→decode→print→verify pipeline."""
        worklog = [
            {"op": "TRAIL_BEGIN", "agent": "pelagic", "trail_id": "integration-test", "ts": 1744658400},
            {"op": "FILE_READ", "path": "flux_vm.py", "desc": "Read FLUX VM"},
            {"op": "FILE_WRITE", "path": "trail_encoder.py", "content": "bytecode-bridge", "desc": "Create bridge"},
            {"op": "TEST_RUN", "test_path": "tests/test_trail.py", "count": 80},
            {"op": "BOTTLE_DROP", "target": "oracle1", "content": "integration-complete"},
            {"op": "TRAIL_END", "steps": 6, "status": 0},
        ]

        # Compile
        compiler = TrailCompiler()
        program = compiler.compile(worklog)
        self.assertTrue(program.is_valid)

        # Encode
        encoder = TrailEncoder(string_table=dict(compiler.string_table))
        bytecode = encoder.encode(program)
        self.assertGreater(len(bytecode), 0)

        # Decode
        decoder = TrailDecoder()
        decoded = decoder.decode(bytecode)
        self.assertEqual(len(decoded.steps), len(program.steps))

        # Print
        printer = TrailPrinter(string_table=decoder.string_table)
        text_output = printer.print_program(decoded, fmt="text")
        self.assertIn("TRAIL_BEGIN", text_output)
        self.assertIn("TRAIL_END", text_output)

        # Verify
        verifier = TrailVerifier()
        self.assertTrue(verifier.verify(program))

        # Fingerprint
        fp = program.fingerprint()
        self.assertEqual(len(fp), 64)

    def test_compiler_encoder_decoder_roundtrip(self):
        """Compiler output should survive encoder→decoder round-trip."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "roundtrip", "ts": 12345},
            {"op": "FILE_READ", "path": "a.py"},
            {"op": "FILE_WRITE", "path": "b.py", "content": "data"},
            {"op": "FILE_EDIT", "path": "c.py", "old": "old", "new": "new"},
            {"op": "SEARCH_CODE", "pattern": "Foo"},
            {"op": "TEST_RUN", "test_path": "test.py", "count": 10},
            {"op": "GIT_COMMIT", "repo_id": 1, "message": "commit"},
            {"op": "GIT_PUSH", "repo_id": 1},
            {"op": "BOTTLE_DROP", "target": "agent", "content": "msg"},
            {"op": "BOTTLE_READ", "source": "agent"},
            {"op": "LEVEL_UP", "level": 3},
            {"op": "SPELL_CAST", "spell_id": "heal"},
            {"op": "ROOM_ENTER", "room_id": "tavern"},
            {"op": "TRUST_UPDATE", "target": "agent", "delta": 5},
            {"op": "CAP_ISSUE", "action": "deploy", "holder": "agent"},
            {"op": "BRANCH", "reg": 0},
            {"op": "NOP"},
            {"op": "COMMENT", "comment": "note"},
            {"op": "LABEL", "label": "loop"},
            {"op": "TRAIL_END", "steps": 21, "status": 0},
        ]
        compiler = TrailCompiler()
        program = compiler.compile(entries)
        encoder = TrailEncoder(string_table=dict(compiler.string_table))
        bytecode = encoder.encode(program)
        decoder = TrailDecoder()
        decoded = decoder.decode(bytecode)

        # All opcodes should match
        orig_ops = [s.opcode for s in program.steps]
        decoded_ops = [s.opcode for s in decoded.steps]
        self.assertEqual(orig_ops, decoded_ops)

    def test_verifier_after_decode(self):
        """Decoded program should also pass verification."""
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "verify-test", "ts": 1000},
            {"op": "FILE_READ", "path": "test.py"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        compiler = TrailCompiler()
        program = compiler.compile(entries)
        encoder = TrailEncoder(string_table=dict(compiler.string_table))
        bytecode = encoder.encode(program)
        decoder = TrailDecoder()
        decoded = decoder.decode(bytecode)

        verifier = TrailVerifier()
        self.assertTrue(verifier.verify(decoded))


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
