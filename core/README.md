# Núcleo de cálculo em C++17

O executável lê um objeto JSON em `stdin` e escreve um objeto JSON em `stdout`. A API chama esse processo; não há algoritmo alternativo em Python ou JavaScript. A biblioteca `nlohmann/json` trata exclusivamente serialização. A filtragem, o calendário, a detecção de conflitos, a pontuação e a heurística estão em `main.cpp`.

## Compilar e testar

Em Debian/Ubuntu, instalar `g++` e `nlohmann-json3-dev`, então, a partir da raiz do repositório:

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic core/main.cpp -o core/ensalamento-core
python -m pytest tests/test_core.py -q
python core/benchmark.py
```

Alternativa com CMake: `cmake -S core -B build && cmake --build build`. A API e os testes aceitam `CORE_BINARY` apontando para o executável em outra localização. No Windows, o nome padrão é `core/ensalamento-core.exe`. O contêiner compila o binário durante o build.

## Contrato

Entrada: `mode` (`allocate`, `validate` ou `suggest`), `rooms`, `classes`, `meetings`, `allocations`, `weights` opcional; `selected_meeting_ids` limita a regeneração; `meeting_id` identifica o encontro no modo de sugestão.

Saída: `allocations`, `unallocated` com motivos, `conflicts` com código/mensagem, `suggestions`, `valid`, `statistics` e os pesos efetivos. Pontuações e explicações acompanham alocações automáticas e sugestões. Campos `details` contêm componentes, preferências atendidas/não atendidas e verificações executadas. A ordem de sugestões é decrescente por pontuação, seguida de identificador de sala crescente.

Uma entrada inválida produz código de saída 2 e `errors: [{code: "INVALID_INPUT", message: "..."}]`. Uma entrada bem formada, mas com conflitos de negócio, produz código 0 e `valid: false`. O consumidor deve distinguir essas situações. Toda validação é feita novamente a cada chamada, sem cache de verificações anteriores.

### Dados mínimos

- Sala: `id`, `campus_id`, `capacity` positiva; `building_id`, `resources`, `accessible`, `status`, `available` e `unavailable` complementam o cadastro. Apenas status `active` admite alocação.
- Turma: `id`, `campus_id`, `size_expected` positiva; `size_confirmed`, se preenchida, substitui a estimativa. `required_resources`, `preferred_resources`, `needs_accessibility`, `preferred_building_id` e `teacher_emails` descrevem necessidades. Professores são comparados sem distinção entre maiúsculas/minúsculas.
- Encontro: `id`, `class_id`, `start`, `end` e **uma data excepcional** em `date` **ou uma recorrência** com `weekday` (0=segunda, 6=domingo), `start_date` e `end_date` inclusivas. `excluded_dates` cancela ocorrências específicas, por exemplo feriados.
- Disponibilidade e indisponibilidade: `date`, `start`, `end`, ou recorrência com `weekday`, `start_date`, `end_date`, `start`, `end`. `available` ausente ou vazio significa abertura geral, sujeita às indisponibilidades. Havendo janelas em `available`, cada ocorrência deve estar inteiramente coberta pela união das janelas desse dia. Janelas adjacentes/ sobrepostas são unidas; um intervalo descoberto, mesmo de um minuto, impede a alocação. `unavailable` sempre prevalece.
- Alocação: `meeting_id`, `room_id`, `source` e `locked`. Uma alocação travada permanece na regeneração e é revalidada mesmo se ficar inválida após uma alteração cadastral.

Todas as turmas não canceladas/encerradas incluídas na entrada devem ter ao menos um encontro e ser completamente alocadas para `valid: true`. O servidor delimita o período e o contexto. Estados excluídos: `cancelled`, `canceled`, `closed`, `cancelada`, `encerrada`. Os dados de turmas canceladas permanecem armazenados pelo servidor para histórico.

## Restrições antes da pontuação

Cada sala candidata deve estar ativa e satisfazer capacidade, campus, recursos obrigatórios e acessibilidade. Todas as ocorrências devem caber nas janelas de disponibilidade quando cadastradas. Nenhuma ocorrência do encontro pode coincidir com uma indisponibilidade da sala. Não podem existir sobreposições com outro encontro alocado na sala. Os encontros da mesma turma e os encontros que compartilham professor também não podem se sobrepor, mesmo quando ainda estão sem sala.

Um encontro pode ter exatamente uma alocação. A implementação não autoriza exceções institucionais a restrições obrigatórias. Uma divisão de turma exige ofertas/encontros distintos previamente cadastrados, com os respectivos tamanhos e professores; não existe divisão automática.

Os horários são intervalos semiabertos: `[início, fim)`. Assim, 08:00–10:00 e 10:00–12:00 podem usar a mesma sala. Há sobreposição quando:

`max(início_A, início_B) < min(fim_A, fim_B)`

e existe ao menos uma data de ocorrência comum, considerando limites, dia da semana e exclusões. A conversão de calendário usa aritmética gregoriana, incluindo anos bissextos. O algoritmo primeiro verifica interseção de intervalos de datas e dias da semana; só percorre ocorrências comuns para tratar exclusões. Datas e horas são locais ao campus; o servidor deve manter essa mesma convenção.

## Índice de adequação

Para uma **sala já válida**, calcula-se:

`S = 100 × (wC·C + wB·B + wR·R + wE·E) / (wC + wB + wR + wE)`

| Componente | Fórmula implementada |
|---|---|
| `C`, ocupação | `tamanho utilizado / capacidade da sala`. Menor desperdício produz pontuação maior. |
| `B`, prédio | `1` quando a sala está no prédio preferido e `0` caso contrário. Sem prédio preferido, vale `1` para todas. |
| `R`, recursos desejáveis | `quantidade de recursos preferenciais presentes / quantidade de recursos preferenciais solicitados`. Sem recursos preferenciais, vale `1` para todas. |
| `E`, estabilidade | `1` se mantém a sala anterior do mesmo encontro; sem alocação anterior, considera as salas já atribuídas a outros encontros da turma; `0` se muda. Sem referência anterior/da turma, vale `1` para todas. |

Pesos padrão: capacidade 40, prédio 20, recursos 25 e estabilidade 15. Cada peso deve ser finito, não negativo e no máximo 1.000.000; a soma deve ser positiva. Campos omitidos mantêm o padrão. A pontuação é arredondada a duas casas antes do desempate, para que a classificação exibida seja reproduzível. Preferências nunca compensam uma violação obrigatória.

O índice é uma decisão de projeto fundamentada nas preferências sugeridas pela seção 6.9.2 do memorial. Não é uma fórmula científica universal nem uma garantia de justiça distributiva; os pesos exigem avaliação institucional. A normalização e os componentes são explicitados para permitir revisão e defesa.

## Heurística e reprodução

1. Preservar todas as alocações travadas e as alocações fora do subconjunto selecionado.
2. Contar as salas que satisfazem as restrições físicas e de disponibilidade de cada encontro.
3. Ordenar os encontros por menor número de candidatas, maior tamanho da turma e identificador crescente.
4. Para cada encontro, filtrar novamente as salas considerando ocupação atual e conflitos acadêmicos; escolher a melhor pontuação, usando o identificador da sala no desempate.
5. Deixar sem sala os encontros sem candidata, agregando os motivos encontrados.
6. Validar **todo** o resultado, inclusive encontros não selecionados, alocações travadas e conflitos de professor.

A estratégia é gulosa, sem backtracking: pode deixar um encontro sem sala mesmo quando uma rearrumação global resolveria o problema. A interface oferece sugestões e ajustes manuais com revalidação integral para apoiar essa revisão. Desempates por identificador dão reprodutibilidade, mas não expressam prioridade acadêmica.

Para `M` encontros, `R` salas, `A` alocações e `U` indisponibilidades por sala, o trabalho principal sem janelas positivas é da ordem de `O(M² + MR(A + U))`, além da ordenação `O(M log M)`. As verificações de calendário podem percorrer ocorrências ao tratar exclusões. Com `V` janelas positivas e `D` ocorrências, acrescenta-se por avaliação de sala até `O(D V log V)` para ordenar/unir intervalos. Os limites de entrada protegem o serviço; a API também deve aplicar timeout ao processo.

## Limites e significado das estatísticas

- JSON até 8 MiB e 64 níveis; até 1.000 salas, 2.000 turmas, 4.000 encontros e 8.000 registros de alocação.
- Datas entre 1970 e 2100; recorrência até 1.830 dias; até 400 exclusões por encontro, 1.000 janelas de disponibilidade e 1.000 indisponibilidades por sala.
- Encontros precisam ter ao menos uma ocorrência válida. Horários que atravessam meia-noite devem ser separados em dois encontros.
- Não há otimização global, cálculo de rotas, distância física entre prédios, capacidade especial de avaliação ou exceção a restrição obrigatória. O cadastro pode guardar dados adicionais; esses aspectos não entram silenciosamente no cálculo.
- `average_occupancy_percent` é a média da razão estudantes/capacidade dos encontros alocados. **Não é** a proporção de horas disponíveis do prédio ocupadas.
- `minutes_per_occurrence_sum` soma a duração de uma ocorrência de cada encontro, sem multiplicar pela quantidade de semanas. Encontros excepcionais entram uma vez. A métrica serve para comparar carga cadastrada, não utilização física exata no semestre.
- `duration_ms` mede a execução do modo após carregar o modelo. O benchmark externo mede o processo inteiro, incluindo inicialização e serialização.

## Evidências e fontes

`tests/test_core.py` executa o binário real e cobre limites de capacidade, acessibilidade, recursos, campus, manutenção, encontros adjacentes, choques de professor/turma/sala, datas excepcionais, exclusões, ano bissexto, recorrências, pesos, preservação de decisões, subconjuntos, erros de entrada e casos gerados de forma determinística. `benchmark.py` usa dados **sintéticos**, explicitamente identificados; não representa horários reais de uma instituição.

- Memorial descritivo fornecido à equipe: seções 6.9, 6.9.1 e 6.9.2 (restrições e preferências).
- [Documentação oficial de nlohmann/json](https://json.nlohmann.me/) — serialização JSON, licença MIT, sem lógica de ensalamento.
- [Howard Hinnant, civil calendar algorithms](https://howardhinnant.github.io/date_algorithms.html) — referência para a transformação entre data gregoriana e ordinal de dias.

O código foi produzido com assistência de IA e requer revisão e domínio pelos participantes. Os testes demonstram propriedades verificadas, não autoria humana nem aprovação acadêmica.
