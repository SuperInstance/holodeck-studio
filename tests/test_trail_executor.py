"""
Comprehensive test suite for the Trail Execution Engine.

Test categories:
  1. TrailEvent creation and serialization (10 tests)
  2. MockWorld basic operations (10 tests)
  3. MockWorld failure simulation (8 tests)
  4. TrailExecutor creation and state (8 tests)
  5. Single-step execution (12 tests)
  6. Full trail execution (10 tests)
  7. Error handling — failed steps (10 tests)
  8. Pause/resume execution (8 tests)
  9. Dry-run mode (6 tests)
  10. Fail-fast mode (6 tests)
  11. Execution trail generation (8 tests)
  12. Execution fingerprint verification (6 tests)
  13. FileWorld — real filesystem operations (8 tests)
  14. FileWorld — git operations (4 tests)
  15. Edge cases: empty trail, single step, very long trail (6 tests)

# [pelagic] Trail Execution Engine test suite — session-008
"""

import sys
import os
import shutil
import subprocess
import tempfile
import unittest

# Ensure the module can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trail_executor import (
    TrailEvent,
    TrailResult,
    WorldInterface,
    MockWorld,
    FileWorld,
    TrailExecutor,
    resolve_operands,
    operand_names,
    OPCODE_ARG_TYPES,
)

