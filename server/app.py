"""Aplicação Flask. Run: python -m server.app; produção: gunicorn server.app:create_app()."""
import copy
import csv
import io
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import subprocess
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import click
from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, g, jsonify, redirect, request, send_from_directory, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

from .domain import (ApiError, active_version, audit, compare, date_field, email,
                     get_record, now, occurs, put_record, require_record, snapshot,
                     text_field, uid, validate_record, version_meta)
from .store import ENTITIES, StaleRevision, Store, empty_state

ROOT = Path(__file__).resolve().parent.parent
ROLES = {"admin", "coordinator", "teacher", "student"}


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("true", "1", "yes")


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    environment = os.getenv("APP_ENV", "development")
    app.config.update(
        APP_ENV=environment,
        SECRET_KEY=os.getenv("SECRET_KEY", "") or (secrets.token_hex(32) if environment != "production" else ""),
        DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///" + str(ROOT / "instance" / "ensalamento.sqlite3")),
        FRONTEND_URL=os.getenv("FRONTEND_URL", ""),
        ALLOWED_DOMAINS=[s.strip().lower() for s in os.getenv("ALLOWED_DOMAINS", "").split(",") if s.strip()],
        ADMIN_EMAILS=[s.strip().lower() for s in os.getenv("ADMIN_EMAILS", "").split(",") if s.strip()],
        DEV_LOGIN_ENABLED=env_bool("DEV_LOGIN_ENABLED"),
        CORE_BINARY=os.getenv("CORE_BINARY", str(ROOT / "core" / ("ensalamento-core.exe" if os.name == "nt" else "ensalamento-core"))),
        GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID", ""), GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        MICROSOFT_CLIENT_ID=os.getenv("MICROSOFT_CLIENT_ID", ""), MICROSOFT_CLIENT_SECRET=os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        MICROSOFT_TENANT_ID=os.getenv("MICROSOFT_TENANT_ID", ""),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=environment == "production",
        SESSION_COOKIE_SAMESITE="None" if environment == "production" else "Lax",
        SESSION_COOKIE_NAME="__Host-ensalamento" if environment == "production" else "ensalamento_session",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if config:
        app.config.update(config)
    production = app.config["APP_ENV"] == "production"
    if production:
        if len(app.config["SECRET_KEY"]) < 32:
            raise RuntimeError("SECRET_KEY com no mínimo 32 caracteres é obrigatória em produção.")
        if not app.config["DATABASE_URL"].startswith(("postgresql://", "postgres://")):
            raise RuntimeError("PostgreSQL gerenciado é obrigatório em produção; SQLite é apenas desenvolvimento.")
        if app.config["DEV_LOGIN_ENABLED"]:
            raise RuntimeError("DEV_LOGIN_ENABLED não pode ser ativado em produção.")
        app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_NAME="__Host-ensalamento", SESSION_COOKIE_SAMESITE="None")
    if not production:
        app.logger.warning("Modo desenvolvimento: SQLite e login fictício, quando habilitado, não representam implantação institucional.")
    store = Store(app.config["DATABASE_URL"])
    app.extensions["store"] = store
    signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="csv-preview-v1")
    oauth = OAuth(app)
    if app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]:
        oauth.register("google", client_id=app.config["GOOGLE_CLIENT_ID"], client_secret=app.config["GOOGLE_CLIENT_SECRET"],
                       server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                       client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"})
    tenant = app.config["MICROSOFT_TENANT_ID"]
    if app.config["MICROSOFT_CLIENT_ID"] or app.config["MICROSOFT_CLIENT_SECRET"]:
        if not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", tenant):
            raise RuntimeError("Microsoft exige MICROSOFT_TENANT_ID UUID específico; common e consumers não são aceitos.")
        if not app.config["MICROSOFT_CLIENT_ID"] or not app.config["MICROSOFT_CLIENT_SECRET"]:
            raise RuntimeError("Configure ambas as credenciais Microsoft.")
        oauth.register("microsoft", client_id=app.config["MICROSOFT_CLIENT_ID"], client_secret=app.config["MICROSOFT_CLIENT_SECRET"],
                       server_metadata_url=f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
                       client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"})

    if app.config["ADMIN_EMAILS"]:
        _, initial = store.read()
        missing = [address for address in app.config["ADMIN_EMAILS"] if not any(u["email"] == address for u in initial["users"])]
        if missing:
            def add_admins(state):
                for address in missing:
                    if not any(u["email"] == address for u in state["users"]):
                        state["users"].append({"id": uid("u_"), "email": email(address), "name": address.split("@")[0],
                                               "role": "admin", "course_ids": [], "active": True})
            store.update(None, add_admins)

    def current_user(state=None):
        if state is None:
            state = g.state if hasattr(g, "state") else store.read()[1]
        user = get_record(state, "users", session.get("user_id"))
        return user if user and user.get("active", True) else None

    def public_user(user):
        return {key: copy.deepcopy(user.get(key)) for key in ("id", "email", "name", "role", "course_ids")} if user else None

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    def origin_allowed():
        origin = request.headers.get("Origin")
        if not origin:
            return True
        permitted = {request.host_url.rstrip("/")}
        if app.config["FRONTEND_URL"]:
            parsed = urlsplit(app.config["FRONTEND_URL"])
            permitted.add(f"{parsed.scheme}://{parsed.netloc}")
        return origin in permitted

    def is_local():
        try:
            return (ipaddress.ip_address(request.remote_addr or "").is_loopback and
                    urlsplit(request.host_url).hostname in ("localhost", "127.0.0.1", "::1"))
        except ValueError:
            return False

    def dev_available():
        return not production and bool(app.config["DEV_LOGIN_ENABLED"]) and is_local()

    @app.before_request
    def security_checks():
        if request.path.startswith("/api/"):
            if not origin_allowed():
                raise ApiError("Origem não autorizada.", 403, "origin_denied")
            if request.method == "OPTIONS":
                return Response(status=204)
            g.revision, g.state = store.read()
            g.user = current_user(g.state)
            if request.path not in ("/api/session", "/api/health", "/api/dev-login"):
                if not g.user:
                    raise ApiError("Entre com uma conta autorizada para continuar.", 401, "authentication_required")
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    supplied = request.headers.get("X-CSRF-Token", "")
                    if not supplied or not secrets.compare_digest(supplied, session.get("csrf_token", "")):
                        raise ApiError("Sessão de formulário expirada. Atualize a página e tente novamente.", 403, "csrf_failed")

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["X-Frame-Options"] = "DENY"
        if production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith(("/api/", "/auth/")):
            response.headers["Cache-Control"] = "no-store"
        if request.headers.get("Origin") and origin_allowed():
            response.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token, If-Match"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers.add("Vary", "Origin")
        return response

    @app.errorhandler(ApiError)
    def api_error(exc):
        body = {"error": exc.code, "message": str(exc)}
        if exc.details is not None:
            body["details"] = exc.details
        return jsonify(body), exc.status

    @app.errorhandler(StaleRevision)
    def stale_error(exc):
        return jsonify(error="stale_revision", message=str(exc)), 409

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error="http_error", message="Solicitação inválida ou endereço inexistente.", status=exc.code), exc.code

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        app.logger.error("Erro não tratado: %s", type(exc).__name__)
        if app.testing:
            raise exc
        return jsonify(error="internal_error", message="Não foi possível concluir. Tente novamente; se persistir, contate a administração."), 500

    def require_role(*roles):
        def decorator(func):
            @wraps(func)
            def wrapped(*args, **kwargs):
                if not g.user or g.user["role"] not in roles:
                    raise ApiError("Seu perfil não tem permissão para esta operação.", 403, "forbidden")
                return func(*args, **kwargs)
            return wrapped
        return decorator

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ApiError("Envie um objeto JSON válido.")
        return data

    def mutate(data, change):
        revision = data.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ApiError("Atualize os dados antes de salvar; revision é obrigatória.", 428, "revision_required")
        user_id = g.user["id"]
        original_role = g.user["role"]
        def checked(state):
            user = get_record(state, "users", user_id)
            if not user or not user.get("active", True) or user["role"] != original_role:
                raise ApiError("Suas permissões mudaram. Entre novamente.", 403)
            g.user = user
            return change(state)
        revision, result = store.update(revision, checked)
        return jsonify(**(result or {}), revision=revision)

    def preferred_period(state, periods):
        today = datetime.now(ZoneInfo(state["settings"]["timezone"])).date().isoformat()
        candidates = [p for p in periods if p.get("active", True)] or periods
        current = [p for p in candidates if p["start_date"] <= today <= p["end_date"]]
        past = [p for p in candidates if p["start_date"] <= today]
        if current or past:
            return max(current or past, key=lambda p: p["start_date"])["id"]
        return min(candidates, key=lambda p: p["start_date"])["id"] if candidates else None

    def period_for(state, requested=None):
        if requested:
            require_record(state, "periods", requested)
            return requested
        return preferred_period(state, state["periods"])

    def can_edit_class(state, klass):
        if g.user["role"] == "admin":
            return
        if g.user["role"] != "coordinator" or klass.get("course_id") not in g.user.get("course_ids", []):
            raise ApiError("A turma não pertence aos cursos sob sua responsabilidade.", 403, "scope_denied")
        if klass.get("status", "draft") not in ("draft", "in_review"):
            raise ApiError("Solicitação bloqueada. Aguarde a devolução ou reabertura pela administração.", 409, "request_locked")
        period = require_record(state, "periods", klass["period_id"])
        today = datetime.now(ZoneInfo(state["settings"]["timezone"])).date().isoformat()
        if not period.get("active", True) or (period.get("submission_deadline") and today > period["submission_deadline"]):
            raise ApiError("O período não está aceitando envios. Solicite reabertura à administração.", 409)

    def check_submission(state, klass):
        validate_record(state, "classes", klass, klass)
        teachers = [u["email"] for u in state["users"] if u["role"] in ("teacher", "admin", "coordinator") and u.get("active", True)]
        if not klass["teacher_emails"] or any(address not in teachers for address in klass["teacher_emails"]):
            raise ApiError("Cadastre e vincule ao menos um professor autorizado antes do envio.")
        meetings = [m for m in state["meetings"] if m["class_id"] == klass["id"]]
        if not meetings:
            raise ApiError("Cadastre ao menos um encontro antes de enviar a turma.")
        for meeting in meetings:
            validate_record(state, "meetings", meeting, meeting)
        special = klass["required_resources"] or klass["preferred_resources"] or klass["needs_accessibility"] or klass.get("preferred_building_id")
        if special and not klass.get("special_justification", "").strip():
            raise ApiError("Justifique as necessidades especiais e preferências da turma.")

    def core(state, mode, **extra):
        requested = extra.pop("period_id", None)
        selected_classes = [copy.deepcopy(c) for c in state["classes"] if not requested or c["period_id"] == requested]
        class_ids = {c["id"] for c in selected_classes}
        meetings = [copy.deepcopy(m) for m in state["meetings"] if m["class_id"] in class_ids]
        meeting_ids = {m["id"] for m in meetings}
        allocations = [copy.deepcopy(a) for a in state["allocations"] if a["meeting_id"] in meeting_ids]
        # Datas de períodos diferentes podem se sobrepor. Publicações dos demais
        # períodos são ocupações fixas, nunca rascunhos editáveis desta operação.
        if requested:
            for other_period, version_id in state["active_versions"].items():
                if other_period == requested:
                    continue
                official = next(v for v in state["versions"] if v["id"] == version_id)["snapshot"]
                selected_classes.extend(copy.deepcopy(official["classes"]))
                meetings.extend(copy.deepcopy(official["meetings"]))
                allocations.extend({**copy.deepcopy(a), "locked": True} for a in official["allocations"])
        if mode == "allocate":
            selection = extra.get("selected_meeting_ids", sorted(meeting_ids))
            if any(ident not in meeting_ids for ident in selection):
                raise ApiError("Selecione somente encontros do período atual.")
            extra["selected_meeting_ids"] = selection
        payload = {"mode": mode, "rooms": state["rooms"], "classes": selected_classes,
                   "meetings": meetings, "allocations": allocations,
                   "weights": state["settings"]["weights"], **extra}
        binary = Path(app.config["CORE_BINARY"])
        if not binary.is_file():
            raise ApiError("Núcleo C++ indisponível. Compile o projeto ou configure CORE_BINARY.", 503, "core_unavailable")
        try:
            result = subprocess.run([str(binary)], input=json.dumps(payload, ensure_ascii=False), text=True,
                                    encoding="utf-8", capture_output=True, timeout=15, check=False)
        except (subprocess.TimeoutExpired, OSError):
            raise ApiError("O núcleo não concluiu a operação no prazo. Revise o volume de dados e tente novamente.", 503, "core_timeout") from None
        try:
            output = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise ApiError("O núcleo retornou uma resposta inválida.", 502, "core_failed") from None
        if result.returncode or not isinstance(output, dict):
            raise ApiError("O núcleo rejeitou os dados de entrada. Revise os cadastros.", 422, "core_input_invalid", output.get("errors", []) if isinstance(output, dict) else [])
        if requested:
            output["allocations"] = [a for a in output.get("allocations", []) if a["meeting_id"] in meeting_ids]
        return output

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", database="postgresql" if store.postgres else "sqlite-development",
                       core_available=Path(app.config["CORE_BINARY"]).is_file(), environment=app.config["APP_ENV"])

    def session_payload():
        return {"user": public_user(current_user()), "csrf_token": csrf_token(),
                "providers": {"google": bool(app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]),
                              "microsoft": bool(app.config["MICROSOFT_CLIENT_ID"] and app.config["MICROSOFT_CLIENT_SECRET"])},
                "demo_available": dev_available(), "environment": app.config["APP_ENV"]}

    @app.get("/api/session")
    def get_session():
        return jsonify(session_payload())

    @app.post("/api/dev-login")
    def dev_login():
        if not dev_available():
            raise ApiError("Login de demonstração disponível somente no desenvolvimento local explicitamente habilitado.", 403)
        role = body().get("role")
        if role not in ROLES:
            raise ApiError("Perfil de demonstração inválido.")
        user = next((u for u in g.state["users"] if u["id"] == "demo-" + role and u.get("active", True)), None)
        if not user or not g.state.get("demo_data"):
            raise ApiError("Dados fictícios ausentes. Execute flask --app server.app seed-demo em uma base vazia.", 409)
        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        return jsonify(session_payload())

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/auth/<provider>")
    def login(provider):
        if provider not in ("google", "microsoft"):
            raise ApiError("Provedor desconhecido.", 404)
        client = oauth.create_client(provider)
        if client is None:
            raise ApiError("Este provedor ainda não foi configurado. Contate a administração.", 503, "provider_unconfigured")
        if production and request.scheme != "https":
            raise ApiError("Autenticação exige HTTPS em produção. Configure o proxy da plataforma.", 400)
        callback = request.host_url.rstrip("/") + f"/auth/{provider}/callback"
        return client.authorize_redirect(callback, nonce=secrets.token_urlsafe(32), prompt="select_account")

    @app.get("/auth/<provider>/callback")
    def callback(provider):
        if provider not in ("google", "microsoft"):
            raise ApiError("Provedor desconhecido.", 404)
        client = oauth.create_client(provider)
        if client is None:
            raise ApiError("Provedor não configurado.", 503)
        try:
            token = client.authorize_access_token()
            claims = token.get("userinfo")
            if not claims or not claims.get("sub") or not claims.get("iss"):
                raise ValueError("missing_claims")
            if provider == "google":
                if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com") or claims.get("email_verified") is not True:
                    raise ValueError("unverified_identity")
                address = email(claims.get("email"))
            else:
                expected_issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
                if claims.get("iss", "").lower() != expected_issuer.lower() or claims.get("tid", "").lower() != tenant.lower():
                    raise ValueError("invalid_tenant")
                address = email(claims.get("email") or claims.get("preferred_username"))
        except Exception as exc:
            app.logger.warning("Falha OAuth %s: %s", provider, type(exc).__name__)
            raise ApiError("Não foi possível verificar sua identidade. Entre novamente pelo botão do provedor.", 401, "identity_unverified") from None
        def bind_identity(state):
            registered = next((u for u in state["users"] if u["email"] == address), None)
            allowed = registered is not None or address.rsplit("@", 1)[1] in app.config["ALLOWED_DOMAINS"]
            # Microsoft não garante email_verified: somente pré-cadastro explícito no tenant institucional.
            if provider == "microsoft" and claims.get("email_verified") is not True and registered is None:
                allowed = False
            if not allowed or (registered and not registered.get("active", True)):
                raise ApiError("Conta não autorizada. Solicite inclusão à administração da instituição.", 403, "account_denied")
            identity = next((i for i in state["identities"] if i["issuer"] == claims["iss"] and i["subject"] == claims["sub"]), None)
            if identity:
                user = require_record(state, "users", identity["user_id"])
                if not user.get("active", True) or user["email"] != address:
                    raise ApiError("A identidade mudou ou foi revogada. Solicite revisão do vínculo à administração.", 403)
                return user
            user = registered
            if user is None:
                user = {"id": uid("u_"), "email": address, "name": str(claims.get("name") or address)[:200],
                        "role": "student", "course_ids": [], "active": True}
                state["users"].append(user)
            state["identities"].append({"issuer": claims["iss"], "subject": claims["sub"], "user_id": user["id"]})
            audit(state, user, "identity_bound", "users", user["id"], "Vínculo federado verificado pelo provedor.", after={"provider": provider})
            return user
        _, user = store.update(None, bind_identity)
        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        csrf_token()
        return redirect(app.config["FRONTEND_URL"] or "/")

    def bootstrap_projection(state, user, period_id, published=False):
        role = user["role"]
        official = active_version(state, period_id) if period_id else None
        draft = role in ("admin", "coordinator") and not published
        result = {"mode": "draft" if draft else "published",
                  "settings": copy.deepcopy(state["settings"]), "published_version": version_meta(official),
                  "demo_data": state.get("demo_data", False), "period_id": period_id}
        if draft:
            result.update({entity: copy.deepcopy(state[entity]) for entity in ENTITIES})
            result["allocations"] = copy.deepcopy(state["allocations"])
            result["versions"] = [version_meta(v) for v in state["versions"] if not period_id or v["period_id"] == period_id]
            result["audit"] = copy.deepcopy(state["audit"][-500:][::-1]) if role == "admin" else []
            if role == "coordinator":
                scope = set(user.get("course_ids", []))
                result["courses"] = [c for c in result["courses"] if c["id"] in scope]
                result["subjects"] = [s for s in result["subjects"] if s["course_id"] in scope]
                result["classes"] = [c for c in result["classes"] if c["course_id"] in scope]
                classes = {c["id"] for c in result["classes"]}
                result["meetings"] = [m for m in result["meetings"] if m["class_id"] in classes]
                meetings = {m["id"] for m in result["meetings"]}
                result["allocations"] = [a for a in result["allocations"] if a["meeting_id"] in meetings]
                result["users"] = [public_user(u) for u in result["users"] if u["role"] == "teacher" and u.get("active", True)]
                # Metadados de versão não podem revelar mudanças de outros cursos.
                result["versions"] = [{**v, "changes": [c for c in v.get("changes", []) if c["meeting_id"] in meetings]} for v in result["versions"]]
                if result["published_version"]:
                    result["published_version"]["changes"] = [c for c in result["published_version"].get("changes", []) if c["meeting_id"] in meetings]
                result["published_allocations"] = [a for a in (official["snapshot"]["allocations"] if official else []) if a["meeting_id"] in meetings]
        else:
            public_periods = [copy.deepcopy(v["snapshot"]["periods"][0]) for v in state["versions"] if state["active_versions"].get(v["period_id"]) == v["id"]]
            result.update({entity: [] for entity in ENTITIES})
            result.update(allocations=[], versions=[], audit=[])
            if official:
                result.update(copy.deepcopy(official["snapshot"]))
                if role in ("teacher", "coordinator"):
                    if role == "teacher":
                        result["classes"] = [c for c in result["classes"] if user["email"] in c["teacher_emails"]]
                    else:
                        scope = set(user.get("course_ids", []))
                        result["courses"] = [c for c in result["courses"] if c["id"] in scope]
                        result["subjects"] = [s for s in result["subjects"] if s["course_id"] in scope]
                        result["classes"] = [c for c in result["classes"] if c["course_id"] in scope]
                    classes = {c["id"] for c in result["classes"]}
                    result["meetings"] = [m for m in result["meetings"] if m["class_id"] in classes]
                    meetings = {m["id"] for m in result["meetings"]}
                    result["allocations"] = [a for a in result["allocations"] if a["meeting_id"] in meetings]
                    result["published_version"]["changes"] = [c for c in result["published_version"].get("changes", []) if c["meeting_id"] in meetings]
            result["periods"] = public_periods
        visible_classes = {m["class_id"] for m in result["meetings"]}
        teacher_emails = {email for c in result["classes"] if c["id"] in visible_classes for email in c["teacher_emails"]}
        catalog = state["users"] if draft else result.get("teachers", [])
        result["teachers"] = [{key: u[key] for key in ("id", "name", "email")} for u in catalog if u["email"] in teacher_emails]
        return result

    @app.get("/api/bootstrap")
    def bootstrap():
        period_id = period_for(g.state, request.args.get("period_id"))
        published_view = request.args.get("view") == "published"
        if (g.user["role"] in ("student", "teacher") or published_view) and not request.args.get("period_id"):
            published = [p for p in g.state["periods"] if p["id"] in g.state["active_versions"]]
            if published:
                period_id = preferred_period(g.state, published)
        result = bootstrap_projection(g.state, g.user, period_id, published=published_view)
        return jsonify(**result, user=public_user(g.user), revision=g.revision, csrf_token=csrf_token())

    @app.post("/api/entities/<entity>")
    @require_role("admin", "coordinator")
    def save_entity(entity):
        data = body()
        supplied = data.get("record")
        if entity not in ENTITIES or not isinstance(supplied, dict):
            raise ApiError("Cadastro ou registro inválido.")
        def save(state):
            old = get_record(state, entity, supplied.get("id"))
            before = copy.deepcopy(old)
            if g.user["role"] == "coordinator":
                if entity not in ("classes", "meetings"):
                    raise ApiError("Coordenadores editam somente suas turmas e encontros.", 403)
                if entity == "classes":
                    if old is None:
                        raise ApiError("Solicite à administração o cadastro inicial da turma.", 403)
                    can_edit_class(state, old)
                    protected = {"course_id", "period_id", "status", "review_note", "id"}
                    if any(key in supplied and supplied[key] != old.get(key) for key in protected):
                        raise ApiError("Curso, período e estado são controlados pela administração.", 403)
                else:
                    klass = require_record(state, "classes", (old or supplied).get("class_id"))
                    can_edit_class(state, klass)
                    if old and supplied.get("class_id", old["class_id"]) != old["class_id"]:
                        raise ApiError("Não é permitido transferir encontros entre turmas.", 403)
            record = validate_record(state, entity, supplied, old)
            if entity == "users" and record["id"] == g.user["id"] and (record["role"] != "admin" or not record["active"]):
                raise ApiError("Não é permitido remover o próprio acesso administrativo.")
            put_record(state, entity, record)
            if entity == "classes" and record["status"] in ("cancelled", "closed"):
                meeting_ids = {m["id"] for m in state["meetings"] if m["class_id"] == record["id"]}
                state["allocations"] = [a for a in state["allocations"] if a["meeting_id"] not in meeting_ids]
            # Alterar cadastros não altera snapshots oficiais. Toda publicação revalida do zero.
            audit(state, g.user, "update" if old else "create", entity, record["id"],
                  data.get("reason") or "Cadastro revisado pela equipe responsável.", before, record)
            return {"record": record}
        return mutate(data, save)

    @app.delete("/api/entities/<entity>/<ident>")
    @require_role("admin", "coordinator")
    def delete_entity(entity, ident):
        data = body()
        reason = text_field(data.get("reason"), "Motivo", limit=3000)
        if entity not in ENTITIES:
            raise ApiError("Cadastro desconhecido.", 404)
        def remove(state):
            record = require_record(state, entity, ident)
            before = copy.deepcopy(record)
            if g.user["role"] == "coordinator":
                if entity != "meetings":
                    raise ApiError("Coordenadores podem remover somente encontros em revisão.", 403)
                can_edit_class(state, require_record(state, "classes", record["class_id"]))
            if entity == "users" and ident == g.user["id"]:
                raise ApiError("Não é permitido remover seu próprio acesso.")
            if entity == "meetings":
                state["meetings"] = [m for m in state["meetings"] if m["id"] != ident]
                state["allocations"] = [a for a in state["allocations"] if a["meeting_id"] != ident]
                after = None
            else:
                if entity == "classes":
                    record["status"] = "cancelled"
                    meetings = {m["id"] for m in state["meetings"] if m["class_id"] == ident}
                    state["allocations"] = [a for a in state["allocations"] if a["meeting_id"] not in meetings]
                elif entity == "rooms":
                    record["status"] = "inactive"
                else:
                    record["active"] = False
                after = record
            audit(state, g.user, "deactivate", entity, ident, reason, before, after)
            return {"record": after, "history_preserved": True}
        return mutate(data, remove)

    @app.post("/api/classes/<ident>/<action>")
    @require_role("admin", "coordinator")
    def transition_class(ident, action):
        data = body()
        if action not in ("submit", "return", "approve"):
            raise ApiError("Ação desconhecida.", 404)
        if action != "submit" and g.user["role"] != "admin":
            raise ApiError("Somente a administração aprova ou devolve solicitações.", 403)
        reason = text_field(data.get("reason"), "Justificativa de devolução", limit=3000) if action == "return" else data.get("reason") or ("Necessidades enviadas para análise." if action == "submit" else "Necessidades revisadas e aprovadas.")
        def transition(state):
            klass = require_record(state, "classes", ident)
            before = copy.deepcopy(klass)
            if action == "submit":
                can_edit_class(state, klass)
                check_submission(state, klass)
                klass["status"] = "submitted"
                klass["review_note"] = ""
            elif action == "return":
                klass["status"] = "in_review"
                klass["review_note"] = reason
            else:
                check_submission(state, klass)
                klass["status"] = "approved"
            audit(state, g.user, action, "classes", ident, reason, before, klass)
            return {"record": klass}
        return mutate(data, transition)

    def csv_preview(state, entity, source):
        if entity not in ENTITIES:
            raise ApiError("Cadastro de importação inválido.")
        if not isinstance(source, str) or len(source.encode("utf-8")) > 1024 * 1024:
            raise ApiError("Envie CSV com até 1 MiB.")
        source = source.lstrip("\ufeff")
        if not source.strip():
            raise ApiError("O arquivo CSV está vazio.")
        # Cabeçalhos separados por vírgula ou ponto-e-vírgula; listas devem estar entre aspas se necessário.
        try:
            dialect = csv.Sniffer().sniff(source[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(source), dialect=dialect)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ApiError("Cabeçalhos CSV ausentes ou duplicados.")
        working = copy.deepcopy(state)
        records, errors, duplicates, warnings = [], [], [], []
        list_fields = {"resources", "teacher_emails", "required_resources", "preferred_resources", "course_ids", "excluded_dates"}
        int_fields = {"capacity", "exam_capacity", "size_expected", "size_confirmed", "weekday"}
        bool_fields = {"active", "accessible", "needs_accessibility"}
        try:
            for line, row in enumerate(reader, 2):
                if line > 10001:
                    errors.append({"line": line, "field": "arquivo", "message": "Máximo de 10.000 registros por importação."})
                    break
                field = "registro"
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ApiError("Quantidade de colunas não corresponde ao cabeçalho.")
                    record = {}
                    for field, value in row.items():
                        value = value.strip()
                        if value == "":
                            if field in ("size_confirmed", "date"):
                                record[field] = None
                            continue
                        if field in list_fields:
                            record[field] = json.loads(value) if value.startswith("[") else [s.strip() for s in value.split(";") if s.strip()]
                        elif field in int_fields:
                            record[field] = int(value)
                        elif field in bool_fields:
                            if value.lower() not in ("true", "false", "1", "0", "sim", "nao", "não"):
                                raise ApiError("Booleano deve ser true/false ou sim/não.")
                            record[field] = value.lower() in ("true", "1", "sim")
                        elif field in ("available", "unavailable"):
                            record[field] = json.loads(value)
                        else:
                            record[field] = value
                    field = "registro"
                    if record.get("id") and get_record(working, entity, record["id"]):
                        duplicates.append({"line": line, "field": "id", "message": "Identificador já existe; importação não substitui registros."})
                        raise ApiError("Identificador duplicado.")
                    validated = validate_record(working, entity, record)
                    put_record(working, entity, validated)
                    records.append(validated)
                except (ApiError, ValueError, TypeError) as exc:
                    message = str(exc) if isinstance(exc, ApiError) else "Valor não corresponde ao tipo esperado."
                    if field == "registro":
                        labels = {"Identificador": "id", "Código": "code", "Nome": "name",
                                  "Capacidade para avaliações": "exam_capacity", "Capacidade": "capacity",
                                  "Quantidade prevista": "size_expected", "Quantidade confirmada": "size_confirmed",
                                  "E-mail": "email", "Professores": "teacher_emails", "Recursos": "resources",
                                  "Cursos": "course_ids", "Papel": "role", "Dia da semana": "weekday",
                                  "Início do período": "start_date", "Fim do período": "end_date",
                                  "Prazo de envio": "submission_deadline", "Início do encontro": "start",
                                  "Fim do encontro": "end", "Início da recorrência": "start_date",
                                  "Fim da recorrência": "end_date", "Data excepcional": "date",
                                  "Datas excluídas": "excluded_dates", "Data excluída": "excluded_dates"}
                        field = next((key for label, key in labels.items() if message.startswith(label)),
                                     message.split(":", 1)[0] if message.split(":", 1)[0] in record else "registro")
                    if "duplicado" in message.lower() and not any(d["line"] == line for d in duplicates):
                        duplicates.append({"line": line, "field": "code", "message": message})
                    errors.append({"line": line, "field": field, "message": message})
        except csv.Error:
            errors.append({"line": reader.line_num, "field": "arquivo", "message": "CSV malformado. Verifique aspas e separadores."})
        return {"valid_count": len(records), "errors": errors, "warnings": warnings, "duplicates": duplicates, "records": records}

    @app.post("/api/import/preview")
    @require_role("admin")
    def preview_import():
        data = body()
        report = csv_preview(g.state, data.get("entity"), data.get("csv"))
        report["token"] = signer.dumps({"entity": data["entity"], "csv": data["csv"], "user_id": g.user["id"]}) if not report["errors"] else None
        return jsonify(report)

    @app.post("/api/import/confirm")
    @require_role("admin")
    def confirm_import():
        data = body()
        try:
            payload = signer.loads(data.get("token", ""), max_age=900)
        except (BadSignature, SignatureExpired, TypeError):
            raise ApiError("Prévia ausente, alterada ou expirada. Gere uma nova prévia.", 400) from None
        if payload["user_id"] != g.user["id"]:
            raise ApiError("Prévia pertence a outro usuário.", 403)
        def commit_import(state):
            report = csv_preview(state, payload["entity"], payload["csv"])
            if report["errors"]:
                raise ApiError("Importação cancelada: corrija todos os erros da prévia.", 422, "import_invalid", report)
            for record in report["records"]:
                put_record(state, payload["entity"], record)
                audit(state, g.user, "import", payload["entity"], record["id"], data.get("reason") or "Importação CSV revisada e confirmada.", after=record)
            return {"imported": len(report["records"])}
        return mutate(data, commit_import)

    @app.post("/api/allocate")
    @require_role("admin")
    def allocate():
        data = body()
        def generate(state):
            period_id = period_for(state, data.get("period_id"))
            selection = data.get("selected_meeting_ids")
            if selection is not None and (not isinstance(selection, list) or any(not isinstance(v, str) for v in selection)):
                raise ApiError("Seleção de encontros inválida.")
            before = copy.deepcopy(state["allocations"])
            result = core(state, "allocate", period_id=period_id, **({"selected_meeting_ids": selection} if selection is not None else {}))
            class_ids = {c["id"] for c in state["classes"] if c["period_id"] == period_id}
            meeting_ids = {m["id"] for m in state["meetings"] if m["class_id"] in class_ids}
            state["allocations"] = [a for a in state["allocations"] if a["meeting_id"] not in meeting_ids] + result.get("allocations", [])
            audit(state, g.user, "allocate", "periods", period_id, data.get("reason") or "Proposta gerada pelo núcleo C++.", before, state["allocations"])
            return result
        return mutate(data, generate)

    @app.post("/api/validate")
    @require_role("admin")
    def validate():
        data = body()
        result = core(g.state, "validate", period_id=period_for(g.state, data.get("period_id")))
        return jsonify(**result, revision=g.revision)

    @app.get("/api/suggestions")
    @require_role("admin")
    def suggestions():
        meeting = require_record(g.state, "meetings", request.args.get("meeting_id"))
        klass = require_record(g.state, "classes", meeting["class_id"])
        return jsonify(core(g.state, "suggest", period_id=klass["period_id"], meeting_id=meeting["id"]))

    @app.post("/api/move")
    @require_role("admin")
    def move():
        data = body()
        reason = text_field(data.get("reason"), "Motivo da mudança", limit=3000)
        def move_allocation(state):
            meeting = require_record(state, "meetings", data.get("meeting_id"))
            klass = require_record(state, "classes", meeting["class_id"])
            require_record(state, "rooms", data.get("room_id"))
            options = core(state, "suggest", period_id=klass["period_id"], meeting_id=meeting["id"])
            suggestion = next((s for s in options.get("suggestions", []) if s["room_id"] == data["room_id"]), None)
            if suggestion is None:
                raise ApiError("Sala inválida para este encontro. Selecione uma das sugestões e revise os conflitos.", 422, "invalid_move", options)
            before = next((copy.deepcopy(a) for a in state["allocations"] if a["meeting_id"] == meeting["id"]), None)
            allocation = {**suggestion, "meeting_id": meeting["id"], "source": "manual", "locked": bool(data.get("locked", True)), "reason": reason}
            state["allocations"] = [a for a in state["allocations"] if a["meeting_id"] != meeting["id"]] + [allocation]
            result = core(state, "validate", period_id=klass["period_id"])
            related = [c for c in result.get("conflicts", []) if c.get("meeting_id") == meeting["id"]]
            if related:
                raise ApiError("A mudança foi rejeitada por conflito obrigatório.", 422, "invalid_move", related)
            audit(state, g.user, "move", "allocations", meeting["id"], reason, before, allocation)
            return {"allocation": allocation, "validation": result}
        return mutate(data, move_allocation)

    @app.post("/api/weights")
    @require_role("admin")
    def weights():
        data = body()
        supplied = data.get("weights")
        keys = {"capacity", "building", "resources", "stability"}
        if not isinstance(supplied, dict) or set(supplied) != keys or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 10000 for v in supplied.values()) or sum(supplied.values()) <= 0:
            raise ApiError("Informe os quatro pesos não negativos, com soma maior que zero (máximo 10.000 por peso).")
        def save_weights(state):
            before = copy.deepcopy(state["settings"]["weights"])
            state["settings"]["weights"] = supplied
            audit(state, g.user, "weights", "settings", "weights", data.get("reason") or "Ajuste dos critérios preferenciais de adequação.", before, supplied)
            return {"weights": supplied}
        return mutate(data, save_weights)

    @app.get("/api/compare")
    @require_role("admin")
    def get_compare():
        period_id = period_for(g.state, request.args.get("period_id"))
        if not period_id:
            raise ApiError("Cadastre um período letivo.")
        return jsonify(changes=compare(g.state, period_id), previous_version=version_meta(active_version(g.state, period_id)))

    @app.get("/api/versions")
    @require_role("admin", "coordinator")
    def get_versions():
        period_id = period_for(g.state, request.args.get("period_id"))
        projection = bootstrap_projection(g.state, g.user, period_id)
        return jsonify(versions=projection["versions"])

    @app.post("/api/publish")
    @require_role("admin")
    def publish():
        data = body()
        description = text_field(data.get("description"), "Descrição da versão", limit=500)
        reason = text_field(data.get("reason", description), "Motivo", limit=3000)
        def commit_publication(state):
            period_id = period_for(state, data.get("period_id"))
            if not period_id:
                raise ApiError("Cadastre e selecione um período letivo.")
            classes = [c for c in state["classes"] if c["period_id"] == period_id and c["status"] not in ("cancelled", "closed")]
            if not classes and not active_version(state, period_id):
                raise ApiError("O período não contém turmas ativas.")
            for klass in classes:
                check_submission(state, klass)
                if klass["status"] not in ("submitted", "approved"):
                    raise ApiError(f"A turma {klass['code']} deve ser enviada ou aprovada antes da publicação.")
            validation = core(state, "validate", period_id=period_id)
            if not validation.get("valid") or validation.get("conflicts") or validation.get("unallocated"):
                raise ApiError("Publicação bloqueada. Resolva todos os conflitos e encontros sem sala.", 422, "publication_blocked", validation)
            changes = compare(state, period_id)
            prior = active_version(state, period_id)
            number = 1 + max((v["number"] for v in state["versions"] if v["period_id"] == period_id), default=0)
            version = {"id": uid("v_"), "number": number, "period_id": period_id, "published_at": now(),
                       "published_by": g.user["email"], "description": description, "changes": changes,
                       "snapshot": snapshot(state, period_id)}
            state["versions"].append(version)
            state["active_versions"][period_id] = version["id"]
            audit(state, g.user, "publish", "versions", version["id"], reason,
                  version_meta(prior), version_meta(version))
            return {"version": version_meta(version)}
        return mutate(data, commit_publication)

    @app.post("/api/versions/<ident>/archive")
    @require_role("admin")
    def archive(ident):
        data = body()
        reason = text_field(data.get("reason"), "Motivo do arquivamento", limit=3000)
        def archive_version(state):
            version = next((v for v in state["versions"] if v["id"] == ident), None)
            if not version:
                raise ApiError("Versão não encontrada.", 404)
            if state["active_versions"].get(version["period_id"]) == ident:
                del state["active_versions"][version["period_id"]]
            audit(state, g.user, "archive", "versions", ident, reason, version_meta(version), {"active": False})
            return {"archived": ident}
        return mutate(data, archive_version)

    def schedule_payload():
        period_id = period_for(g.state, request.args.get("period_id"))
        official = active_version(g.state, period_id) if period_id else None
        zone = ZoneInfo(g.state["settings"]["timezone"])
        today = datetime.now(zone)
        day = date_field(request.args.get("date", today.date().isoformat()), "Data da agenda")
        view = request.args.get("view", "day")
        if view not in ("day", "week"):
            raise ApiError("Visão deve ser day ou week.")
        days = [day] if view == "day" else [day - timedelta(days=day.weekday()) + timedelta(days=i) for i in range(7)]
        result = {"events": [], "current": None, "next": None, "published_version": version_meta(official),
                  "date": day.isoformat(), "timezone": str(zone)}
        if not official:
            return result
        data = official["snapshot"]
        classes = {c["id"]: c for c in data["classes"]}
        if g.user["role"] == "teacher":
            classes = {i: c for i, c in classes.items() if g.user["email"] in c["teacher_emails"]}
        elif g.user["role"] == "coordinator":
            classes = {i: c for i, c in classes.items() if c["course_id"] in g.user.get("course_ids", [])}
        if request.args.get("class_id"):
            classes = {i: c for i, c in classes.items() if i == request.args["class_id"]}
        elif g.user["role"] == "student":
            return result
        rooms = {r["id"]: r for r in data["rooms"]}
        buildings = {r["id"]: r for r in data["buildings"]}
        campuses = {r["id"]: r for r in data["campuses"]}
        allocations = {a["meeting_id"]: a for a in data["allocations"]}
        changed = {c["meeting_id"] for c in official.get("changes", []) if c["kind"] == "changed"}
        for current_day in days:
            for meeting in data["meetings"]:
                if meeting["class_id"] not in classes or not occurs(meeting, current_day):
                    continue
                allocation = allocations.get(meeting["id"])
                if not allocation:
                    continue
                room = rooms[allocation["room_id"]]
                event = {"meeting_id": meeting["id"], "date": current_day.isoformat(), "start": meeting["start"], "end": meeting["end"],
                         "class": classes[meeting["class_id"]], "room": room, "building": buildings[room["building_id"]],
                         "campus": campuses[room["campus_id"]], "allocation": allocation,
                         "status": "changed" if meeting["id"] in changed else "confirmed", "updated_at": official["published_at"]}
                result["events"].append(event)
        result["events"].sort(key=lambda e: (e["date"], e["start"], e["class"]["code"]))
        time_now = today.strftime("%H:%M")
        result["current"] = next((e for e in result["events"] if e["date"] == today.date().isoformat() and e["start"] <= time_now < e["end"]), None)
        result["next"] = next((e for e in result["events"] if (e["date"], e["start"]) > (today.date().isoformat(), time_now)), None)
        # Changes from unrelated classes are not exposed through schedule metadata.
        visible = {e["meeting_id"] for e in result["events"]}
        result["published_version"]["changes"] = [c for c in result["published_version"].get("changes", []) if c["meeting_id"] in visible]
        return result

    @app.get("/api/schedule")
    def schedule():
        return jsonify(schedule_payload())

    @app.get("/api/calendar.ics")
    def calendar():
        payload = schedule_payload()
        def escape(value):
            return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,").replace("\r", "")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Ensalamento Academico//PT-BR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
        zone = ZoneInfo(payload["timezone"])
        stamp = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
        for event in payload["events"]:
            start = datetime.fromisoformat(event["date"] + "T" + event["start"]).replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
            end = datetime.fromisoformat(event["date"] + "T" + event["end"]).replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
            lines.extend(["BEGIN:VEVENT", f"UID:{event['meeting_id']}-{event['date']}@ensalamento.local", f"DTSTAMP:{stamp}",
                          f"DTSTART:{start}", f"DTEND:{end}", "SUMMARY:" + escape(event["class"]["name"]),
                          "LOCATION:" + escape(f"{event['campus']['name']}, {event['building']['name']}, {event['room']['name']}, {event['room']['floor']}"),
                          "DESCRIPTION:" + escape("Versão oficial " + str(payload["published_version"]["number"]) + ". " + event["room"].get("directions", "")), "END:VEVENT"])
        lines.append("END:VCALENDAR")
        # RFC 5545 folding: limit each physical line to 75 UTF-8 octets, preserving code points.
        folded = []
        for line in lines:
            part = ""
            for char in line:
                if len((part + char).encode("utf-8")) > 75:
                    folded.append(part)
                    part = " "
                part += char
            folded.append(part)
        return Response("\r\n".join(folded) + "\r\n", mimetype="text/calendar", headers={"Content-Disposition": 'attachment; filename="agenda.ics"'})

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Cria dados totalmente fictícios somente quando a base está vazia."""
        if production:
            raise click.ClickException("seed-demo é restrito ao ambiente de desenvolvimento.")
        from .seed import demo_state
        def seed(state):
            if any(state[key] for key in ("periods", "classes", "rooms", "versions")) or state["users"]:
                raise click.ClickException("Base não vazia: seed cancelado para preservar os dados existentes.")
            state.clear()
            state.update(demo_state())
        store.update(None, seed)
        click.echo("Dados fictícios criados. Use DEV_LOGIN_ENABLED=true somente em localhost.")

    @app.cli.command("export-state")
    @click.argument("destination", type=click.Path(path_type=Path))
    def export_state(destination):
        """Exporta backup; arquivo contém dados pessoais e deve ficar privado."""
        revision, state = store.read()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            json.dump({"format": "ensalamento-backup-v1", "exported_at": now(), "revision": revision, "state": state}, handle, ensure_ascii=False, indent=2)
        click.echo("Backup criado em " + str(destination))

    @app.cli.command("restore-state")
    @click.argument("source", type=click.Path(exists=True, path_type=Path))
    def restore_state(source):
        """Restaura backup somente em base vazia; nunca sobrescreve dados vivos."""
        with source.open(encoding="utf-8") as handle:
            backup = json.load(handle)
        if backup.get("format") != "ensalamento-backup-v1" or not isinstance(backup.get("state"), dict):
            raise click.ClickException("Formato de backup inválido.")
        restored = backup["state"]
        if set(empty_state()) - set(restored):
            raise click.ClickException("Backup incompleto.")
        def restore(state):
            if any(state[key] for key in ("periods", "users", "versions")):
                raise click.ClickException("Restauração requer uma base vazia; use outro DATABASE_URL.")
            state.clear()
            state.update(restored)
        store.update(None, restore)
        click.echo("Backup restaurado transacionalmente.")

    @app.get("/config.js")
    def dynamic_config():
        config_path = ROOT / "web" / "config.js"
        original = config_path.read_text(encoding="utf-8") if config_path.is_file() else "window.ENSALAMENTO_CONFIG={};"
        return Response(original + "\nwindow.ENSALAMENTO_CONFIG=Object.freeze({...window.ENSALAMENTO_CONFIG,API_BASE:window.location.origin});\n", mimetype="application/javascript", headers={"Cache-Control": "no-store"})

    @app.get("/")
    def index():
        return send_from_directory(ROOT / "web", "index.html")

    @app.get("/<path:filename>")
    def assets(filename):
        if filename.startswith(("api/", "auth/", ".")):
            raise ApiError("Endereço não encontrado.", 404)
        return send_from_directory(ROOT / "web", filename)

    # Render tem um único proxy confiável; habilitação explícita evita confiar em headers locais.
    if env_bool("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.getenv("PORT", "8000")), debug=False)
