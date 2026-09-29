"""Independent security/publication regressions against Flask and the real C++ core."""
import copy
import os
from pathlib import Path

import pytest

from server.app import create_app
from server.store import empty_state

ROOT = Path(__file__).resolve().parents[1]
BINARY = str(ROOT / "core" / ("ensalamento-core.exe" if os.name == "nt" else "ensalamento-core"))


@pytest.fixture
def context(tmp_path):
    app = create_app(dict(TESTING=True, APP_ENV="development", SECRET_KEY="test-key-only-not-a-production-secret",
                          DATABASE_URL="sqlite:///" + str(tmp_path / "review.sqlite"), CORE_BINARY=BINARY,
                          ADMIN_EMAILS=[], ALLOWED_DOMAINS=[], DEV_LOGIN_ENABLED=False))
    store = app.extensions["store"]
    state = empty_state()
    state["periods"] = [dict(id=f"p{i}", code=f"P{i}", name=f"Período {i}", start_date="2026-09-01", end_date="2026-12-15", active=True) for i in (1, 2)]
    state["campuses"] = [dict(id="campus", code="campus", name="Campus", active=True)]
    state["buildings"] = [dict(id="b", code="b", name="Prédio", campus_id="campus", active=True)]
    state["courses"] = [dict(id=f"course{i}", code=f"C{i}", name=f"Curso {i}", campus_id="campus", active=True) for i in (1, 2)]
    state["rooms"] = [dict(id=f"r{i}", code=f"R{i}", name=f"Sala {i}", campus_id="campus", building_id="b", floor="Térreo", capacity=40,
                           resources=[], accessible=True, status="active", available=[], unavailable=[]) for i in (1, 2)]
    state["users"] = [dict(id="admin", email="admin@example.edu", name="Admin", role="admin", course_ids=[], active=True),
                      dict(id="student", email="student@example.edu", name="Aluno", role="student", course_ids=[], active=True),
                      dict(id="coordinator", email="coord@example.edu", name="Coordenação", role="coordinator", course_ids=["course1"], active=True)]
    for i in (1, 2):
        state["users"].append(dict(id=f"teacher{i}", email=f"teacher{i}@example.edu", name=f"Professor {i}", role="teacher", course_ids=[], active=True))
        state["classes"].append(dict(id=f"c{i}", code=f"T{i}", name=f"Turma {i}", course_id=f"course{i}", period_id=f"p{i}", campus_id="campus",
                                     size_expected=30, size_confirmed=None, teacher_emails=[f"teacher{i}@example.edu"], required_resources=[],
                                     preferred_resources=[], needs_accessibility=False, special_justification="", status="approved"))
        state["meetings"].append(dict(id=f"m{i}", class_id=f"c{i}", weekday=0, start="08:00", end="10:00", date=None,
                                      start_date="2026-09-01", end_date="2026-12-15", excluded_dates=[]))
        state["allocations"].append(dict(meeting_id=f"m{i}", room_id="r1", source="manual", locked=False, explanation="Alocação de teste"))
    store.update(None, lambda target: target.update(state))
    client = app.test_client()

    def login(user_id):
        with client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id
            session["csrf_token"] = "test-csrf-token"

    def post(url, **payload):
        payload.setdefault("revision", store.read()[0])
        return client.post(url, json=payload, headers={"X-CSRF-Token": "test-csrf-token"})

    login("admin")
    return dict(app=app, store=store, client=client, login=login, post=post)


def publish(context, period):
    return context["post"]("/api/publish", period_id=period, description="Versão de teste", reason="Regressão automatizada")


def test_publication_rejects_same_room_in_another_active_period(context):
    assert publish(context, "p1").status_code == 200
    response = publish(context, "p2")
    assert response.status_code == 422, response.get_json()
    assert response.get_json()["error"] == "publication_blocked"
    assert any(c["code"] == "ROOM_OVERLAP" for c in response.get_json()["details"]["conflicts"])
    assert set(context["store"].read()[1]["active_versions"]) == {"p1"}


def test_publication_rejects_same_teacher_across_periods_even_in_other_room(context):
    def change(state):
        state["classes"][1]["teacher_emails"] = ["teacher1@example.edu"]
        state["allocations"][1]["room_id"] = "r2"
    context["store"].update(None, change)
    assert publish(context, "p1").status_code == 200
    response = publish(context, "p2")
    assert response.status_code == 422, response.get_json()
    assert any(c["code"] == "TEACHER_OVERLAP" for c in response.get_json()["details"]["conflicts"])


def test_allocate_preserves_other_period_and_respects_its_official_occupancy(context):
    assert publish(context, "p1").status_code == 200
    before = copy.deepcopy(context["store"].read()[1]["versions"][0])
    result = context["post"]("/api/allocate", period_id="p2")
    assert result.status_code == 200, result.get_json()
    state = context["store"].read()[1]
    assert {a["meeting_id"]: a["room_id"] for a in state["allocations"]} == {"m1": "r1", "m2": "r2"}
    assert state["versions"][0] == before
    assert publish(context, "p2").status_code == 200