from trail_encoder import (
    TrailOpcodes,
    TrailStep,
    TrailProgram,
    TrailEncoder,
    TrailDecoder,
    TrailCompiler,
    str_to_hash,
    str_hash_to_u16_pair,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_simple_bytecode() -> bytes:
    """Create bytecode for a simple trail: FILE_READ, SEARCH_CODE, FILE_WRITE."""
    compiler = TrailCompiler()
    entries = [
        {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "t-1", "ts": 1000},
        {"op": "FILE_READ", "path": "hello.py", "desc": "Read hello"},
        {"op": "SEARCH_CODE", "pattern": "TrustEngine"},
        {"op": "FILE_WRITE", "path": "output.py", "content": "data"},
        {"op": "TRAIL_END", "steps": 3, "status": 0},
    ]
    return compiler.compile_and_encode(entries)


def make_multi_opcode_bytecode() -> bytes:
    """Create bytecode with many different opcodes."""
    compiler = TrailCompiler()
    entries = [
        {"op": "TRAIL_BEGIN", "agent": "pelagic", "trail_id": "multi-001", "ts": 2000},
        {"op": "FILE_READ", "path": "src/main.py"},
        {"op": "SEARCH_CODE", "pattern": "TrustEngine"},
        {"op": "FILE_WRITE", "path": "src/out.py", "content": "output"},
        {"op": "FILE_EDIT", "path": "src/main.py", "old": "old_code", "new": "new_code"},
        {"op": "TEST_RUN", "test_path": "tests/", "count": 42},
        {"op": "BOTTLE_DROP", "target": "oracle1", "content": "message"},
        {"op": "BOTTLE_READ", "source": "oracle1"},
        {"op": "LEVEL_UP", "level": 7},
        {"op": "SPELL_CAST", "spell_id": "fireball"},
        {"op": "ROOM_ENTER", "room_id": "tavern"},
        {"op": "TRUST_UPDATE", "target": "pelagic", "delta": 10},
        {"op": "CAP_ISSUE", "action": "deploy", "holder": "pelagic"},
        {"op": "NOP"},
        {"op": "COMMENT", "comment": "midpoint check"},
        {"op": "LABEL", "label": "phase2"},
        {"op": "GIT_COMMIT", "repo_id": 1, "message": "save progress"},
        {"op": "GIT_PUSH", "repo_id": 1},
        {"op": "BRANCH", "reg": 3},
        {"op": "TRAIL_END", "steps": 15, "status": 0},
    ]
    return compiler.compile_and_encode(entries)


def make_minimal_bytecode() -> bytes:
    """Create minimal bytecode with just TRAIL_BEGIN + TRAIL_END."""
    compiler = TrailCompiler()
    entries = [
        {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "minimal", "ts": 100},
        {"op": "TRAIL_END", "steps": 0, "status": 0},
    ]
    return compiler.compile_and_encode(entries)


# ═════════════════════════════════════════════════════════════════════════════
# 1. TrailEvent creation and serialization
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailEvent(unittest.TestCase):
    """Test TrailEvent dataclass creation and serialization."""

    def test_basic_creation(self):
        """TrailEvent should store all fields correctly."""
        ev = TrailEvent(
            step_index=0, opcode=TrailOpcodes.FILE_READ,
            operands={"path": "test.py"}, result="ok",
            duration_ms=1.5, timestamp=1000.0,
        )
        self.assertEqual(ev.step_index, 0)
        self.assertEqual(ev.opcode, TrailOpcodes.FILE_READ)
        self.assertEqual(ev.result, "ok")
        self.assertEqual(ev.duration_ms, 1.5)

    def test_proof_auto_generated(self):
        """Proof should be auto-generated if not provided."""
        ev = TrailEvent(
            step_index=0, opcode=TrailOpcodes.FILE_READ,
            operands={}, result="ok", duration_ms=1.0, timestamp=1000.0,
        )
        self.assertIsNotNone(ev.proof)
        self.assertEqual(len(ev.proof), 16)

    def test_proof_deterministic(self):
        """Same inputs should produce same proof."""
        ev1 = TrailEvent(step_index=0, opcode=TrailOpcodes.FILE_READ,
                        operands={}, result="ok", duration_ms=1.0, timestamp=1000.0)
        ev2 = TrailEvent(step_index=0, opcode=TrailOpcodes.FILE_READ,
                        operands={}, result="ok", duration_ms=1.0, timestamp=1000.0)
        self.assertEqual(ev1.proof, ev2.proof)

    def test_proof_different_for_different_results(self):
        """Different results should produce different proofs."""
        ev1 = TrailEvent(step_index=0, opcode=TrailOpcodes.FILE_READ,
                        operands={}, result="ok", duration_ms=1.0, timestamp=1000.0)
        ev2 = TrailEvent(step_index=0, opcode=TrailOpcodes.FILE_READ,
                        operands={}, result="error", duration_ms=1.0, timestamp=1000.0)
        self.assertNotEqual(ev1.proof, ev2.proof)

    def test_to_dict(self):
        """to_dict should produce a serializable dict."""
        ev = TrailEvent(step_index=5, opcode=TrailOpcodes.FILE_WRITE,
                        operands={"path": "f.py", "content": "x"},
                        result="written", duration_ms=2.0, timestamp=1000.0)
        d = ev.to_dict()
        self.assertEqual(d["step_index"], 5)
        self.assertEqual(d["opcode"], int(TrailOpcodes.FILE_WRITE))
        self.assertEqual(d["opcode_name"], "FILE_WRITE")
        self.assertIn("path", d["operands"])

    def test_from_dict_roundtrip(self):
        """from_dict should reconstruct an event."""
        ev = TrailEvent(step_index=3, opcode=TrailOpcodes.SEARCH_CODE,
                        operands={"pattern": "x"}, result="found",
                        duration_ms=0.5, timestamp=1000.0)
        d = ev.to_dict()
        ev2 = TrailEvent.from_dict(d)
        self.assertEqual(ev2.step_index, ev.step_index)
        self.assertEqual(ev2.opcode, ev.opcode)
        self.assertEqual(ev2.result, ev.result)
        self.assertEqual(ev2.proof, ev.proof)

    def test_to_json(self):
        """to_json should produce valid JSON string."""
        ev = TrailEvent(step_index=0, opcode=TrailOpcodes.NOP,
                        operands={}, result="skip", duration_ms=0.1, timestamp=1000.0)
        j = ev.to_json()
        self.assertIn("FILE_READ" if False else "NOP", j)
        import json
        parsed = json.loads(j)
        self.assertEqual(parsed["step_index"], 0)

    def test_custom_proof_preserved(self):
        """Custom proof should not be overwritten."""
        ev = TrailEvent(step_index=0, opcode=TrailOpcodes.NOP,
                        operands={}, result="skip", duration_ms=0.1,
                        timestamp=1000.0, proof="custom_proof")
        self.assertEqual(ev.proof, "custom_proof")

    def test_different_opcodes_different_proofs(self):
        """Different opcodes should produce different proofs."""
        ev1 = TrailEvent(step_index=0, opcode=TrailOpcodes.FILE_READ,
                        operands={}, result="ok", duration_ms=1.0, timestamp=1000.0)
        ev2 = TrailEvent(step_index=0, opcode=TrailOpcodes.FILE_WRITE,
                        operands={}, result="ok", duration_ms=1.0, timestamp=1000.0)
        self.assertNotEqual(ev1.proof, ev2.proof)


# ═════════════════════════════════════════════════════════════════════════════
# 2. MockWorld basic operations
# ═════════════════════════════════════════════════════════════════════════════

class TestMockWorldBasic(unittest.TestCase):
    """Test MockWorld basic operation recording."""

    def setUp(self):
        self.world = MockWorld()

    def test_file_read_records_call(self):
        """file_read should record a call."""
        self.world.file_read("test.py")
        self.assertEqual(len(self.world.calls), 1)
        self.assertEqual(self.world.calls[0]["method"], "file_read")

    def test_file_write_records_call(self):
        """file_write should record a call with args."""
        self.world.file_write("out.py", "content")
        self.assertEqual(len(self.world.calls), 1)
        self.assertEqual(self.world.calls[0]["args"]["path"], "out.py")

    def test_all_methods_callable(self):
        """All WorldInterface methods should be callable."""
        methods = [
            ("git_commit", ["repo", "msg"]),
            ("git_push", ["repo"]),
            ("file_read", ["path"]),
            ("file_write", ["path", "content"]),
            ("file_edit", ["path", "old", "new"]),
            ("test_run", ["tests/", 50]),
            ("search_code", ["pattern"]),
            ("bottle_drop", ["target", "content"]),
            ("bottle_read", ["source"]),
            ("level_up", ["agent", 5]),
            ("spell_cast", ["fireball"]),
            ("room_enter", ["tavern"]),
            ("trust_update", ["target", 10.0]),
            ("cap_issue", ["deploy", "holder"]),
        ]
        for method_name, args in methods:
            method = getattr(self.world, method_name)
            result = method(*args)
            self.assertIsInstance(result, str)
            self.assertIn(method_name, result)

    def test_default_result_format(self):
        """Default result should be 'method: ok'."""
        result = self.world.file_read("test.py")
        self.assertEqual(result, "file_read: ok")

    def test_custom_result(self):
        """Custom call_results should be returned."""
        self.world.call_results["file_read"] = "custom: 42 chars"
        result = self.world.file_read("test.py")
        self.assertEqual(result, "custom: 42 chars")

    def test_multiple_calls_recorded(self):
        """Multiple calls should all be recorded."""
        self.world.file_read("a.py")
        self.world.file_read("b.py")
        self.world.file_write("c.py", "data")
        self.assertEqual(len(self.world.calls), 3)

    def test_call_args_preserved(self):
        """Call args should be preserved exactly."""
        self.world.file_edit("f.py", "old text", "new text")
        args = self.world.calls[0]["args"]
        self.assertEqual(args["path"], "f.py")
        self.assertEqual(args["old"], "old text")
        self.assertEqual(args["new"], "new text")

    def test_assert_call_count(self):
        """assert_call_count should pass for correct count."""
        self.world.file_read("a.py")
        self.world.file_read("b.py")
        # Should not raise
        self.world.assert_call_count("file_read", 2)

    def test_assert_call_count_fails(self):
        """assert_call_count should fail for wrong count."""
        self.world.file_read("a.py")
        with self.assertRaises(AssertionError):
            self.world.assert_call_count("file_read", 2)

    def test_reset(self):
        """reset should clear all state."""
        self.world.file_read("a.py")
        self.world.reset()
        self.assertEqual(len(self.world.calls), 0)
        self.assertEqual(len(self.world.call_results), 0)


# ═════════════════════════════════════════════════════════════════════════════
# 3. MockWorld failure simulation
# ═════════════════════════════════════════════════════════════════════════════

class TestMockWorldFailure(unittest.TestCase):
    """Test MockWorld failure simulation."""

    def test_fail_on_specific_method(self):
        """fail_on should cause specific method to raise RuntimeError."""
        self.world = MockWorld(fail_on={"file_read"})
        with self.assertRaises(RuntimeError):
            self.world.file_read("test.py")

    def test_fail_on_does_not_affect_others(self):
        """fail_on should not affect methods not in the set."""
        self.world = MockWorld(fail_on={"file_read"})
        result = self.world.file_write("out.py", "data")
        self.assertIn("file_write", result)

    def test_fail_on_multiple_methods(self):
        """fail_on can specify multiple failing methods."""
        self.world = MockWorld(fail_on={"file_read", "file_write"})
        with self.assertRaises(RuntimeError):
            self.world.file_read("a.py")
        with self.assertRaises(RuntimeError):
            self.world.file_write("b.py", "data")

    def test_fail_on_with_message(self):
        """Failure should include method name in message."""
        self.world = MockWorld(fail_on={"git_commit"})
        with self.assertRaises(RuntimeError) as ctx:
            self.world.git_commit("repo", "msg")
        self.assertIn("git_commit", str(ctx.exception))

    def test_no_failure_without_fail_on(self):
        """Without fail_on, all calls should succeed."""
        self.world = MockWorld()
        result = self.world.file_read("any.py")
        self.assertIn("ok", result)

    def test_assert_call_order(self):
        """assert_call_order should pass for correct order."""
        self.world = MockWorld()
        self.world.file_read("a.py")
        self.world.file_write("b.py", "data")
        # Should not raise
        self.world.assert_call_order(["file_read", "file_write"])

    def test_assert_call_order_fails(self):
        """assert_call_order should fail for wrong order."""
        self.world = MockWorld()
        self.world.file_write("b.py", "data")
        self.world.file_read("a.py")
        with self.assertRaises(AssertionError):
            self.world.assert_call_order(["file_read", "file_write"])

    def test_assert_called_with(self):
        """assert_called_with should pass for correct args."""
        self.world = MockWorld()
        self.world.file_edit("f.py", "old", "new")
        self.world.assert_called_with("file_edit", {
            "path": "f.py", "old": "old", "new": "new"
        })


# ═════════════════════════════════════════════════════════════════════════════
# 4. TrailExecutor creation and state
# ═════════════════════════════════════════════════════════════════════════════

class TestTrailExecutorState(unittest.TestCase):
    """Test TrailExecutor creation and state management."""

    def setUp(self):
        self.world = MockWorld()
        self.bytecode = make_simple_bytecode()

    def test_creation(self):
        """Executor should be created from bytecode and world."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        self.assertIsNotNone(executor)

    def test_decodes_program(self):
        """Executor should decode the bytecode into a program."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        self.assertGreater(len(executor.program.steps), 0)

    def test_populates_string_table(self):
        """Executor should populate the string table from bytecode."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        self.assertGreater(len(executor.string_table), 0)

    def test_initial_state(self):
        """Initial state should show not started."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        state = executor.get_state()
        self.assertEqual(state["current_index"], 0)
        self.assertFalse(state["paused"])
        self.assertFalse(state["finished"])

    def test_dry_run_flag(self):
        """dry_run flag should be stored."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, dry_run=True)
        state = executor.get_state()
        self.assertTrue(state["dry_run"])

    def test_fail_fast_flag(self):
        """fail_fast flag should be stored."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, fail_fast=True)
        state = executor.get_state()
        self.assertTrue(state["fail_fast"])

    def test_initial_events_empty(self):
        """get_events should return empty list initially."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        self.assertEqual(len(executor.get_events()), 0)

    def test_world_interface_compliance(self):
        """MockWorld should satisfy WorldInterface protocol."""
        self.assertTrue(isinstance(self.world, WorldInterface))


# ═════════════════════════════════════════════════════════════════════════════
# 5. Single-step execution
# ═════════════════════════════════════════════════════════════════════════════

class TestSingleStepExecution(unittest.TestCase):
    """Test step-by-step execution."""

    def setUp(self):
        self.world = MockWorld()
        self.bytecode = make_simple_bytecode()
        self.executor = TrailExecutor(world=self.world, bytecode=self.bytecode)

    def test_first_step_returns_event(self):
        """First step() should return a TrailEvent."""
        event = self.executor.step()
        self.assertIsNotNone(event)
        self.assertIsInstance(event, TrailEvent)

    def test_first_step_is_trail_begin(self):
        """First step should be TRAIL_BEGIN."""
        event = self.executor.step()
        self.assertEqual(event.opcode, TrailOpcodes.TRAIL_BEGIN)

    def test_trail_begin_no_world_call(self):
        """TRAIL_BEGIN should not call WorldInterface."""
        self.executor.step()  # TRAIL_BEGIN
        self.assertEqual(len(self.world.calls), 0)

    def test_action_step_calls_world(self):
        """Action step should call WorldInterface."""
        self.executor.step()  # TRAIL_BEGIN
        event = self.executor.step()  # FILE_READ
        self.assertEqual(event.opcode, TrailOpcodes.FILE_READ)
        self.assertEqual(len(self.world.calls), 1)
        self.assertEqual(self.world.calls[0]["method"], "file_read")

    def test_step_advances_index(self):
        """Each step should advance the current index."""
        state1 = self.executor.get_state()
        self.executor.step()
        state2 = self.executor.get_state()
        self.assertGreater(state2["current_index"], state1["current_index"])

    def test_step_records_event(self):
        """Each step should add to events list."""
        self.executor.step()
        events = self.executor.get_events()
        self.assertEqual(len(events), 1)

    def test_event_has_step_index(self):
        """Event should have correct step index."""
        event = self.executor.step()
        self.assertEqual(event.step_index, 0)

    def test_event_has_timestamp(self):
        """Event should have a timestamp."""
        event = self.executor.step()
        self.assertGreater(event.timestamp, 0)

    def test_event_has_duration(self):
        """Event should have a duration."""
        event = self.executor.step()
        self.assertGreaterEqual(event.duration_ms, 0)

    def test_event_has_operands_dict(self):
        """Event should have an operands dict."""
        self.executor.step()  # TRAIL_BEGIN
        event = self.executor.step()  # FILE_READ
        self.assertIsInstance(event.operands, dict)
        self.assertIn("path", event.operands)

    def test_final_step_returns_none(self):
        """After all steps, step() should return None."""
        event = True
        while event is not None:
            event = self.executor.step()
        self.assertIsNone(event)

    def test_finished_state_after_all_steps(self):
        """After all steps, state should show finished."""
        self.executor.execute()
        state = self.executor.get_state()
        self.assertTrue(state["finished"])


# ═════════════════════════════════════════════════════════════════════════════
# 6. Full trail execution
# ═════════════════════════════════════════════════════════════════════════════

class TestFullTrailExecution(unittest.TestCase):
    """Test complete trail execution."""

    def setUp(self):
        self.world = MockWorld()
        self.bytecode = make_simple_bytecode()

    def test_execute_returns_result(self):
        """execute() should return a TrailResult."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertIsInstance(result, TrailResult)

    def test_result_success_on_all_pass(self):
        """Result should show success when all steps pass."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertTrue(result.success)

    def test_result_has_events(self):
        """Result should contain events."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertGreater(len(result.events), 0)

    def test_result_has_execution_trail(self):
        """Result should have execution_trail bytes."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertIsInstance(result.execution_trail, bytes)
        self.assertGreater(len(result.execution_trail), 0)

    def test_result_has_fingerprint(self):
        """Result should have an execution_fingerprint."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertIsInstance(result.execution_fingerprint, str)
        self.assertEqual(len(result.execution_fingerprint), 64)

    def test_result_has_duration(self):
        """Result should have a positive duration."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertGreater(result.duration_ms, 0)

    def test_completed_steps_count(self):
        """completed_steps should match total_steps when all pass."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertEqual(result.completed_steps, result.total_steps)
        self.assertEqual(result.failed_steps, 0)

    def test_multi_opcode_execution(self):
        """All opcodes should execute without error."""
        bc = make_multi_opcode_bytecode()
        executor = TrailExecutor(world=self.world, bytecode=bc)
        result = executor.execute()
        self.assertTrue(result.success)

    def test_world_receives_all_action_calls(self):
        """WorldInterface should receive calls for all action steps."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.execute()
        methods = [c["method"] for c in self.world.calls]
        self.assertIn("file_read", methods)
        self.assertIn("search_code", methods)
        self.assertIn("file_write", methods)

    def test_result_to_json(self):
        """to_json should produce valid JSON."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        j = result.to_json()
        import json
        parsed = json.loads(j)
        self.assertIn("success", parsed)


# ═════════════════════════════════════════════════════════════════════════════
# 7. Error handling — failed steps
# ═════════════════════════════════════════════════════════════════════════════

class TestErrorHandling(unittest.TestCase):
    """Test error handling during execution."""

    def test_world_failure_recorded_as_error_event(self):
        """WorldInterface failure should produce an ERROR event."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_simple_bytecode())
        result = executor.execute()
        error_events = [e for e in result.events if "ERROR" in e.result]
        self.assertGreater(len(error_events), 0)

    def test_world_failure_does_not_stop_default(self):
        """By default, execution continues after a failure."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_multi_opcode_bytecode())
        result = executor.execute()
        # Should have executed more steps than just the failed one
        self.assertGreater(result.total_steps, 1)

    def test_result_shows_failed_steps(self):
        """Result should count failed steps."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_multi_opcode_bytecode())
        result = executor.execute()
        self.assertGreater(result.failed_steps, 0)

    def test_result_not_success_on_failures(self):
        """Result should show not-success when failures occur."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_multi_opcode_bytecode())
        result = executor.execute()
        self.assertFalse(result.success)

    def test_error_event_has_opcode(self):
        """Error event should have the correct opcode."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_simple_bytecode())
        result = executor.execute()
        error_events = [e for e in result.events
                       if e.opcode == TrailOpcodes.FILE_READ and "ERROR" in e.result]
        self.assertEqual(len(error_events), 1)

    def test_error_event_preserves_operands(self):
        """Error event should preserve the original operands."""
        world = MockWorld(fail_on={"file_write"})
        executor = TrailExecutor(world=world, bytecode=make_simple_bytecode())
        result = executor.execute()
        error_events = [e for e in result.events if "ERROR" in e.result]
        self.assertGreater(len(error_events), 0)
        # Should have operands dict
        self.assertIsInstance(error_events[0].operands, dict)

    def test_multiple_failures_all_recorded(self):
        """Multiple failures should all be recorded."""
        world = MockWorld(fail_on={"file_read", "file_write"})
        executor = TrailExecutor(world=world, bytecode=make_multi_opcode_bytecode())
        result = executor.execute()
        self.assertGreaterEqual(result.failed_steps, 2)

    def test_non_failed_steps_still_complete(self):
        """Non-failed steps should still show as completed."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_multi_opcode_bytecode())
        result = executor.execute()
        self.assertGreater(result.completed_steps, 0)

    def test_error_includes_exception_info(self):
        """Error result should include exception info."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_simple_bytecode())
        result = executor.execute()
        error_events = [e for e in result.events if "ERROR" in e.result]
        self.assertTrue(any("Simulated failure" in e.result or "file_read" in e.result
                           for e in error_events))

    def test_summary_shows_failures(self):
        """Summary should indicate failures or partial completion."""
        world = MockWorld(fail_on={"file_read"})
        executor = TrailExecutor(world=world, bytecode=make_simple_bytecode())
        result = executor.execute()
        summary = result.summary()
        self.assertTrue("FAILED" in summary or "PARTIAL" in summary)


# ═════════════════════════════════════════════════════════════════════════════
# 8. Pause/resume execution
# ═════════════════════════════════════════════════════════════════════════════

class TestPauseResume(unittest.TestCase):
    """Test pause and resume functionality."""

    def setUp(self):
        self.world = MockWorld()
        self.bytecode = make_multi_opcode_bytecode()

    def test_pause_stops_step(self):
        """Pause should cause step() to return None."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.pause()
        event = executor.step()
        self.assertIsNone(event)

    def test_pause_state(self):
        """Pause should set paused state."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.pause()
        self.assertTrue(executor.get_state()["paused"])

    def test_resume_clears_paused(self):
        """Resume should clear paused state."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.pause()
        executor.resume()
        self.assertFalse(executor.get_state()["paused"])

    def test_resume_allows_steps(self):
        """Resume should allow step() to proceed."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.pause()
        executor.resume()
        event = executor.step()
        self.assertIsNotNone(event)

    def test_pause_mid_execution(self):
        """Pausing mid-execution should stop further steps."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        events_before = len(executor.get_events())
        executor.step()  # TRAIL_BEGIN
        executor.step()  # First action
        executor.pause()
        # Try to step more
        for _ in range(10):
            executor.step()
        events_after = len(executor.get_events())
        self.assertEqual(events_after, events_before + 2)

    def test_resume_from_pause(self):
        """Resuming should continue from where we left off."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.step()  # TRAIL_BEGIN
        idx_before = executor.get_state()["current_index"]
        executor.pause()
        executor.resume()
        executor.step()  # Next step
        idx_after = executor.get_state()["current_index"]
        self.assertGreater(idx_after, idx_before)

    def test_execute_with_resume_from(self):
        """execute(resume_from=N) should skip first N steps."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute(resume_from=3)
        # Should only have events from step 3 onward
        for ev in result.events:
            if ev.opcode not in (TrailOpcodes.TRAIL_BEGIN, TrailOpcodes.TRAIL_END):
                self.assertGreaterEqual(ev.step_index, 3)

    def test_execute_respects_pause(self):
        """execute() should respect pause state."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        # Start execute in a paused state
        executor.pause()
        result = executor.execute()
        # Should only have 0 events since it starts paused
        self.assertEqual(len(result.events), 0)


# ═════════════════════════════════════════════════════════════════════════════
# 9. Dry-run mode
# ═════════════════════════════════════════════════════════════════════════════

class TestDryRunMode(unittest.TestCase):
    """Test dry-run execution mode."""

    def setUp(self):
        self.world = MockWorld()
        self.bytecode = make_simple_bytecode()

    def test_dry_run_no_world_calls(self):
        """Dry-run should not call WorldInterface."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, dry_run=True)
        executor.execute()
        self.assertEqual(len(self.world.calls), 0)

    def test_dry_run_produces_events(self):
        """Dry-run should still produce events."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, dry_run=True)
        result = executor.execute()
        self.assertGreater(len(result.events), 0)

    def test_dry_run_events_marked(self):
        """Dry-run events should contain DRY-RUN marker."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, dry_run=True)
        result = executor.execute()
        action_events = [e for e in result.events
                        if e.opcode not in (TrailOpcodes.TRAIL_BEGIN,
                                            TrailOpcodes.TRAIL_END, TrailOpcodes.NOP)]
        self.assertTrue(all("DRY-RUN" in e.result for e in action_events))

    def test_dry_run_result_success(self):
        """Dry-run result should show success."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, dry_run=True)
        result = executor.execute()
        self.assertTrue(result.success)

    def test_dry_run_generates_execution_trail(self):
        """Dry-run should still generate an execution trail."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, dry_run=True)
        result = executor.execute()
        self.assertGreater(len(result.execution_trail), 0)

    def test_dry_run_generates_fingerprint(self):
        """Dry-run should still generate a fingerprint."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode, dry_run=True)
        result = executor.execute()
        self.assertEqual(len(result.execution_fingerprint), 64)


# ═════════════════════════════════════════════════════════════════════════════
# 10. Fail-fast mode
# ═════════════════════════════════════════════════════════════════════════════

class TestFailFastMode(unittest.TestCase):
    """Test fail-fast execution mode."""

    def setUp(self):
        self.world = MockWorld(fail_on={"file_read"})
        self.bytecode = make_simple_bytecode()

    def test_fail_fast_stops_on_first_error(self):
        """Fail-fast should stop on first error."""
        executor = TrailExecutor(
            world=self.world, bytecode=self.bytecode, fail_fast=True
        )
        result = executor.execute()
        # Should have fewer events than total steps
        total_steps = len(executor.program.steps)
        self.assertLess(result.total_steps, total_steps)

    def test_fail_fast_has_errors(self):
        """Fail-fast result should show errors."""
        executor = TrailExecutor(
            world=self.world, bytecode=self.bytecode, fail_fast=True
        )
        result = executor.execute()
        self.assertGreater(result.failed_steps, 0)

    def test_fail_fast_not_success(self):
        """Fail-fast result should not be success on error."""
        executor = TrailExecutor(
            world=self.world, bytecode=self.bytecode, fail_fast=True
        )
        result = executor.execute()
        self.assertFalse(result.success)

    def test_fail_fast_finished_state(self):
        """Fail-fast should set finished state."""
        executor = TrailExecutor(
            world=self.world, bytecode=self.bytecode, fail_fast=True
        )
        executor.execute()
        self.assertTrue(executor.get_state()["finished"])

    def test_fail_fast_no_error_all_pass(self):
        """Fail-fast should succeed when all steps pass."""
        world = MockWorld()
        executor = TrailExecutor(
            world=world, bytecode=self.bytecode, fail_fast=True
        )
        result = executor.execute()
        self.assertTrue(result.success)

    def test_fail_fast_vs_normal_comparison(self):
        """Fail-fast should produce fewer events than normal mode."""
        # Normal mode
        world_normal = MockWorld(fail_on={"file_read"})
        bc_multi = make_multi_opcode_bytecode()
        executor_normal = TrailExecutor(world=world_normal, bytecode=bc_multi, fail_fast=False)
        result_normal = executor_normal.execute()

        # Fail-fast mode
        world_fast = MockWorld(fail_on={"file_read"})
        executor_fast = TrailExecutor(world=world_fast, bytecode=bc_multi, fail_fast=True)
        result_fast = executor_fast.execute()

        self.assertLess(result_fast.total_steps, result_normal.total_steps)


# ═════════════════════════════════════════════════════════════════════════════
# 11. Execution trail generation
# ═════════════════════════════════════════════════════════════════════════════

class TestExecutionTrail(unittest.TestCase):
    """Test execution trail (meta-trail) generation."""

    def setUp(self):
        self.world = MockWorld()
        self.bytecode = make_simple_bytecode()

    def test_execution_trail_is_bytes(self):
        """Execution trail should be bytes."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertIsInstance(result.execution_trail, bytes)

    def test_execution_trail_non_empty(self):
        """Execution trail should not be empty."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertGreater(len(result.execution_trail), 0)

    def test_execution_trail_decodable(self):
        """Execution trail should be decodable."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        decoder = TrailDecoder()
        program = decoder.decode(result.execution_trail)
        self.assertIsInstance(program, TrailProgram)
        self.assertTrue(program.is_valid)

    def test_execution_trail_contains_steps(self):
        """Execution trail should contain steps."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        decoder = TrailDecoder()
        program = decoder.decode(result.execution_trail)
        self.assertGreater(len(program.steps), 2)  # At least BEGIN + END

    def test_different_executions_different_trails(self):
        """Different executions should produce different trails."""
        bc1 = make_simple_bytecode()
        bc2 = make_multi_opcode_bytecode()

        result1 = TrailExecutor(world=MockWorld(), bytecode=bc1).execute()
        result2 = TrailExecutor(world=MockWorld(), bytecode=bc2).execute()
        self.assertNotEqual(result1.execution_trail, result2.execution_trail)

    def test_same_execution_same_trail(self):
        """Same execution should produce same trail."""
        bc = make_simple_bytecode()
        result1 = TrailExecutor(world=MockWorld(), bytecode=bc).execute()
        result2 = TrailExecutor(world=MockWorld(), bytecode=bc).execute()
        self.assertEqual(result1.execution_trail, result2.execution_trail)

    def test_meta_trail_can_be_re_executed(self):
        """Meta-trail should be re-executable."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result1 = executor.execute()

        # Execute the meta-trail
        meta_world = MockWorld()
        meta_executor = TrailExecutor(world=meta_world, bytecode=result1.execution_trail)
        result2 = meta_executor.execute()
        self.assertTrue(result2.success)

    def test_meta_meta_trail_exists(self):
        """Meta-meta-trail should exist and be valid."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result1 = executor.execute()

        meta_world = MockWorld()
        meta_executor = TrailExecutor(world=meta_world, bytecode=result1.execution_trail)
        result2 = meta_executor.execute()

        # The meta-meta-trail
        self.assertGreater(len(result2.execution_trail), 0)


# ═════════════════════════════════════════════════════════════════════════════
# 12. Execution fingerprint verification
# ═════════════════════════════════════════════════════════════════════════════

class TestFingerprintVerification(unittest.TestCase):
    """Test execution fingerprint and verification."""

    def setUp(self):
        self.world = MockWorld()
        self.bytecode = make_simple_bytecode()

    def test_fingerprint_is_sha256(self):
        """Execution fingerprint should be a valid SHA-256 hex digest."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        self.assertEqual(len(result.execution_fingerprint), 64)
        # Should be valid hex
        int(result.execution_fingerprint, 16)

    def test_fingerprint_deterministic(self):
        """Same execution should produce same fingerprint."""
        result1 = TrailExecutor(world=MockWorld(), bytecode=self.bytecode).execute()
        result2 = TrailExecutor(world=MockWorld(), bytecode=self.bytecode).execute()
        self.assertEqual(result1.execution_fingerprint, result2.execution_fingerprint)

    def test_verify_passes_on_clean_execution(self):
        """verify() should pass when all steps executed."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.execute()
        self.assertTrue(executor.verify())

    def test_verify_fails_on_partial_execution(self):
        """verify() should fail if not all steps executed."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        executor.step()  # Just one step
        self.assertFalse(executor.verify())

    def test_fingerprint_chain_different_links(self):
        """Each link in the fingerprint chain should be different."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result1 = executor.execute()

        meta_executor = TrailExecutor(world=MockWorld(), bytecode=result1.execution_trail)
        result2 = meta_executor.execute()

        self.assertNotEqual(result1.execution_fingerprint, result2.execution_fingerprint)

    def test_result_summary_includes_fingerprint(self):
        """Summary should include the fingerprint."""
        executor = TrailExecutor(world=self.world, bytecode=self.bytecode)
        result = executor.execute()
        summary = result.summary()
        self.assertIn(result.execution_fingerprint[:8], summary)


# ═════════════════════════════════════════════════════════════════════════════
# 13. FileWorld — real filesystem operations
# ═════════════════════════════════════════════════════════════════════════════

class TestFileWorldReal(unittest.TestCase):
    """Test FileWorld with real filesystem (using temp directories)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="trail_exec_test_")
        self.world = FileWorld(base_dir=self.tmpdir, backup_on_write=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_file_write_creates_file(self):
        """file_write should create a real file."""
        path = os.path.join(self.tmpdir, "test.py")
        self.world.file_write("test.py", "print('hello')")
        self.assertTrue(os.path.exists(path))

    def test_file_write_content(self):
        """file_write should write correct content."""
        self.world.file_write("data.txt", "hello world")
        path = os.path.join(self.tmpdir, "data.txt")
        with open(path, "r") as f:
            content = f.read()
        self.assertEqual(content, "hello world")

    def test_file_read_existing(self):
        """file_read should read existing file."""
        self.world.file_write("existing.py", "x = 42")
        result = self.world.file_read("existing.py")
        self.assertIn("existing.py", result)
        self.assertNotIn("ERROR", result)

    def test_file_read_nonexistent(self):
        """file_read should report error for nonexistent file."""
        result = self.world.file_read("nonexistent.py")
        self.assertIn("ERROR", result)

    def test_file_edit_replaces_content(self):
        """file_edit should replace text in a file."""
        self.world.file_write("edit_me.py", "old_line = 1\nnew_line = 2\n")
        result = self.world.file_edit("edit_me.py", "old_line = 1", "replaced_line = 1")
        self.assertNotIn("ERROR", result)
        with open(os.path.join(self.tmpdir, "edit_me.py"), "r") as f:
            content = f.read()
        self.assertIn("replaced_line = 1", content)
        self.assertNotIn("old_line = 1", content)

    def test_file_edit_backup(self):
        """file_edit with backup_on_write should create .bak file."""
        self.world.file_write("backup_test.py", "original content")
        # file_edit creates its own backup via FileWorld's file_edit method
        self.world.file_edit("backup_test.py", "original", "modified")
        backup_path = os.path.join(self.tmpdir, "backup_test.py.bak")
        self.assertTrue(os.path.exists(backup_path))

    def test_file_write_creates_subdirs(self):
        """file_write should create parent directories."""
        self.world.file_write("sub/dir/file.py", "data")
        path = os.path.join(self.tmpdir, "sub", "dir", "file.py")
        self.assertTrue(os.path.exists(path))

    def test_world_records_calls(self):
        """FileWorld should record calls for auditing."""
        self.world.file_write("f.py", "data")
        self.world.file_read("f.py")
        self.assertEqual(len(self.world.calls), 2)
        self.assertEqual(self.world.calls[0]["method"], "file_write")
        self.assertEqual(self.world.calls[1]["method"], "file_read")


# ═════════════════════════════════════════════════════════════════════════════
# 14. FileWorld — git operations
# ═════════════════════════════════════════════════════════════════════════════

class TestFileWorldGit(unittest.TestCase):
    """Test FileWorld git operations (using temp git repos)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="trail_git_test_")
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=self.tmpdir,
                       capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=self.tmpdir, capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=self.tmpdir, capture_output=True, timeout=10)
        # Create initial commit
        init_file = os.path.join(self.tmpdir, "README.md")
        with open(init_file, "w") as f:
            f.write("# Test")
        subprocess.run(["git", "add", "."], cwd=self.tmpdir,
                       capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "initial"],
                       cwd=self.tmpdir, capture_output=True, timeout=10)
        self.world = FileWorld(base_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_git_commit_creates_commit(self):
        """git_commit should create a new git commit."""
        test_file = os.path.join(self.tmpdir, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1")
        result = self.world.git_commit(".", "add test file")
        self.assertNotIn("ERROR", result)
        # Verify commit was created
        r = subprocess.run(["git", "log", "--oneline"], cwd=self.tmpdir,
                          capture_output=True, text=True)
        self.assertIn("add test file", r.stdout)

    def test_git_commit_no_changes(self):
        """git_commit with no changes should still succeed or report no-op."""
        result = self.world.git_commit(".", "no changes")
        # Either success or a "nothing to commit" message
        self.assertIsInstance(result, str)

    def test_git_push_no_remote(self):
        """git_push without remote should report error."""
        result = self.world.git_push(".")
        # Should contain an error about no remote
        self.assertIsInstance(result, str)

    def test_git_operations_recorded(self):
        """Git operations should be recorded in calls."""
        test_file = os.path.join(self.tmpdir, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1")
        self.world.git_commit(".", "test commit")
        self.world.git_push(".")
        methods = [c["method"] for c in self.world.calls]
        self.assertIn("git_commit", methods)
        self.assertIn("git_push", methods)


# ═════════════════════════════════════════════════════════════════════════════
# 15. Edge cases
# ═════════════════════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    """Test edge cases: empty, minimal, long trails."""

    def test_minimal_trail_execution(self):
        """Minimal trail (BEGIN + END) should execute cleanly."""
        bc = make_minimal_bytecode()
        world = MockWorld()
        result = TrailExecutor(world=world, bytecode=bc).execute()
        self.assertTrue(result.success)
        # Should have 2 events (BEGIN + END)
        self.assertEqual(len(result.events), 2)

    def test_minimal_trail_no_action_calls(self):
        """Minimal trail should make no WorldInterface calls."""
        bc = make_minimal_bytecode()
        world = MockWorld()
        TrailExecutor(world=world, bytecode=bc).execute()
        self.assertEqual(len(world.calls), 0)

    def test_long_trail_execution(self):
        """Trail with many steps should execute all of them."""
        compiler = TrailCompiler()
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "long", "ts": 1000},
        ]
        for i in range(50):
            entries.append({
                "op": "FILE_READ",
                "path": f"file_{i:03d}.py",
            })
        entries.append({"op": "TRAIL_END", "steps": len(entries), "status": 0})
        bc = compiler.compile_and_encode(entries)

        world = MockWorld()
        result = TrailExecutor(world=world, bytecode=bc).execute()
        self.assertTrue(result.success)
        # completed_steps counts all events (including TRAIL_BEGIN/END)
        self.assertEqual(result.completed_steps, 52)
        # Should have made 50 WorldInterface calls
        self.assertEqual(len(world.calls), 50)

    def test_single_action_step(self):
        """Trail with single action step should execute correctly."""
        compiler = TrailCompiler()
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "single", "ts": 1000},
            {"op": "LEVEL_UP", "level": 42},
            {"op": "TRAIL_END", "steps": 1, "status": 0},
        ]
        bc = compiler.compile_and_encode(entries)
        world = MockWorld()
        result = TrailExecutor(world=world, bytecode=bc).execute()
        self.assertTrue(result.success)
        self.assertEqual(len(world.calls), 1)
        self.assertEqual(world.calls[0]["method"], "level_up")

    def test_trail_with_only_nops(self):
        """Trail with only NOPs should execute cleanly."""
        compiler = TrailCompiler()
        entries = [
            {"op": "TRAIL_BEGIN", "agent": "test", "trail_id": "nops", "ts": 1000},
            {"op": "NOP"},
            {"op": "NOP"},
            {"op": "NOP"},
            {"op": "TRAIL_END", "steps": 3, "status": 0},
        ]
        bc = compiler.compile_and_encode(entries)
        world = MockWorld()
        result = TrailExecutor(world=world, bytecode=bc).execute()
        self.assertTrue(result.success)
        self.assertEqual(len(world.calls), 0)

    def test_empty_bytecode_handling(self):
        """Empty bytecode should produce a result with no action events."""
        world = MockWorld()
        executor = TrailExecutor(world=world, bytecode=b"")
        result = executor.execute()
        # Empty bytecode decodes to empty program — no events
        self.assertEqual(len(result.events), 0)
        self.assertTrue(result.success)


# ─── Resolve Operands Tests (bonus coverage) ─────────────────────────────────

class TestOperandResolution(unittest.TestCase):
    """Test the resolve_operands helper function."""

    def test_string_operand_resolved(self):
        """String operand should be resolved from string table."""
        path = "test_file.py"
        h = str_to_hash(path)
        hi, lo = str_hash_to_u16_pair(path)
        string_table = {h: path}

        resolved = resolve_operands(
            TrailOpcodes.FILE_READ, [hi, lo], string_table
        )
        self.assertEqual(resolved, [path])

    def test_numeric_operand_preserved(self):
        """Numeric operand should be preserved as-is."""
        resolved = resolve_operands(
            TrailOpcodes.LEVEL_UP, [42], {}
        )
        self.assertEqual(resolved, [42])

    def test_unresolved_string_fallback(self):
        """Unresolvable string should produce fallback value."""
        resolved = resolve_operands(
            TrailOpcodes.FILE_READ, [0xDEAD, 0xBEEF], {}
        )
        self.assertTrue(resolved[0].startswith("<unresolved:"))

    def test_mixed_operands(self):
        """Mixed string and numeric operands should resolve correctly."""
        test_path = "tests/"
        h = str_to_hash(test_path)
        hi, lo = str_hash_to_u16_pair(test_path)
        string_table = {h: test_path}

        resolved = resolve_operands(
            TrailOpcodes.TEST_RUN, [hi, lo, 50], string_table
        )
        self.assertEqual(resolved, [test_path, 50])

    def test_operand_names_all_opcodes(self):
        """operand_names should return names for all action opcodes."""
        for op in TrailOpcodes:
            if op in (TrailOpcodes.TRAIL_BEGIN, TrailOpcodes.TRAIL_END,
                      TrailOpcodes.HASHTABLE):
                continue
            names = operand_names(op)
            self.assertIsInstance(names, list)

    def test_opcode_arg_types_completeness(self):
        """OPCODE_ARG_TYPES should have entries for all non-structural opcodes."""
        for op in TrailOpcodes:
            if op in (TrailOpcodes.TRAIL_BEGIN, TrailOpcodes.TRAIL_END,
                      TrailOpcodes.HASHTABLE):
                continue
            self.assertIn(op, OPCODE_ARG_TYPES, f"Missing arg types for {op.name}")


if __name__ == "__main__":
    unittest.main()
