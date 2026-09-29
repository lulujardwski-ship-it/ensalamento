"""Validação de cadastros e projeções; nunca substitui o algoritmo em C++."""
import copy
import re
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from .store import ENTITIES


class ApiError(Exception):
    def __init__(self, message, status=400, code="validation_error", details=None):
        super().__init__(message)
        self.status, self.code, self.details = status, code, details


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid(prefix=""):
    return prefix + uuid4().hex[:16]


def get_record(state, entity, ident):
    return next((r for r in state[entity] if r["id"] == ident), None)


def require_record(state, entity, ident):
    record = get_record(state, entity, ident)
    if record is None:
        raise ApiError(f"Registro não encontrado em {entity}: {ident}.", 404, "not_found")
    return record


def audit(state, actor, action, entity, ident, reason, before=None, after=None):
    state["audit"].append({"id": uid("a_"), "at": now(), "actor": actor["email"],
                           "action": action, "entity": entity, "record_id": ident,
                           "reason": reason, "before": copy.deepcopy(before),
                           "after": copy.deepcopy(after)})


def text_field(value, label, required=True, limit=200):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ApiError(f"{label}: informe texto válido com até {limit} caracteres.")
    return value.strip()


def integer(value, label, minimum=0, maximum=100000):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ApiError(f"{label}: informe um inteiro entre {minimum} e {maximum}.")
    return value


def date_field(value, label):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        parsed = date.fromisoformat(value)
        if not 1970 <= parsed.year <= 2100:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise ApiError(f"{label}: use uma data válida no formato AAAA-MM-DD.") from None


def time_field(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ApiError(f"{label}: use horário válido HH:MM.")
    return value


def strings(value, label):
    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(v, str) or not v.strip() or len(v) > 254 for v in value):
        raise ApiError(f"{label}: informe uma lista de textos não vazios.")
    return list(dict.fromkeys(v.strip() for v in value))


def email(value):
    value = text_field(value, "E-mail", limit=254).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ApiError("Informe um e-mail válido.")
    return value


FIELDS = {
    "periods": {"id", "code", "name", "start_date", "end_date", "submission_deadline", "active"},
    "campuses": {"id", "code", "name", "address", "directions", "active"},
    "buildings": {"id", "code", "name", "campus_id", "directions", "block", "active"},
    "resources": {"id", "code", "name", "active"},
    "courses": {"id", "code", "name", "campus_id", "active"},
    "subjects": {"id", "code", "name", "course_id", "active"},
    "rooms": {"id", "code", "name", "campus_id", "building_id", "floor", "capacity", "exam_capacity", "type", "resources", "accessible", "status", "available", "unavailable", "directions"},
    "users": {"id", "email", "name", "role", "course_ids", "active"},
    "classes": {"id", "code", "name", "course_id", "subject_id", "period_id", "size_expected", "size_confirmed", "teacher_emails", "campus_id", "required_resources", "preferred_resources", "needs_accessibility", "preferred_building_id", "special_justification", "shift", "status", "review_note"},
    "meetings": {"id", "class_id", "weekday", "start", "end", "date", "start_date", "end_date", "excluded_dates"},
}