def test_manual_move_cannot_conflict_with_another_official_period(context):
    assert publish(context, "p1").status_code == 200
    context["store"].update(None, lambda state: state["allocations"][1].update(room_id="r2"))
    response = context["post"]("/api/move", meeting_id="m2", room_id="r1", reason="Teste de conflito")
    assert response.status_code == 422, response.get_json()
    assert context["store"].read()[1]["allocations"][1]["room_id"] == "r2"


def test_nonoverlapping_periods_can_reuse_same_room(context):
    def change(state):
        state["periods"][0]["end_date"] = state["meetings"][0]["end_date"] = "2026-09-30"
        state["periods"][1]["start_date"] = state["meetings"][1]["start_date"] = "2026-10-01"
    context["store"].update(None, change)
    assert publish(context, "p1").status_code == 200
    response = publish(context, "p2")
    assert response.status_code == 200, response.get_json()


@pytest.mark.parametrize("user_id", ["student", "teacher1", "coordinator"])
@pytest.mark.parametrize("endpoint,extra", [("/api/publish", {"period_id": "p1", "description": "Tentativa"}),
                                           ("/api/allocate", {"period_id": "p1"}),
                                           ("/api/import/preview", {"entity": "users", "csv": "id,email,name,role\nx,x@example.edu,X,admin"})])
def test_non_admin_cannot_publish_allocate_or_import(context, user_id, endpoint, extra):
    context["login"](user_id)
    before = context["store"].read()
    response = context["post"](endpoint, **extra)
    assert response.status_code == 403, response.get_json()
    assert context["store"].read() == before


def test_coordinator_cannot_reparent_existing_meeting_or_escalate_role(context):
    context["store"].update(None, lambda state: state["classes"][0].update(status="draft"))
    context["login"]("coordinator")
    before = context["store"].read()
    response = context["post"]("/api/entities/meetings", record=dict(id="m1", class_id="c2"))
    assert response.status_code == 403, response.get_json()
    response = context["post"]("/api/entities/users", record=dict(id="coordinator", role="admin"))
    assert response.status_code == 403, response.get_json()
    assert context["store"].read() == before


def test_coordinator_cannot_create_meeting_for_another_course(context):
    context["login"]("coordinator")
    response = context["post"]("/api/entities/meetings", record=dict(id="attempt", class_id="c2", weekday=1, start="10:00", end="12:00"))
    assert response.status_code == 403, response.get_json()


def test_submitted_coordinator_request_is_locked(context):
    context["store"].update(None, lambda state: state["classes"][0].update(status="submitted"))
    context["login"]("coordinator")
    response = context["post"]("/api/entities/classes", record=dict(id="c1", size_expected=1))
    assert response.status_code == 409, response.get_json()


def test_csrf_is_checked_before_mutation(context):
    before = context["store"].read()
    response = context["client"].post("/api/publish", json={"revision": before[0], "period_id": "p1", "description": "Teste"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "csrf_failed"
    assert context["store"].read() == before


def test_student_and_teacher_do_not_receive_draft_classes(context):
    for user_id in ("student", "teacher1"):
        context["login"](user_id)
        response = context["client"].get("/api/bootstrap?period_id=p1")
        assert response.status_code == 200
        assert response.get_json()["classes"] == []
        assert response.get_json()["allocations"] == []


def test_teacher_cannot_expand_schedule_by_passing_someone_elses_class(context):
    context["store"].update(None, lambda state: state["allocations"][1].update(room_id="r2"))
    assert publish(context, "p1").status_code == 200
    assert publish(context, "p2").status_code == 200
    context["login"]("teacher1")
    response = context["client"].get("/api/schedule?period_id=p2&class_id=c2&date=2026-09-07")
    assert response.status_code == 200
    assert response.get_json()["events"] == []


def test_published_snapshot_does_not_change_when_draft_is_edited(context):
    assert publish(context, "p1").status_code == 200
    response = context["post"]("/api/entities/classes", record=dict(id="c1", name="Nome apenas no rascunho"))
    assert response.status_code == 200, response.get_json()
    context["login"]("student")
    result = context["client"].get("/api/bootstrap?period_id=p1").get_json()
    assert result["classes"][0]["name"] == "Turma 1"


def test_revoked_account_loses_access_with_existing_cookie(context):
    context["login"]("teacher1")
    context["store"].update(None, lambda state: next(u for u in state["users"] if u["id"] == "teacher1").update(active=False))
    response = context["client"].get("/api/bootstrap")
    assert response.status_code == 401


def test_stale_revision_does_not_overwrite_newer_data(context):
    stale = context["store"].read()[0]
    context["store"].update(None, lambda state: state["classes"][0].update(name="Alteração concorrente"))
    response = context["post"]("/api/entities/classes", revision=stale, record=dict(id="c1", name="Dado antigo"))
    assert response.status_code == 409
    assert context["store"].read()[1]["classes"][0]["name"] == "Alteração concorrente"
