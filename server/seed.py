"""Conjunto sintético. Nomes, contas, localização e capacidades são fictícios."""
import copy

from .domain import audit, now, snapshot
from .store import empty_state


def demo_state():
    state = empty_state()
    state["demo_data"] = True
    state["periods"] = [{"id": "2026-2", "code": "2026.2", "name": "2º semestre de 2026", "start_date": "2026-08-03", "end_date": "2026-12-18", "submission_deadline": "2026-12-01", "active": True}]
    state["campuses"] = [{"id": "campus-centro", "code": "CTR", "name": "Campus Centro (fictício)", "address": "Avenida do Conhecimento, 100 — endereço ilustrativo", "directions": "Entrada principal junto à praça central.", "active": True}]
    state["buildings"] = [
        {"id": "bloco-a", "code": "A", "name": "Bloco A · Ensino", "campus_id": "campus-centro", "directions": "À esquerda da entrada, após a biblioteca.", "active": True},
        {"id": "bloco-b", "code": "B", "name": "Bloco B · Tecnologia", "campus_id": "campus-centro", "directions": "Ao fundo do campus, caminho com piso tátil e rampa.", "active": True},
    ]
    state["resources"] = [{"id": "projector", "code": "PROJ", "name": "Projetor", "active": True}, {"id": "computers", "code": "PC", "name": "Computadores", "active": True}, {"id": "whiteboard", "code": "QUADRO", "name": "Quadro branco", "active": True}]
    state["courses"] = [{"id": "software", "code": "ES", "name": "Engenharia de Software", "campus_id": "campus-centro", "active": True}, {"id": "administration", "code": "ADM", "name": "Administração", "campus_id": "campus-centro", "active": True}]
    state["users"] = [
        {"id": "demo-admin", "email": "admin@example.edu", "name": "Administração · demonstração", "role": "admin", "course_ids": [], "active": True},
        {"id": "demo-coordinator", "email": "coordenacao@example.edu", "name": "Coordenação · demonstração", "role": "coordinator", "course_ids": ["software"], "active": True},
        {"id": "demo-teacher", "email": "professor@example.edu", "name": "Ana Exemplo · docente fictícia", "role": "teacher", "course_ids": ["software"], "active": True},
        {"id": "teacher-b", "email": "docente.b@example.edu", "name": "Bruno Exemplo · docente fictício", "role": "teacher", "course_ids": ["software", "administration"], "active": True},
        {"id": "teacher-c", "email": "docente.c@example.edu", "name": "Clara Exemplo · docente fictícia", "role": "teacher", "course_ids": ["administration"], "active": True},
        {"id": "demo-student", "email": "aluno@example.edu", "name": "Estudante · demonstração", "role": "student", "course_ids": [], "active": True},
    ]
    room_specs = [
        ("a101", "A101", "Sala A101", "bloco-a", "Térreo", 40, ["projector", "whiteboard"]),
        ("a102", "A102", "Sala A102", "bloco-a", "Térreo", 60, ["projector", "whiteboard"]),
        ("a201", "A201", "Sala A201", "bloco-a", "1º andar", 32, ["whiteboard"]),
        ("b101", "B101", "Laboratório B101", "bloco-b", "Térreo", 36, ["computers", "projector", "whiteboard"]),
        ("b102", "B102", "Laboratório B102", "bloco-b", "Térreo", 44, ["computers", "projector", "whiteboard"]),
        ("b201", "B201", "Sala B201", "bloco-b", "1º andar", 50, ["projector", "whiteboard"]),
    ]
    for ident, code, name, building, floor, capacity, resources in room_specs:
        state["rooms"].append({"id": ident, "code": code, "name": name, "campus_id": "campus-centro", "building_id": building,
                               "floor": floor, "capacity": capacity, "exam_capacity": capacity // 2,
                               "type": "laboratory" if "computers" in resources else "classroom", "resources": resources,
                               "accessible": ident != "a201", "status": "active", "available": [], "unavailable": [],
                               "directions": "Siga a sinalização do bloco. " + ("Acesso térreo, com rampa." if floor == "Térreo" else "Use a escada; consulte as condições de acessibilidade.")})
    class_specs = [
        ("es-web", "ES-WEB-4N", "Desenvolvimento Web", "software", 32, "professor@example.edu", ["computers"], "b101", [0, 2], "19:00", "20:40"),
        ("es-alg", "ES-ALG-2N", "Algoritmos e Estruturas de Dados", "software", 38, "professor@example.edu", ["projector"], "a101", [1, 3], "19:00", "20:40"),
        ("es-bd", "ES-BD-4N", "Banco de Dados", "software", 30, "docente.b@example.edu", ["computers"], "b101", [0, 2], "20:50", "22:30"),
        ("adm-gestao", "ADM-GES-2N", "Gestão de Organizações", "administration", 48, "docente.c@example.edu", ["projector"], "a102", [1, 3], "19:00", "20:40"),
        ("adm-etica", "ADM-ETI-2N", "Ética e Sociedade", "administration", 28, "docente.b@example.edu", [], "a101", [4], "19:00", "20:40"),
    ]
    for ident, code, name, course, size, teacher, resources, room, weekdays, start, end in class_specs:
        subject_id = "subject-" + ident
        state["subjects"].append({"id": subject_id, "code": ident.upper(), "name": name, "course_id": course, "active": True})
        state["classes"].append({"id": ident, "code": code, "name": name, "course_id": course, "subject_id": subject_id,
                                 "period_id": "2026-2", "size_expected": size, "size_confirmed": None,
                                 "teacher_emails": [teacher], "campus_id": "campus-centro", "required_resources": resources,
                                 "preferred_resources": ["whiteboard"], "needs_accessibility": ident == "es-web",
                                 "preferred_building_id": "bloco-b" if "computers" in resources else "bloco-a",
                                 "special_justification": "Dados sintéticos: recursos adequados às atividades didáticas e percurso acessível quando indicado.",
                                 "shift": "Noturno", "status": "approved", "review_note": ""})
        for weekday in weekdays:
            meeting_id = ident + "-" + str(weekday)
            state["meetings"].append({"id": meeting_id, "class_id": ident, "weekday": weekday, "start": start, "end": end,
                                      "date": None, "start_date": "2026-08-03", "end_date": "2026-12-18", "excluded_dates": []})
            state["allocations"].append({"meeting_id": meeting_id, "room_id": room, "source": "manual", "locked": False,
                                         "explanation": "Cenário fictício previamente organizado; capacidade, recursos, campus e acessibilidade compatíveis. Revalide no núcleo antes de publicar alterações."})
    version = {"id": "demo-version-1", "number": 1, "period_id": "2026-2", "published_at": now(),
               "published_by": "admin@example.edu", "description": "Versão ilustrativa · dados inteiramente fictícios", "changes": [],
               "snapshot": snapshot(state, "2026-2")}
    state["versions"] = [version]
    state["active_versions"] = {"2026-2": version["id"]}
    audit(state, state["users"][0], "seed_demo", "versions", version["id"], "Criação explícita do cenário sintético para testes; não representa uma instituição real.", after={"classes": 5, "rooms": 6, "meetings": 9})
    return state