def validate_record(state, entity, supplied, existing=None):
    if entity not in ENTITIES:
        raise ApiError("Tipo de cadastro desconhecido.", 404)
    if not isinstance(supplied, dict):
        raise ApiError("O campo record deve ser um objeto JSON.")
    unknown = set(supplied) - FIELDS[entity]
    if unknown:
        raise ApiError("Campos desconhecidos: " + ", ".join(sorted(unknown)))
    record = {**(existing or {}), **copy.deepcopy(supplied)}
    record["id"] = text_field(record.get("id") or uid(entity[:2] + "_"), "Identificador", limit=100)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", record["id"]):
        raise ApiError("Identificador deve conter somente letras, números, ponto, hífen e sublinhado.")
    if entity not in ("users", "meetings"):
        record["code"] = text_field(record.get("code", record["id"]), "Código", limit=100)
        record["name"] = text_field(record.get("name"), "Nome")
        contexts = {"buildings": ("campus_id",), "rooms": ("building_id",),
                    "subjects": ("course_id",), "classes": ("period_id", "course_id")}.get(entity, ())
        if any(r["id"] != record["id"] and r.get("code", "").casefold() == record["code"].casefold() and
               all(r.get(c) == record.get(c) for c in contexts) for r in state[entity]):
            raise ApiError("Código duplicado no mesmo contexto.")
    for field in ("active", "accessible", "needs_accessibility"):
        if field in record and not isinstance(record[field], bool):
            raise ApiError(f"{field}: use true ou false.")
    references = {"campus_id": "campuses", "building_id": "buildings", "course_id": "courses",
                  "subject_id": "subjects", "period_id": "periods", "class_id": "classes",
                  "preferred_building_id": "buildings"}
    for field, target in references.items():
        if record.get(field):
            require_record(state, target, record[field])
    required_refs = {"buildings": ("campus_id",), "courses": ("campus_id",),
                     "subjects": ("course_id",), "rooms": ("campus_id", "building_id"),
                     "classes": ("course_id", "period_id", "campus_id"), "meetings": ("class_id",)}
    for field in required_refs.get(entity, ()):
        if not record.get(field):
            raise ApiError(f"{field}: selecione um registro existente.")
    for field in ("directions", "address", "special_justification", "review_note"):
        if field in record:
            record[field] = text_field(record[field], field, required=False, limit=3000)
    if entity == "periods":
        start = date_field(record.get("start_date"), "Início do período")
        end = date_field(record.get("end_date"), "Fim do período")
        if end < start or (end - start).days > 730:
            raise ApiError("O período deve durar entre 1 e 731 dias.")
        if record.get("submission_deadline"):
            date_field(record["submission_deadline"], "Prazo de envio")
        record.setdefault("active", True)
    elif entity == "users":
        record["email"] = email(record.get("email"))
        record["name"] = text_field(record.get("name"), "Nome")
        if record.get("role") not in ("admin", "coordinator", "teacher", "student"):
            raise ApiError("Papel inválido.")
        record["course_ids"] = strings(record.get("course_ids", []), "Cursos")
        for course in record["course_ids"]:
            require_record(state, "courses", course)
        record.setdefault("active", True)
        if any(r["id"] != record["id"] and r["email"] == record["email"] for r in state["users"]):
            raise ApiError("E-mail já cadastrado.")
    elif entity == "rooms":
        integer(record.get("capacity"), "Capacidade", 1)
        if record.get("exam_capacity") is not None:
            integer(record["exam_capacity"], "Capacidade para avaliações", 1, record["capacity"])
        record["resources"] = strings(record.get("resources", []), "Recursos")
        for resource in record["resources"]:
            require_record(state, "resources", resource)
        if require_record(state, "buildings", record["building_id"])["campus_id"] != record["campus_id"]:
            raise ApiError("O prédio não pertence ao campus informado.")
        record.setdefault("accessible", False)
        record.setdefault("floor", "Térreo")
        record["floor"] = str(record["floor"])
        record.setdefault("status", "active")
        if record["status"] not in ("active", "maintenance", "inactive"):
            raise ApiError("Estado da sala inválido.")
        for availability_field in ("available", "unavailable"):
            record.setdefault(availability_field, [])
            if not isinstance(record[availability_field], list) or len(record[availability_field]) > 1000:
                raise ApiError("Disponibilidades devem ser uma lista de até 1000 intervalos.")
            for interval in record[availability_field]:
                if not isinstance(interval, dict):
                    raise ApiError("Intervalo de disponibilidade inválido.")
                if interval.get("date"):
                    date_field(interval["date"], "Data da disponibilidade")
                else:
                    integer(interval.get("weekday"), "Dia da disponibilidade", 0, 6)
                    first = date_field(interval.get("start_date"), "Início da recorrência de disponibilidade")
                    last = date_field(interval.get("end_date"), "Fim da recorrência de disponibilidade")
                    if first > last:
                        raise ApiError("Datas da disponibilidade invertidas.")
                start = time_field(interval.get("start"), "Início da disponibilidade")
                end = time_field(interval.get("end"), "Fim da disponibilidade")
                if end <= start:
                    raise ApiError("Fim da disponibilidade deve ser posterior ao início.")
    elif entity == "classes":
        integer(record.get("size_expected"), "Quantidade prevista", 1)
        if record.get("size_confirmed") is not None:
            integer(record["size_confirmed"], "Quantidade confirmada", 1)
        record.setdefault("size_confirmed", None)
        record["teacher_emails"] = [email(v) for v in strings(record.get("teacher_emails", []), "Professores")]
        for field in ("required_resources", "preferred_resources"):
            record[field] = strings(record.get(field, []), field)
            for resource in record[field]:
                require_record(state, "resources", resource)
        record.setdefault("needs_accessibility", False)
        record.setdefault("status", "draft")
        if record["status"] not in ("draft", "submitted", "in_review", "approved", "cancelled", "closed"):
            raise ApiError("Estado da turma inválido.")
        if record.get("subject_id") and require_record(state, "subjects", record["subject_id"])["course_id"] != record["course_id"]:
            raise ApiError("Disciplina não pertence ao curso informado.")
    elif entity == "meetings":
        klass = require_record(state, "classes", record["class_id"])
        period = require_record(state, "periods", klass["period_id"])
        start = time_field(record.get("start"), "Início do encontro")
        end = time_field(record.get("end"), "Fim do encontro")
        if end <= start:
            raise ApiError("Fim do encontro deve ser posterior ao início; divida encontros que atravessem meia-noite.")
        record.setdefault("date", None)
        record.setdefault("start_date", period["start_date"])
        record.setdefault("end_date", period["end_date"])
        first = date_field(record["start_date"], "Início da recorrência")
        last = date_field(record["end_date"], "Fim da recorrência")
        if first > last or first < date.fromisoformat(period["start_date"]) or last > date.fromisoformat(period["end_date"]):
            raise ApiError("Recorrência deve estar dentro do período letivo.")
        if record["date"]:
            exact = date_field(record["date"], "Data excepcional")
            if not first <= exact <= last:
                raise ApiError("Data excepcional fora da validade do encontro.")
            record["weekday"] = exact.weekday()
        else:
            integer(record.get("weekday"), "Dia da semana", 0, 6)
        record["excluded_dates"] = strings(record.get("excluded_dates", []), "Datas excluídas")
        for exception in record["excluded_dates"]:
            date_field(exception, "Data excluída")
    return record


