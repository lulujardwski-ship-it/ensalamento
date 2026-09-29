# Contrato da API — Ensalamento

API JSON, nomes `snake_case`, raiz configurável `API_BASE` (mesma origem em desenvolvimento). Datas ISO, horas `HH:MM`, `weekday` 0=segunda a 6=domingo, fuso `America/Sao_Paulo`. Credenciais: `fetch(...,{credentials:'include'})`. Erros: `{error,message,details?}`. Operações autenticadas exigem sessão; mutações exigem `X-CSRF-Token` e `revision` no JSON (revisão recebida no bootstrap). Conflito de revisão: HTTP 409, recarregar o bootstrap. As respostas de mutação incluem `revision`.

## Autenticação
- `GET /api/session` → `{user:null|{id,email,name,role,course_ids},csrf_token,providers:{google:boolean,microsoft:boolean},demo_available,environment}`.
- `GET /auth/google` / `GET /auth/microsoft`: redirecionam ao provedor. Callback `/auth/<provider>/callback`, depois redireciona ao `FRONTEND_URL`.
- `POST /api/dev-login` `{role:'admin'|'coordinator'|'teacher'|'student'}` → mesma sessão. Somente desenvolvimento explícito em localhost, usuários fictícios. Dispensa CSRF por ser entrada, verifica Origin.
- `POST /api/logout` `{}` com CSRF.

## Leitura
- `GET /api/bootstrap?period_id=...` → `{revision,user,csrf_token,mode:'draft'|'published',periods,campuses,buildings,resources,courses,subjects,rooms,classes,meetings,allocations,settings,published_version,versions,audit,users}`. Admin recebe rascunho integral. Coordenador recebe apenas suas turmas/cursos e dados físicos. Professor recebe apenas aulas vinculadas ao seu e-mail na versão publicada. Aluno recebe apenas versão publicada. Sem publicação: listas acadêmicas/allocations vazias e `published_version:null`; nunca expõe rascunho. `versions`, `audit`, `users` são vazios ou omitidos para consultas sem permissão. `settings.weights={capacity,building,resources,stability}`.
- `GET /api/versions?period_id=...` lista metadados (admin/coordenador).
- `GET /api/compare?period_id=...` → `{changes:[{meeting_id,before,after,kind}],previous_version}` (admin).
- `GET /api/schedule?period_id=...&class_id=...&date=YYYY-MM-DD&view=day|week` → `{events,current,next,published_version,date,timezone}`. Professor é filtrado pelo e-mail autenticado; `class_id` não amplia permissões.
- `GET /api/calendar.ics?period_id=...&class_id=...&date=YYYY-MM-DD` exporta a semana oficial.
- `GET /api/health` → estado técnico sem dados internos.

## Cadastros e coordenação
- `POST /api/entities/<entity>` `{revision,record:{...},reason}` cria ou atualiza por `record.id` (se omitido gera UUID). Entidades: `periods,campuses,buildings,resources,courses,subjects,rooms,users,classes,meetings`. Admin em todas; coordenador apenas `classes` e `meetings` de cursos próprios, enquanto rascunho/em revisão. Retorna `{record,revision}`.
- `DELETE /api/entities/<entity>/<id>` `{revision,reason}`: registros usados são inativados/cancelados; nunca remove snapshot publicado.
- `POST /api/classes/<id>/submit` `{revision,reason?}` valida e bloqueia (`status:'submitted'`).
- `POST /api/classes/<id>/return` `{revision,reason}` admin devolve (`status:'in_review'`).
- `POST /api/classes/<id>/approve` `{revision,reason?}` admin aprova (`status:'approved'`).
- `POST /api/import/preview` `{entity,csv}` → `{token,valid_count,errors:[{line,field,message}],warnings:[],duplicates:[],records:[]}`. Sem mutação da base; até 1 MiB. Cabeçalhos correspondem aos campos JSON; listas aceitam `;`, booleanos `true/false`, campos compostos aceitam JSON.
- `POST /api/import/confirm` `{revision,token,reason}` → `{imported,revision}`. Revalida tudo e aplica atomicamente; prévia com erros não é confirmável.

## Ensalamento (admin)
- `POST /api/allocate` `{revision,period_id?,selected_meeting_ids?,reason?}` → resposta do núcleo + `revision`.
- `POST /api/validate` `{revision?,period_id?}` → `{valid,conflicts,unallocated,allocations,statistics,revision}`. Apenas valida, não exige revisão otimista.
- `GET /api/suggestions?meeting_id=...` → `{suggestions:[{room_id,score,explanation}],...}`.
- `POST /api/move` `{revision,meeting_id,room_id,locked:true,reason}` revalida antes de aceitar, grava origem `manual`.
- `POST /api/weights` `{revision,weights:{capacity,building,resources,stability},reason}` configura pesos não negativos.
- `POST /api/publish` `{revision,period_id,description,reason}` revalida e bloqueia pendências; cria snapshot imutável e troca versão ativa em transação. Retorna `{version,revision}`.
- `POST /api/versions/<id>/archive` `{revision,reason}` arquiva publicação removendo-a da consulta ativa.

## Entidades principais
`rooms`: `{id,code,name,campus_id,building_id,floor,capacity,exam_capacity?,type?,resources:[],accessible,status:'active'|'maintenance'|'inactive',available:[],unavailable:[],directions}`.

`classes`: `{id,code,name,course_id,subject_id?,period_id,size_expected,size_confirmed:null|number,teacher_emails:[],campus_id,required_resources:[],preferred_resources:[],needs_accessibility,preferred_building_id?,special_justification?,shift?,status:'draft'|'submitted'|'in_review'|'approved'|'cancelled'|'closed',review_note?}`.

`meetings`: `{id,class_id,weekday,start,end,date:null|YYYY-MM-DD,start_date,end_date,excluded_dates:[]}`.

`allocations`: `{meeting_id,room_id,source:'automatic'|'manual',locked,score,explanation}`.

`periods`: `{id,code,name,start_date,end_date,submission_deadline?,active}`; `campuses`: `{id,code,name,address,directions}`; `buildings`: `{id,code,name,campus_id,directions}`; `courses`: `{id,code,name,campus_id}`; `subjects`: `{id,code,name,course_id}`; `resources`: `{id,code,name}`; `users`: `{id,email,name,role,course_ids:[],active}`.

## Persistência e segurança
PostgreSQL obrigatório em produção; SQLite somente local/testes. Documento JSON único com bloqueio transacional e revisão otimista, adequado à demonstração, não a grandes instituições. Auditoria guarda autor/data/motivo/antes/depois. Versões mantêm cópia completa dos dados necessários à consulta. Sem senhas, tokens OAuth ou segredos nos dados retornados.

Cada intervalo em `available` e `unavailable` aceita `{date,start,end}` ou `{weekday,start_date,end_date,start,end}`. Disponibilidade vazia não restringe horários; indisponibilidades sempre bloqueiam.
