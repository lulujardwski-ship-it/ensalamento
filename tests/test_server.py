"""Integração HTTP + banco transacional + núcleo C++ real.

Execute depois de compilar core/ensalamento-core: python -m pytest tests.
Os testes usam contas e dados sintéticos, nunca provedores OAuth reais.
"""
import copy
import json
from pathlib import Path

import pytest

from server.app import ROOT, create_app
from server.seed import demo_state


@pytest.fixture
def app(tmp_path):
    application = create_app({"TESTING": True, "SECRET_KEY": "test-only-do-not-use-in-production-" * 2,
                              "APP_ENV": "development", "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.sqlite3"),
                              "DEV_LOGIN_ENABLED": True, "ADMIN_EMAILS": [], "ALLOWED_DOMAINS": [],
                              "GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": "", "MICROSOFT_CLIENT_ID": "",
                              "MICROSOFT_CLIENT_SECRET": "", "MICROSOFT_TENANT_ID": "", "FRONTEND_URL": ""})
    def populate(state):
        state.clear()
        state.update(demo_state())
    application.extensions["store"].update(None, populate)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, role="admin"):
    result = client.post("/api/dev-login", json={"role": role})
    assert result.status_code == 200, result.get_json()
    return result.get_json()


def bootstrap(client):
    result = client.get("/api/bootstrap")
    assert result.status_code == 200, result.get_json()
    return result.get_json()


def post(client, route, data=None, revision=None):
    current = bootstrap(client)
    payload = {"revision": current["revision"] if revision is None else revision, **(data or {})}
    return client.post(route, json=payload, headers={"X-CSRF-Token": current["csrf_token"]})


def require_core(app):
    assert Path(app.config["CORE_BINARY"]).is_file(), "Compile o núcleo C++ antes dos testes de integração."


def test_private_data_requires_session(client):
    response = client.get("/api/bootstrap")
    assert response.status_code == 401
    assert "classes" not in response.get_json()
    assert client.get("/api/session").get_json()["user"] is None


def test_development_login_is_disabled_by_default_and_nonlocal(app, client):
    app.config["DEV_LOGIN_ENABLED"] = False
    assert client.post("/api/dev-login", json={"role": "admin"}).status_code == 403
    app.config["DEV_LOGIN_ENABLED"] = True
    assert client.post("/api/dev-login", json={"role": "admin"}, environ_base={"REMOTE_ADDR": "203.0.113.1"}).status_code == 403


