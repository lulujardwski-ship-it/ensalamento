# Rastreabilidade do memorial

Esta matriz aponta onde verificar cada requisito. A existência do código não prova uma
configuração de produção concluída. Autenticação externa, hospedagem, dados institucionais
e defesa precisam de verificação humana no ambiente de entrega.

## Requisitos funcionais

| ID | Comportamento a verificar | Área de implementação / demonstração |
|---|---|---|
| RF-01 | Google e Microsoft; sem senha própria | `/auth/google`, `/auth/microsoft`; depende dos clientes OAuth |
| RF-02 | Identidade estável e e-mail confirmado | Callback OIDC e vínculo de identidade externa |
| RF-03 | Domínios/listas de contas autorizadas | `ALLOWED_DOMAINS`, usuários pré-cadastrados e autorização no servidor |
| RF-04 | Papéis por pré-cadastro | Cadastro de usuários; aluno autorizado como papel padrão |
| RF-05 | Seleção de turma confirmada no primeiro acesso | Tela de seleção do aluno |
| RF-06 | Preferência por usuário e período | Armazenamento local da interface |
| RF-07 | Preferência não é autorização e não contém token | Cookie de sessão + RBAC independente da preferência |
| RF-08 | Novo navegador exige nova seleção | Testar navegador sem preferência salva |
| RF-09 | Alterar turma; invalidar preferência de turma inativa | Ação trocar turma e verificação da seleção |
| RF-10 | Cadastros e importação CSV | Administração: salas, usuários, turmas, encontros e professores |
| RF-11 | Prévia de importação | `/api/import/preview` |
| RF-12 | Importação inválida preserva dados; relatório de erros | Confirmação atômica e relatório linha/campo/motivo |
| RF-13 | Códigos únicos no contexto | Validação de entidades no servidor |
| RF-14 | Exclusão preserva referências e histórico | Inativação/cancelamento e snapshots |
| RF-15 | Coordenador vê apenas seus cursos/turmas | Bootstrap filtrado e autorização por curso |
| RF-16 | Tamanho, professor, encontros, campus e recursos | Formulários de turma e encontros |
| RF-17 | Obrigatório versus preferência; justificativa | Necessidades da turma |
| RF-18 | Validar informações antes de enviar | Validação do cadastro e `/api/classes/<id>/submit` |
| RF-19 | Bloquear edição após envio, manter revisões | Estados e auditoria de solicitação |
| RF-20 | Progresso por coordenação; devolução justificada | Painel administrativo e ação devolver |
| RF-21 | Gerar todas ou selecionadas | `/api/allocate`, seleção de encontros |
| RF-22 | Filtrar salas inválidas | `core/main.cpp` |
| RF-23 | Índice de adequação configurável | Pesos na API e pontuação no C++ |
| RF-24 | Explicar restrições e preferências | Explicação e componentes de cada sugestão |
| RF-25 | Pendência com causas | `unallocated` do núcleo |
| RF-26 | Movimento manual revalida | `/api/move` |
| RF-27 | Exceções exigem justificativa/regra institucional | Preferências podem ser preteridas; sem regra institucional cadastrada não há bypass obrigatório |
| RF-28 | Alocados, pendentes, conflitos e utilização | Painel de alocação e estatísticas do núcleo |
| RF-29 | Bloquear publicação inválida | `/api/publish` reexecuta a validação |
| RF-30 | Comparar com publicação anterior | `/api/compare` e tela de versões |
| RF-31 | Número, data, responsável e descrição | Metadados de versão |
| RF-32 | Rascunho posterior preserva consulta oficial | Snapshot imutável por publicação |
| RF-33 | Destacar mudança publicada | Estado Alterada e data da versão |
| RF-34 | Versão mais recente e revalidação da tela | Atualização periódica/ao recuperar foco |
| RF-35 | Aula atual, próxima e restante do dia | Agenda do aluno |
| RF-36 | Professor reconhecido por e-mail | Agenda filtrada pelo usuário autenticado |
| RF-37 | Visões diária e semanal | Agenda |
| RF-38 | Detalhes completos do encontro | Cards de aula e detalhes |
| RF-39 | Localização textual e referência visual | Detalhes de sala/prédio; representação esquemática |
| RF-40 | Pesquisa respeitando permissões | Busca sobre dados já filtrados pelo servidor |
| RF-41 | Sem publicação, não revelar rascunho | Estado vazio da agenda |

## Regras de negócio

| ID | Regra | Verificação principal |
|---|---|---|
| RB-01 | Sala sem encontros sobrepostos | Testes C++ de intervalos, dias e datas |
| RB-02 | Uma sala por encontro | Rejeição de alocação duplicada; divisão precisa de grupos explícitos |
| RB-03 | Capacidade suficiente | Usa quantidade confirmada quando informada, senão prevista |
| RB-04 | Sala disponível e ativa | Estado e indisponibilidades no núcleo |
| RB-05 | Todos os recursos obrigatórios | Contenção de conjuntos no núcleo |
| RB-06 | Acessibilidade obrigatória | Filtro independente dos pesos |
| RB-07 | Professor sem sobreposição | Comparação de docentes entre encontros |
| RB-08 | Mudança invalida verificação anterior | Validação executada novamente antes de mover/publicar |
| RB-09 | Uma versão publicada por período/contexto | Ponteiro ativo atualizado na transação |
| RB-10 | Rascunho invisível para consulta | Projeção da versão publicada |
| RB-11 | Cancelamento fora de futuras consultas; histórico preservado | Revisão publicada e snapshot anterior mantido |
| RB-12 | Autor, data, motivo, antes e depois | Auditoria administrativa e diferenças de versão |

## Requisitos não funcionais e entregas

- Interface responsiva, teclado, foco visível, rótulos e estados que não dependem somente da cor.
- Sessão em cookie, autorização no servidor, CSRF, nenhum token OAuth em armazenamento local.
- Publicação transacional, erro de geração/importação sem apagar versão oficial.
- Fuso institucional definido; datas e horários consistentes.
- Testes críticos automatizados; procedimentos de compilação, implantação e restauração.
- README, LICENSE, .gitignore e área Sobre na aplicação.
- Repositório público e aplicação online; apenas `main` é considerada entrega pelo memorial.
- Nome/logotipo da instituição e membros/papéis devem ser fornecidos pela equipe.

## Extensões e limites da nota

Exportação de agenda `.ics` é uma extensão útil de integração com calendários. Indicadores
básicos de ocupação já fazem parte do RF-28 e não são apresentados como extensão inédita.
Testes adicionais e medições são evidências de qualidade, não garantias dos 30 pontos extras.

Os marcos A e B (aulas 12 e 24), a exigência de dados reais e a delimitação exata do núcleo
C/C++ têm ambiguidades no memorial. As datas e a interpretação precisam ser confirmadas
com o professor. O projeto não inventa aprovação ou cumprimento retroativo desses marcos.
