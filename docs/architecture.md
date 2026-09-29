# Arquitetura, metodologia e discussão crítica

## Problema e objetivos

Uma alteração de sala pode deixar planilhas, cartazes e mensagens desatualizados. O sistema
mantém uma versão oficial por período, bloqueia conflitos e fornece caminhos de consulta
distintos para administração, coordenação, professores e alunos. Os dados de demonstração
são exemplos fictícios, não observações coletadas em uma universidade.

## Fronteiras entre componentes

- **Interface:** HTML sem framework, CSS responsivo e módulos JavaScript. Não há custo de
  download de um framework nem etapa de empacotamento obrigatória. A contrapartida é manter
  manualmente componentes, estado e tratamento de eventos. A preferência de turma usa
  armazenamento local por usuário e período; ela não é uma autorização.
- **API:** Flask organiza HTTP e integra Authlib para OIDC. Toda operação aplica autorização
  no servidor. Ações de coordenação também verificam o vínculo ao curso. Cookies transportam
  a sessão; tokens OAuth nunca são enviados ao JavaScript ou gravados no localStorage.
- **Núcleo:** processo C++17 que recebe JSON e devolve validação, sugestões e explicações.
  O servidor limita a duração da chamada e não mantém uma implementação paralela em Python.
  A biblioteca nlohmann/json apenas interpreta/serializa JSON. As regras são do projeto.
- **Persistência:** PostgreSQL na produção, com estado de domínio em documento JSON e
  bloqueio transacional. SQLite existe somente para execução local e testes. A publicação
  copia os dados necessários em um snapshot: editar uma sala no rascunho não modifica a
  localização exibida na versão anteriormente publicada.

## Decisões e alternativas

| Decisão | Benefício | Custo ou limitação | Alternativa |
|---|---|---|---|
| Pages + API em Docker + PostgreSQL | Cumpre o memorial, componentes separados e publicação repetível | Configurar três serviços, CORS e cookies entre sites | Hospedagem única simplificaria sessão, mas não substitui a infraestrutura exigida |
| Processo C++ separado | Isola o algoritmo, testes diretos e independente da camada web | Iniciar um processo por requisição custa tempo | Biblioteca compartilhada exigiria integração ABI e empacotamento mais complexo |
| Heurística gulosa determinística | Decisões reproduzíveis e explicáveis | Pode deixar pendências mesmo quando outra combinação global seria possível | Busca com retrocesso/otimização global acrescenta custo e complexidade |
| Documento transacional com revisão | Snapshots e atualização atômica simples na demonstração | Escritas serializadas e documento cresce com o histórico | Esquema relacional normalizado, índices e particionamento para escala institucional |
| Frontend sem framework | Artefatos pequenos e poucas dependências | Componentização e atualizações manuais | Framework pode ajudar em interfaces maiores, mas exige justificar custo |

O documento transacional representa as entidades do memorial, mas não substitui um desenho
relacional destinado a milhões de registros. A publicação usa a mesma transação que a
validação e o snapshot. A revisão otimista impede uma aba antiga de sobrescrever alterações
feitas por outra pessoa; a interface solicita atualização em caso de HTTP 409.

## Metodologia do ensalamento

O algoritmo elimina salas inválidas antes de calcular pontuações. Capacidade, campus,
acessibilidade, recursos obrigatórios, disponibilidade e conflitos não são compensados por
uma boa preferência. Intervalos de horário são semiabertos: uma aula que termina às 10:00
não conflita com outra que começa às 10:00. As datas efetivas dos encontros recorrentes e
excepcionais são consideradas; exclusões não são tratadas como aulas.

A implementação e as fórmulas efetivas estão em [core/README.md](../core/README.md). A
heurística, os pesos padrão e os critérios de desempate são decisões deste projeto para
operacionalizar RF-21 a RF-27; não são apresentados como um algoritmo publicado de terceiros.
O professor deve confirmar que essa fronteira corresponde ao núcleo conceitual esperado.

## Segurança e privacidade