def test_csrf_and_origin_guards(client):
    login(client)
    data = bootstrap(client)
    assert client.post("/api/weights", json={"revision": data["revision"]}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Origin": "https://attacker.invalid"}).status_code == 403
    assert client.post("/api/dev-login", json={"role": "admin"}, headers={"Origin": "https://attacker.invalid"}).status_code == 403


def test_session_cookie_http_only_and_logout(client):
    response = client.post("/api/dev-login", json={"role": "student"})
    cookie = response.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    csrf = response.get_json()["csrf_token"]
    assert client.post("/api/logout", json={}, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/bootstrap").status_code == 401


def test_student_cannot_publish_or_edit(client):
    login(client, "student")
    assert post(client, "/api/publish", {"description": "Ataque"}).status_code == 403
    assert post(client, "/api/entities/rooms", {"record": {"id": "a101", "capacity": 999}}).status_code == 403


def test_teacher_scope_is_derived_from_authenticated_email(client):
    login(client, "teacher")
    data = bootstrap(client)
    assert {c["id"] for c in data["classes"]} == {"es-web", "es-alg"}
    assert data["users"] == [] and data["audit"] == []
    schedule = client.get("/api/schedule?date=2026-09-29&class_id=adm-gestao&view=week").get_json()
    assert schedule["events"] == []


def test_coordinator_scope_and_lock(client):
    login(client, "coordinator")
    data = bootstrap(client)
    assert {c["course_id"] for c in data["classes"]} == {"software"}
    assert post(client, "/api/entities/classes", {"record": {"id": "adm-gestao", "size_expected": 20}}).status_code == 403
    assert post(client, "/api/entities/classes", {"record": {"id": "es-web", "size_expected": 20}}).status_code == 409
    assert post(client, "/api/publish", {"description": "Indevida"}).status_code == 403


def test_return_edit_submit_lock_and_audit(client):
    login(client)
    assert post(client, "/api/classes/es-web/return", {"reason": "Atualizar previsão de matrícula."}).status_code == 200
    login(client, "coordinator")
    assert post(client, "/api/entities/classes", {"record": {"id": "es-web", "size_expected": 33}}).status_code == 200
    assert post(client, "/api/classes/es-web/submit").status_code == 200
    assert post(client, "/api/entities/classes", {"record": {"id": "es-web", "size_expected": 34}}).status_code == 409
    login(client)
    actions = [event["action"] for event in bootstrap(client)["audit"]]
    assert "return" in actions and "submit" in actions and "update" in actions


def test_submission_requires_teacher_and_meetings(client):
    login(client)
    assert post(client, "/api/classes/es-web/return", {"reason": "Revisão"}).status_code == 200
    assert post(client, "/api/entities/classes", {"record": {"id": "es-web", "teacher_emails": []}}).status_code == 200
    response = post(client, "/api/classes/es-web/submit")
    assert response.status_code == 400
    assert "professor" in response.get_json()["message"]


def test_coordinator_cannot_escalate_status_or_scope(client):
    login(client)
    post(client, "/api/classes/es-web/return", {"reason": "Revisão"})
    login(client, "coordinator")
    for record in ({"id": "es-web", "status": "approved"}, {"id": "es-web", "course_id": "administration"}):
        assert post(client, "/api/entities/classes", {"record": record}).status_code == 403
    assert post(client, "/api/entities/users", {"record": {"id": "demo-coordinator", "role": "admin"}}).status_code == 403


def test_stale_revision_rolls_back(client):
    login(client)
    revision = bootstrap(client)["revision"]
    assert post(client, "/api/entities/rooms", {"record": {"id": "a101", "name": "Primeira alteração"}}, revision).status_code == 200
    assert post(client, "/api/entities/rooms", {"record": {"id": "a101", "name": "Sobrescrita indevida"}}, revision).status_code == 409
    assert next(r for r in bootstrap(client)["rooms"] if r["id"] == "a101")["name"] == "Primeira alteração"


def test_unpublished_metadata_does_not_leak_to_student(client):
    login(client)
    assert post(client, "/api/entities/rooms", {"record": {"id": "a101", "name": "RASCUNHO SECRETO"}}).status_code == 200
    assert post(client, "/api/entities/classes", {"record": {"id": "es-alg", "name": "DISCIPLINA RASCUNHO"}}).status_code == 200
    login(client, "student")
    encoded = json.dumps(bootstrap(client), ensure_ascii=False)
    assert "RASCUNHO SECRETO" not in encoded and "DISCIPLINA RASCUNHO" not in encoded
    assert "Sala A101" in encoded


def test_no_published_version_has_no_draft_data(client):
    login(client)
    assert post(client, "/api/versions/demo-version-1/archive", {"reason": "Teste de ausência de publicação."}).status_code == 200
    login(client, "student")
    data = bootstrap(client)
    assert data["published_version"] is None
    assert data["classes"] == data["meetings"] == data["rooms"] == data["allocations"] == []


def test_real_core_validation_and_generation(app, client):
    require_core(app)
    login(client)
    result = post(client, "/api/validate", {"period_id": "2026-2"})
    assert result.status_code == 200, result.get_json()
    assert result.get_json()["valid"] is True
    generated = post(client, "/api/allocate", {"period_id": "2026-2"})
    assert generated.status_code == 200, generated.get_json()
    assert generated.get_json()["valid"] is True
    assert len(generated.get_json()["allocations"]) == 9


def test_publication_revalidates_changed_capacity_and_keeps_official(app, client):
    require_core(app)
    login(client)
    assert post(client, "/api/entities/rooms", {"record": {"id": "b101", "capacity": 18}}).status_code == 200
    published = post(client, "/api/publish", {"period_id": "2026-2", "description": "Não pode publicar"})
    assert published.status_code == 422, published.get_json()
    login(client, "student")
    data = bootstrap(client)
    assert data["published_version"]["number"] == 1
    assert next(r for r in data["rooms"] if r["id"] == "b101")["capacity"] == 36


def test_invalid_manual_move_rolls_back(app, client):
    require_core(app)
    login(client)
    before = bootstrap(client)
    result = post(client, "/api/move", {"meeting_id": "es-web-0", "room_id": "a201", "reason": "Teste de restrições"})
    assert result.status_code == 422, result.get_json()
    after = bootstrap(client)
    assert before["revision"] == after["revision"]
    assert before["allocations"] == after["allocations"]


def test_valid_manual_move_snapshot_revision_and_change_highlight(app, client):
    require_core(app)
    login(client)
    moved = post(client, "/api/move", {"meeting_id": "es-web-0", "room_id": "b102", "reason": "Aula prática em laboratório maior.", "locked": True})
    assert moved.status_code == 200, moved.get_json()
    login(client, "student")
    assert next(a for a in bootstrap(client)["allocations"] if a["meeting_id"] == "es-web-0")["room_id"] == "b101"
    login(client)
    differences = client.get("/api/compare?period_id=2026-2").get_json()["changes"]
    assert any(c["meeting_id"] == "es-web-0" for c in differences)
    published = post(client, "/api/publish", {"period_id": "2026-2", "description": "Laboratório ampliado", "reason": "Atividade prática."})
    assert published.status_code == 200, published.get_json()
    assert published.get_json()["version"]["number"] == 2
    login(client, "student")
    data = bootstrap(client)
    assert next(a for a in data["allocations"] if a["meeting_id"] == "es-web-0")["room_id"] == "b102"
    schedule = client.get("/api/schedule?period_id=2026-2&class_id=es-web&date=2026-09-28&view=week").get_json()
    assert next(e for e in schedule["events"] if e["meeting_id"] == "es-web-0")["status"] == "changed"


def test_csv_invalid_preview_and_confirmation_are_atomic(client):
    login(client)
    data = bootstrap(client)
    source = "id,code,name,campus_id,building_id,capacity\nnew-1,N1,Nova sala,campus-centro,bloco-a,30\nnew-2,N2,Sala inválida,campus-centro,bloco-a,-2\n"
    response = post(client, "/api/import/preview", {"entity": "rooms", "csv": source})
    report = response.get_json()
    assert response.status_code == 200 and report["valid_count"] == 1
    assert report["errors"][0]["line"] == 3 and report["token"] is None
    assert len(bootstrap(client)["rooms"]) == len(data["rooms"])
    assert post(client, "/api/import/confirm", {"token": "forged-token"}).status_code == 400


def test_csv_valid_preview_confirmation_duplicates_and_replay(client):
    login(client)
    source = "id,code,name,campus_id,building_id,capacity\nnew-1,N1,Nova sala,campus-centro,bloco-a,30\n"
    report = post(client, "/api/import/preview", {"entity": "rooms", "csv": source}).get_json()
    assert report["errors"] == [] and report["token"]
    confirmed = post(client, "/api/import/confirm", {"token": report["token"]})
    assert confirmed.status_code == 200 and confirmed.get_json()["imported"] == 1
    again = post(client, "/api/import/confirm", {"token": report["token"]})
    assert again.status_code == 422
    duplicate = post(client, "/api/import/preview", {"entity": "rooms", "csv": source}).get_json()
    assert duplicate["duplicates"] and duplicate["errors"]


def test_csv_users_and_meetings_accept_typed_fields(client):
    login(client)
    source = "id,email,name,role,course_ids,active\nteacher-new,nova@example.edu,Docente sintético,teacher,software,true\n"
    report = post(client, "/api/import/preview", {"entity": "users", "csv": source}).get_json()
    assert not report["errors"], report
    assert report["records"][0]["active"] is True
    source = "id,class_id,weekday,start,end\nnew-meeting,es-web,4,08:00,09:30\n"
    report = post(client, "/api/import/preview", {"entity": "meetings", "csv": source}).get_json()
    assert not report["errors"], report
    assert report["records"][0]["start_date"] == "2026-08-03"


def test_schedule_exceptions_and_ics(app, client):
    require_core(app)
    login(client)
    assert post(client, "/api/entities/meetings", {"record": {"id": "es-web-0", "excluded_dates": ["2026-09-28"]}}).status_code == 200
    assert post(client, "/api/publish", {"period_id": "2026-2", "description": "Feriado demonstrativo"}).status_code == 200
    login(client, "student")
    result = client.get("/api/schedule?period_id=2026-2&class_id=es-web&date=2026-09-28&view=week").get_json()
    assert len(result["events"]) == 1
    ics = client.get("/api/calendar.ics?period_id=2026-2&class_id=es-web&date=2026-09-28&view=week")
    assert ics.status_code == 200
    assert "BEGIN:VCALENDAR" in ics.get_data(as_text=True)
    assert "DTSTART:20260930T220000Z" in ics.get_data(as_text=True)
    assert all(len(line) <= 75 for line in ics.data.split(b"\r\n"))


def test_seed_refuses_to_overwrite_and_backup_restores(app, tmp_path):
    runner = app.test_cli_runner()
    refusal = runner.invoke(args=["seed-demo"])
    assert refusal.exit_code != 0 and "não vazia" in refusal.output
    target = tmp_path / "backup.json"
    assert runner.invoke(args=["export-state", str(target)]).exit_code == 0
    assert runner.invoke(args=["export-state", str(target)]).exit_code != 0
    other = create_app({"TESTING": True, "APP_ENV": "development", "SECRET_KEY": "test" * 20,
                        "DATABASE_URL": "sqlite:///" + str(tmp_path / "restore.sqlite3"), "ADMIN_EMAILS": [],
                        "GOOGLE_CLIENT_ID": "", "MICROSOFT_CLIENT_ID": "", "MICROSOFT_CLIENT_SECRET": ""})
    restored = other.test_cli_runner().invoke(args=["restore-state", str(target)])
    assert restored.exit_code == 0, restored.output
    assert other.extensions["store"].read()[1]["versions"] == app.extensions["store"].read()[1]["versions"]


def test_production_fails_closed_without_secret_or_postgres(tmp_path):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"APP_ENV": "production", "SECRET_KEY": "", "DATABASE_URL": "sqlite:///" + str(tmp_path / "bad.db")})
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        create_app({"APP_ENV": "production", "SECRET_KEY": "long-secret" * 6, "DATABASE_URL": "sqlite:///" + str(tmp_path / "bad.db")})


def test_auth_providers_unconfigured_fail_without_password_fallback(client):
    assert client.get("/auth/google").status_code == 503
    assert client.get("/auth/microsoft").status_code == 503
    assert client.post("/api/login", json={"password": "irrelevant"}).status_code in (401, 404)


def test_revocation_changes_permissions_on_existing_session(app, client):
    login(client, "student")
    def deactivate(state):
        next(u for u in state["users"] if u["id"] == "demo-student")["active"] = False
    app.extensions["store"].update(None, deactivate)
    assert client.get("/api/bootstrap").status_code == 401