def put_record(state, entity, record):
    for index, old in enumerate(state[entity]):
        if old["id"] == record["id"]:
            state[entity][index] = record
            return
    state[entity].append(record)


def snapshot(state, period_id):
    classes = [copy.deepcopy(r) for r in state["classes"] if r["period_id"] == period_id and r["status"] not in ("cancelled", "closed")]
    class_ids = {r["id"] for r in classes}
    meetings = [copy.deepcopy(r) for r in state["meetings"] if r["class_id"] in class_ids]
    meeting_ids = {m["id"] for m in meetings}
    teacher_emails = {email for c in classes for email in c["teacher_emails"]}
    return {"periods": [copy.deepcopy(require_record(state, "periods", period_id))],
            **{key: copy.deepcopy(state[key]) for key in ("campuses", "buildings", "resources", "courses", "subjects", "rooms")},
            "classes": classes, "meetings": meetings,
            "teachers": [{key: u[key] for key in ("id", "name", "email")} for u in state["users"] if u["email"] in teacher_emails],
            "allocations": [copy.deepcopy(a) for a in state["allocations"] if a["meeting_id"] in meeting_ids]}


def active_version(state, period_id):
    ident = state["active_versions"].get(period_id)
    return next((v for v in state["versions"] if v["id"] == ident), None)


def version_meta(version):
    return {k: copy.deepcopy(v) for k, v in version.items() if k != "snapshot"} if version else None


def compare(state, period_id):
    prior = active_version(state, period_id)
    before = prior["snapshot"] if prior else {"allocations": [], "classes": [], "meetings": [], "rooms": []}
    after = snapshot(state, period_id)
    def index_rows(data):
        allocations = {a["meeting_id"]: a for a in data["allocations"]}
        classes = {c["id"]: c for c in data["classes"]}
        rooms = {r["id"]: r for r in data["rooms"]}
        return {m["id"]: {"meeting": m, "class": classes.get(m["class_id"]),
                          "allocation": allocations.get(m["id"]),
                          "room": rooms.get(allocations.get(m["id"], {}).get("room_id"))}
                for m in data["meetings"]}
    old, new = index_rows(before), index_rows(after)
    changes = []
    for ident in sorted(set(old) | set(new)):
        if old.get(ident) != new.get(ident):
            changes.append({"meeting_id": ident, "before": old.get(ident), "after": new.get(ident),
                            "kind": "added" if ident not in old else "removed" if ident not in new else "changed"})
    return changes


def occurs(meeting, day):
    iso = day.isoformat()
    if iso in meeting.get("excluded_dates", []):
        return False
    if not meeting["start_date"] <= iso <= meeting["end_date"]:
        return False
    return meeting.get("date") == iso if meeting.get("date") else meeting["weekday"] == day.weekday()