O sistema verifica identidade externa, sessão, CSRF, papel e escopo. A confirmação da
identidade ocorre no servidor; alterar um campo ou uma turma no navegador não concede
permissão. Configuração de desenvolvimento e contas fictícias não devem ser habilitadas
na hospedagem. A produção exige banco PostgreSQL e configuração de segredos.

O acesso Microsoft depende de um tenant explícito e configuração institucional. A validação
de credenciais OAuth reais precisa ocorrer após o cadastro dos clientes nos provedores.
Não confundir testes com respostas simuladas de OAuth com um login externo comprovado.

Cookies entre `github.io` e `onrender.com` podem ser bloqueados pelo navegador, mesmo com
`SameSite=None; Secure`. Domínios próprios sob o mesmo site evitam essa dependência. A API
também entrega o frontend na própria origem como alternativa operacional; o endereço do
Pages permanece publicado. Validar a topologia final com o professor e com o navegador
usado na apresentação.

## Discussão ética

1. **Localização de pessoas.** Agendas podem revelar onde um professor estará. A consulta
   autenticada e os escopos limitam exposição, mas não eliminam compartilhamentos indevidos.
   Evitar publicar agendas pessoais em capturas de tela e repositórios.
2. **Acessibilidade e dados sensíveis.** Registrar a necessidade funcional, não diagnósticos
   médicos. A acessibilidade é uma restrição obrigatória, sem compensação por pontuação.
3. **Distribuição de recursos escassos.** Priorizar turmas difíceis pode beneficiar certos
   cursos. Uma heurística correta não é prova de equidade. Avaliar pendências por curso e
   revisar decisões com pessoas responsáveis.
4. **Dados incorretos.** Uma capacidade ou matrícula errada pode produzir uma alocação
   formalmente válida, mas inadequada no mundo real. A instituição precisa conferir os
   cadastros; auditoria identifica mudanças, não garante sua veracidade.
5. **Automação e responsabilidade.** A sugestão não publica sozinha. O administrador precisa
   revisar, justificar alterações e assumir a decisão. Uma sala válida pode ainda ser
   inconveniente por fatores não modelados.
6. **Assistência de IA.** O uso está declarado no NOTICE. Participação e autoria não podem
   ser inferidas da quantidade de código gerado nem simuladas com commits de outras pessoas.

## Limitações conhecidas

- A heurística não garante ótimo global nem uma solução sempre que existir solução.
- Não modela diagnósticos, navegação GPS, matrículas, notas ou frequência.
- A publicação bloqueia pendências; exceções institucionais a restrições obrigatórias não
  são presumidas. Uma regra especial precisa ser formalmente especificada antes de implementada.
- Divisão de turma em grupos simultâneos deve ser representada explicitamente em turmas ou
  encontros distintos, com tamanhos e docentes corretos; não duplicar uma alocação.
- Dados fictícios permitem repetir os testes, mas não demonstram impacto em uma instituição real.
- Resultados de desempenho local não demonstram latência de internet, comportamento de um plano
  de hospedagem ocioso ou capacidade de atender toda uma universidade.
- Nome, logotipo, equipe e papéis dependem de confirmação. Marcos A e B e uso de dados reais
  também precisam ser esclarecidos com o professor.

## Referências

- Memorial fornecido na disciplina: *Projeto 1 — Prática Profissional em Desenvolvimento Web*,
  seções 2, 5, 6 e 7. Documento de requisitos, não fonte de resultados empíricos.
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html): autenticação federada.
- [Authlib, integração Flask](https://docs.authlib.org/en/latest/oauth2/client/web/flask.html): cliente OIDC.
- [Google OAuth para aplicações web](https://developers.google.com/identity/protocols/oauth2/web-server).
- [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).
- [GitHub Pages, workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
- [Render Docker](https://render.com/docs/docker) e [BluePrint](https://render.com/docs/blueprint-spec).
- [Supabase, conexão PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres).

Conclusão: a separação entre validação, revisão e publicação reduz inconsistências e permite
rastrear decisões. A confirmação de utilidade real exige validação dos dados e avaliação por
usuários da instituição; uma demonstração sintética não substitui essa etapa.
