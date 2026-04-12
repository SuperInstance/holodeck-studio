"""Tests for the Instinct Engine — reflex evaluation, priority sorting."""
import pytest
from instinct import InstinctEngine, Reflex


class TestInstinctEngine:
    def setup_method(self):
        self.engine = InstinctEngine()

    def test_no_reflexes_calm_state(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.1, trust=0.5,
            has_work=True, idle_ticks=0)
        # With work and moderate trust, guard reflex should fire
        assert any(r.instinct == "guard" for r in reflexes)

    def test_survive_reflex(self):
        reflexes = self.engine.tick(
            energy=0.1, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=0)
        assert any(r.instinct == "survive" for r in reflexes)
        survive = [r for r in reflexes if r.instinct == "survive"]
        assert len(survive) == 2
        assert survive[0].action == "go"
        assert survive[0].text == "harbor"
        assert survive[0].priority == 1.0

    def test_flee_reflex(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.9, trust=0.0,
            has_work=False, idle_ticks=0)
        assert any(r.instinct == "flee" for r in reflexes)
        flee = [r for r in reflexes if r.instinct == "flee"]
        assert flee[0].action == "go"
        assert flee[0].text == "lighthouse"

    def test_report_reflex(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.5, trust=0.0,
            has_work=False, idle_ticks=0)
        assert any(r.instinct == "report" for r in reflexes)

    def test_report_not_at_boundary(self):
        """Report only fires when 0.3 <= threat < 0.7."""
        # Below range
        reflexes = self.engine.tick(
            energy=0.8, threat=0.2, trust=0.0,
            has_work=False, idle_ticks=0)
        assert not any(r.instinct == "report" for r in reflexes)

        # Above range
        reflexes = self.engine.tick(
            energy=0.8, threat=0.8, trust=0.0,
            has_work=False, idle_ticks=0)
        assert not any(r.instinct == "report" for r in reflexes)

    def test_hoard_reflex(self):
        """Hoard fires when 0.15 < energy <= 0.4."""
        reflexes = self.engine.tick(
            energy=0.3, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=0)
        assert any(r.instinct == "hoard" for r in reflexes)

    def test_hoard_not_at_survive_level(self):
        """Hoard should NOT fire at survive energy level."""
        reflexes = self.engine.tick(
            energy=0.1, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=0)
        assert not any(r.instinct == "hoard" for r in reflexes)

    def test_cooperate_reflex(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.0, trust=0.7,
            has_work=False, idle_ticks=0)
        assert any(r.instinct == "cooperate" for r in reflexes)

    def test_teach_reflex(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.0, trust=0.9,
            has_work=False, idle_ticks=0)
        teach = [r for r in reflexes if r.instinct == "teach"]
        assert len(teach) == 2
        assert teach[0].action == "go"
        assert teach[0].text == "dojo"

    def test_curious_reflex(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=150)
        assert any(r.instinct == "curious" for r in reflexes)

    def test_curious_not_below_threshold(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=50)
        assert not any(r.instinct == "curious" for r in reflexes)

    def test_mourn_reflex(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=0, peer_died=True)
        assert any(r.instinct == "mourn" for r in reflexes)
        mourn = [r for r in reflexes if r.instinct == "mourn"]
        assert mourn[0].action == "go"
        assert mourn[0].text == "graveyard"

    def test_evolve_reflex(self):
        reflexes = self.engine.tick(
            energy=0.8, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=600)
        assert any(r.instinct == "evolve" for r in reflexes)

    def test_priority_sorting(self):
        reflexes = self.engine.tick(
            energy=0.05, threat=0.8, trust=0.9,
            has_work=False, idle_ticks=600, peer_died=True)
        # Should have survive, flee, mourn, teach, evolve, etc.
        priorities = [r.priority for r in reflexes]
        assert priorities == sorted(priorities, reverse=True)
        assert priorities[0] == 1.0  # survive is highest

    def test_top_reflex(self):
        reflex = self.engine.top_reflex(
            energy=0.05, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=0)
        assert reflex is not None
        assert reflex.instinct == "survive"
        assert reflex.priority == 1.0

    def test_top_reflex_none(self):
        """With no triggers, top_reflex returns None."""
        # energy=0.5, threat=0, trust=0.3, no work, idle=50, no death
        reflex = self.engine.top_reflex(
            energy=0.5, threat=0.0, trust=0.3,
            has_work=False, idle_ticks=50)
        assert reflex is None

    def test_top_reflex_has_work(self):
        reflex = self.engine.top_reflex(
            energy=0.8, threat=0.0, trust=0.0,
            has_work=True, idle_ticks=0)
        assert reflex is not None
        assert reflex.instinct == "guard"

    def test_tick_increments_counter(self):
        assert self.engine.tick_count == 0
        self.engine.tick(0.8, 0.0, 0.5, False, 0)
        assert self.engine.tick_count == 1
        self.engine.tick(0.8, 0.0, 0.5, False, 0)
        assert self.engine.tick_count == 2

    def test_peer_death_tracking(self):
        self.engine.tick(0.8, 0.0, 0.5, False, 0, peer_died=True)
        assert self.engine.last_peer_death is True
        self.engine.tick(0.8, 0.0, 0.5, False, 0, peer_died=False)
        assert self.engine.last_peer_death is False

    def test_instincts_list(self):
        expected = ["survive", "flee", "guard", "report", "hoard",
                    "cooperate", "teach", "curious", "mourn", "evolve"]
        assert InstinctEngine.INSTINCTS == expected

    def test_multiple_simultaneous_instincts(self):
        """Test that multiple instincts can fire at once."""
        reflexes = self.engine.tick(
            energy=0.1, threat=0.8, trust=0.9,
            has_work=True, idle_ticks=600, peer_died=True)
        instincts = {r.instinct for r in reflexes}
        assert "survive" in instincts
        assert "flee" in instincts
        assert "guard" in instincts
        assert "mourn" in instincts
        assert "teach" in instincts
        assert "evolve" in instincts

    def test_energy_boundary_at_zero(self):
        """Energy at exactly 0.15 triggers survive."""
        reflexes = self.engine.tick(
            energy=0.15, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=0)
        assert any(r.instinct == "survive" for r in reflexes)

    def test_energy_boundary_just_above(self):
        """Energy at 0.16 does NOT trigger survive but might trigger hoard."""
        reflexes = self.engine.tick(
            energy=0.16, threat=0.0, trust=0.0,
            has_work=False, idle_ticks=0)
        assert not any(r.instinct == "survive" for r in reflexes)

    def test_threat_boundary_at_0_7(self):
        """Threat at exactly 0.7 triggers flee."""
        reflexes = self.engine.tick(
            energy=0.8, threat=0.7, trust=0.0,
            has_work=False, idle_ticks=0)
        assert any(r.instinct == "flee" for r in reflexes)

    def test_reflex_dataclass(self):
        r = Reflex("test", "go", "tavern", 0.5)
        assert r.instinct == "test"
        assert r.action == "go"
        assert r.text == "tavern"
        assert r.priority == 0.5
