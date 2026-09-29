"""Behavioral tests against the compiled C++ executable (no Python solver)."""
import copy
from datetime import date, timedelta
import json
import os
from pathlib import Path
import random
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get("CORE_BINARY", ROOT / "core" / ("ensalamento-core.exe" if os.name == "nt" else "ensalamento-core")))


def run(payload, expected_code=0):
    assert BINARY.is_file(), f"Compile the C++ core first: {BINARY}"
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    process = subprocess.run([str(BINARY)], input=raw, text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert process.returncode == expected_code, process.stdout + process.stderr
    return json.loads(process.stdout)


def room(key="r1", **extra):
    return dict(id=key, name=key, campus_id="campus", building_id="a", capacity=30,
                resources=["projetor"], accessible=True, status="active", unavailable=[], **extra)


def klass(key="c1", **extra):
    value = dict(id=key, campus_id="campus", size_expected=25, size_confirmed=None,
                 teacher_emails=[f"{key}@example.edu"], required_resources=[],
                 preferred_resources=[], needs_accessibility=False, status="approved")
    value.update(extra)
    return value


def meeting(key="m1", class_id="c1", **extra):
    value = dict(id=key, class_id=class_id, weekday=0, start="08:00", end="10:00",
                 start_date="2026-09-01", end_date="2026-12-15", excluded_dates=[])
    value.update(extra)
    return value


def fixture():
    return dict(mode="allocate", rooms=[room()], classes=[klass()], meetings=[meeting()], allocations=[])


def codes(output):
    return {c["code"] for c in output["conflicts"]}


def add_second(data, **meeting_extra):
    data["classes"].append(klass("c2"))
    data["meetings"].append(meeting("m2", "c2", **meeting_extra))


def assignments(output):
    return {a["meeting_id"]: a["room_id"] for a in output["allocations"]}


def test_basic_allocation_has_explanation_and_validates():
    data = fixture()
    result = run(data)
    assert result["valid"]
    assert assignments(result) == {"m1": "r1"}
    assert "capacidade 30 para 25" in result["allocations"][0]["explanation"]
    assert result["statistics"]["average_occupancy_percent"] == 83.33
    data.update(mode="validate", allocations=result["allocations"])
    assert run(data)["valid"]


@pytest.mark.parametrize("field,value,reason", [
    ("capacity", 24, "Capacidade insuficiente"),
    ("status", "maintenance", "manutenção"),
    ("status", "inactive", "desativada"),
    ("campus_id", "outro", "campus"),
])
def test_required_room_constraints(field, value, reason):
    data = fixture()
    data["rooms"][0][field] = value
    result = run(data)
    assert not result["valid"] and not result["allocations"]
    assert reason in " ".join(result["unallocated"][0]["reasons"])


def test_confirmed_size_overrides_expected_size_and_equal_capacity_is_valid():
    data = fixture()
    data["classes"][0].update(size_expected=70, size_confirmed=30)
    assert run(data)["valid"]
    data["classes"][0]["size_confirmed"] = 31
    assert not run(data)["valid"]


def test_required_resources_and_accessibility_cannot_be_bought_by_weights():
    data = fixture()
    data["classes"][0].update(required_resources=["laboratório"], needs_accessibility=True)
    data["rooms"][0].update(accessible=False)
    data["weights"] = {"capacity": 0, "building": 1000000, "resources": 0, "stability": 0}
    result = run(data)
    assert not result["allocations"]
    reasons = " ".join(result["unallocated"][0]["reasons"])
    assert "acessibilidade" in reasons and "laboratório" in reasons


def test_adjacent_intervals_share_a_room():
    data = fixture()
    add_second(data, start="10:00", end="12:00")
    assert run(data)["valid"]


def test_overlapping_intervals_do_not_share_room():
    data = fixture()
    add_second(data, start="09:59", end="12:00")
    result = run(data)
    assert len(result["allocations"]) == 1
    assert len(result["unallocated"]) == 1


def test_validation_rejects_manual_room_collision():
    data = fixture()
    add_second(data)
    data.update(mode="validate", allocations=[dict(meeting_id="m1", room_id="r1"), dict(meeting_id="m2", room_id="r1")])
    assert "ROOM_OVERLAP" in codes(run(data))


def test_teacher_overlap_is_detected_even_without_room_assignment():
    data = fixture()
    add_second(data)
    data["classes"][1]["teacher_emails"] = ["C1@EXAMPLE.EDU"]
    data["rooms"].append(room("r2"))
    result = run(data)
    assert "TEACHER_OVERLAP" in codes(result)
    assert not result["allocations"]
    assert not result["valid"]


def test_same_class_cannot_have_overlapping_meetings():
    data = fixture()
    data["meetings"].append(meeting("m2", "c1", start="09:00", end="11:00"))
    assert "CLASS_OVERLAP" in codes(run(data))


def test_nonoverlapping_calendar_ranges_can_share_room():
    data = fixture()
    data["meetings"][0]["end_date"] = "2026-09-30"
    add_second(data, start_date="2026-10-01")
    assert run(data)["valid"]


def test_exception_matches_recurrence_only_on_actual_weekday():
    data = fixture()
    add_second(data, date="2026-09-08")  # Tuesday; first meeting is Monday.
    assert run(data)["valid"]
    data["meetings"][1]["date"] = "2026-09-07"
    assert not run(data)["valid"]


def test_excluded_date_removes_conflict_with_exception():
    data = fixture()
    add_second(data, date="2026-09-07")
    data["meetings"][0]["excluded_dates"] = ["2026-09-07"]
    assert run(data)["valid"]


def test_recurrences_with_disjoint_remaining_occurrences_can_share_room():
    data = fixture()
    data["meetings"][0].update(start_date="2026-09-07", end_date="2026-09-14", excluded_dates=["2026-09-14"])
    add_second(data, start_date="2026-09-07", end_date="2026-09-14", excluded_dates=["2026-09-07"])
    assert run(data)["valid"]


def test_temporary_unavailability_checks_date_and_exclusions():
    data = fixture()
    data["rooms"][0]["unavailable"] = [dict(date="2026-09-07", start="09:00", end="11:00")]
    assert not run(data)["valid"]
    data["meetings"][0]["excluded_dates"] = ["2026-09-07"]
    assert run(data)["valid"]


def test_recurring_unavailability():
    data = fixture()
    data["rooms"][0]["unavailable"] = [dict(weekday=0, start_date="2026-09-01", end_date="2026-12-15", start="09:00", end="11:00")]
    assert not run(data)["valid"]


def opening(**extra):
    value = dict(weekday=0, start_date="2026-09-01", end_date="2026-12-15", start="08:00", end="10:00")
    value.update(extra)
    return value


def test_weekly_opening_window_covers_all_occurrences():
    data = fixture()
    data["rooms"][0]["available"] = [opening()]
    assert run(data)["valid"]
    data["rooms"][0]["available"][0]["end_date"] = "2026-10-01"
    assert not run(data)["valid"]


def test_exception_outside_opening_day_is_rejected():
    data = fixture()
    data["rooms"][0]["available"] = [opening()]
    data["meetings"][0]["date"] = "2026-09-08"
    result = run(data)
    assert not result["valid"]
    assert "disponibilidade" in " ".join(result["unallocated"][0]["reasons"])


def test_gap_between_opening_windows_cannot_host_continuous_meeting():
    data = fixture()
    data["rooms"][0]["available"] = [opening(end="09:00"), opening(start="09:01")]
    assert not run(data)["valid"]


def test_adjacent_and_overlapping_opening_windows_are_merged():
    data = fixture()
    data["rooms"][0]["available"] = [opening(start="09:00"), opening(end="09:00")]
    assert run(data)["valid"]
    data["rooms"][0]["available"][0]["start"] = "08:30"
    assert run(data)["valid"]


def test_unavailability_overrides_opening_windows():
    data = fixture()
    data["rooms"][0]["available"] = [opening(start="07:00", end="12:00")]
    data["rooms"][0]["unavailable"] = [dict(date="2026-09-07", start="09:00", end="09:30")]
    assert not run(data)["valid"]


def test_excluded_occurrence_does_not_require_opening_window():
    data = fixture()
    data["meetings"][0].update(start_date="2026-09-07", end_date="2026-09-14", excluded_dates=["2026-09-14"])
    data["rooms"][0]["available"] = [dict(date="2026-09-07", start="08:00", end="10:00")]
    assert run(data)["valid"]


def test_difficulty_order_prevents_consuming_only_accessible_room():
    data = fixture()
    data["rooms"][0]["accessible"] = True
    data["rooms"].append(room("r2"))
    data["rooms"][1]["accessible"] = False
    add_second(data)
    data["classes"][1]["needs_accessibility"] = True
    result = run(data)
    assert result["valid"]
    assert assignments(result) == {"m2": "r1", "m1": "r2"}


def test_deterministic_tie_break_does_not_depend_on_room_input_order():
    data = fixture()
    data["rooms"] = [room("z"), room("a")]
    first = run(data)
    data["rooms"].reverse()
    assert assignments(first) == assignments(run(data)) == {"m1": "a"}


def test_weights_rank_only_valid_suggestions_and_report_unmet_preferences():
    data = fixture()
    data["classes"][0].update(preferred_building_id="b", preferred_resources=["ar"])
    data["rooms"].append(room("r2"))
    data["rooms"][1].update(building_id="b", capacity=100)
    data.update(mode="suggest", meeting_id="m1", weights=dict(capacity=0, building=1, resources=0, stability=0))
    result = run(data)
    assert result["suggestions"][0]["room_id"] == "r2"
    assert result["suggestions"][0]["score"] == 100
    assert result["suggestions"][0]["details"]["preferences_unmet"] == ["Recurso: ar"]
    data["rooms"][1]["capacity"] = 20
    assert [s["room_id"] for s in run(data)["suggestions"]] == ["r1"]


def test_stability_prefers_previous_allocation():
    data = fixture()
    data["rooms"].append(room("r2"))
    data["allocations"] = [dict(meeting_id="m1", room_id="r2", locked=False, source="automatic")]
    assert assignments(run(data)) == {"m1": "r2"}


def test_locked_manual_allocation_is_preserved_and_revalidated():
    data = fixture()
    locked = dict(meeting_id="m1", room_id="r1", locked=True, source="manual", explanation="Decisão registrada")
    data["allocations"] = [locked]
    assert run(data)["allocations"] == [locked]
    data["classes"][0]["size_confirmed"] = 31
    result = run(data)
    assert result["allocations"] == [locked]
    assert "CAPACITY" in codes(result)
    assert not result["valid"]


def test_subset_preserves_unselected_allocation_but_validates_entire_schedule():
    data = fixture()
    add_second(data)
    data.update(selected_meeting_ids=["m1"], allocations=[dict(meeting_id="m2", room_id="r1", locked=False)])
    result = run(data)
    assert assignments(result) == {"m2": "r1"}
    assert result["unallocated"][0]["meeting_id"] == "m1"
    assert not result["valid"]


def test_suggestions_allow_current_room_without_self_collision():
    data = fixture()
    data.update(mode="suggest", meeting_id="m1", allocations=[dict(meeting_id="m1", room_id="r1")])
    assert len(run(data)["suggestions"]) == 1


def test_duplicate_allocations_unknown_references_and_missing_meetings_block_validation():
    data = fixture()
    data["classes"].append(klass("c2"))
    data.update(mode="validate", allocations=[dict(meeting_id="m1", room_id="r1"), dict(meeting_id="m1", room_id="ghost"), dict(meeting_id="ghost", room_id="r1")])
    assert codes(run(data)) >= {"DUPLICATE_ALLOCATION", "UNKNOWN_ROOM", "UNKNOWN_MEETING", "CLASS_NO_MEETINGS"}


def test_cancelled_class_does_not_require_allocation():
    data = fixture()
    data["classes"][0]["status"] = "cancelled"
    result = run(data)
    assert result["valid"] and not result["allocations"] and not result["unallocated"]


@pytest.mark.parametrize("mutate", [
    lambda x: x["rooms"][0].update(capacity=0),
    lambda x: x["classes"][0].update(size_expected=-1),
    lambda x: x["classes"][0].update(size_confirmed=0),
    lambda x: x["meetings"][0].update(start="25:00"),
    lambda x: x["meetings"][0].update(end="08:00"),
    lambda x: x["meetings"][0].update(end="07:59"),
    lambda x: x["meetings"][0].update(date="2026-02-29"),
    lambda x: x["meetings"][0].update(end_date="2025-01-01"),
    lambda x: x["meetings"][0].update(class_id="missing"),
    lambda x: x["meetings"][0].update(weekday=7),
    lambda x: x["meetings"].append(copy.deepcopy(x["meetings"][0])),
    lambda x: x.update(weights={"capacity": -1}),
    lambda x: x.update(weights={"capacity": 0, "building": 0, "resources": 0, "stability": 0}),
    lambda x: x.update(weights={"magic": 1}),
    lambda x: x.update(mode="unknown"),
    lambda x: x.update(selected_meeting_ids=["missing"]),
    lambda x: x["rooms"][0].update(accessible="yes"),
    lambda x: x["meetings"][0].update(start_date="2026-09-08", end_date="2026-09-08"),
])
def test_bad_inputs_return_structured_error_without_crashing(mutate):
    data = fixture()
    mutate(data)
    result = run(data, expected_code=2)
    assert not result["valid"] and result["errors"][0]["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("raw", ["{bad", "null", "[]", '{"rooms":{}}', "[" * 70 + "]" * 70])
def test_malformed_json_returns_structured_error(raw):
    assert run(raw, expected_code=2)["errors"]


def test_leap_day_is_supported():
    data = fixture()
    data["meetings"][0]["date"] = "2028-02-29"
    assert run(data)["valid"]


def test_empty_input_collections_are_valid_but_absent_room_is_explained():
    assert run(dict(rooms=[], classes=[], meetings=[]))["valid"]
    data = fixture()
    data["rooms"] = []
    result = run(data)
    assert result["unallocated"][0]["reasons"] == ["Nenhuma sala cadastrada."]


def test_generated_allocations_never_violate_constraints_in_random_small_cases():
    randomizer = random.Random(712)
    for case in range(12):
        data = dict(mode="allocate", rooms=[room(f"r{i}") for i in range(5)], classes=[], meetings=[], allocations=[])
        for r in data["rooms"]:
            r.update(capacity=randomizer.randint(20, 70), accessible=randomizer.choice([True, False]), resources=randomizer.choice([[], ["projetor"]]))
        for i in range(12):
            data["classes"].append(klass(f"c{i}", size_expected=randomizer.randint(15, 55), needs_accessibility=randomizer.choice([True, False]), required_resources=randomizer.choice([[], ["projetor"]])))
            hour = randomizer.choice([8, 10, 12, 14])
            data["meetings"].append(meeting(f"m{i}", f"c{i}", weekday=randomizer.randrange(5), start=f"{hour:02}:00", end=f"{hour+2:02}:00"))
        result = run(data)
        assert result["conflicts"] == [], f"case {case}"
        data.update(mode="validate", allocations=result["allocations"])
        validated = run(data)
        assert validated["conflicts"] == []
        assert validated["unallocated"] == result["unallocated"]


def test_calendar_collisions_match_independent_day_enumeration():
    """Independent datetime oracle checks the C++ ordinal/weekday calculations."""
    randomizer = random.Random(2049)
    for _ in range(80):
        base = date(randomizer.choice([1970, 1999, 2000, 2026, 2028, 2099, 2100]), randomizer.randrange(1, 10), 1)
        data = fixture()
        add_second(data)
        occurrences = []
        for item in data["meetings"]:
            first = base + timedelta(days=randomizer.randrange(14))
            last = first + timedelta(days=randomizer.randrange(14, 60))
            day = randomizer.randrange(7)
            exclusions = {first + timedelta(days=randomizer.randrange((last - first).days + 1)) for _ in range(3)}
            item.update(start_date=first.isoformat(), end_date=last.isoformat(), weekday=day,
                        excluded_dates=sorted(d.isoformat() for d in exclusions))
            dates = {first + timedelta(days=n) for n in range((last - first).days + 1)}
            dates = {d for d in dates if d.weekday() == day and d not in exclusions}
            if not dates:
                item["excluded_dates"] = []
                dates = {first + timedelta(days=n) for n in range((last - first).days + 1)
                         if (first + timedelta(days=n)).weekday() == day}
            if randomizer.choice([False, True]):
                exact = min(dates)
                item["date"] = exact.isoformat()
                dates = {exact}
            occurrences.append(dates)
        data.update(mode="validate", allocations=[dict(meeting_id="m1", room_id="r1"), dict(meeting_id="m2", room_id="r1")])
        actual = "ROOM_OVERLAP" in codes(run(data))
        expected = bool(occurrences[0] & occurrences[1])
        assert actual == expected, data["meetings"]
