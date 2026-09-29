# Ensalamento

Aplicação acadêmica para organizar a distribuição de turmas em salas, publicar versões
oficiais dos horários e orientar alunos e professores. Projeto da disciplina **Prática
Profissional em Desenvolvimento Web — Engenharia de Software**, 2026.

> Implementação e demonstração local disponíveis. A publicação de produção depende de configurar
> PostgreSQL, hospedagem e os dois provedores de identidade. Os exemplos são fictícios.
> Instituição, logotipo, integrantes e papéis ainda precisam ser informados pela equipe.

## Arquitetura

```text
GitHub Pages (HTML, CSS e JavaScript)
             │ HTTPS + sessão em cookie
             ▼
Render (Docker: Flask/Gunicorn + núcleo C++17)
             │ transações
             ▼
Supabase (PostgreSQL gerenciado)
```

O C++ decide se uma sala é válida, calcula sua adequação e gera a proposta. Python cuida
da autenticação, permissões, persistência, importações, auditoria e publicação. Bibliotecas
HTTP, OAuth, banco e JSON não substituem o algoritmo de ensalamento.

## Documentação

- [Contrato da API](docs/api-contract.md)
- [Publicação e configuração](docs/deploy.md)
- [Decisões de arquitetura e discussão ética](docs/architecture.md)
- [Rastreabilidade do memorial](docs/requirements.md)
- [Roteiro de demonstração e defesa](docs/defense.md)
- [Autoria e assistência de IA](NOTICE.md)

## Funcionalidades

Cadastros da estrutura física e acadêmica, CSV com prévia e confirmação atômica, coordenação
por curso, proposta automática, seleção parcial, ajustes preservados, comparação de versões,
publicação transacional, auditoria, agenda diária/semanal, pesquisa, localização e calendário.
Google e Microsoft usam OIDC; o servidor controla permissões, sessão HttpOnly e proteção CSRF.
A integração real com esses provedores ainda precisa ser configurada e verificada.

## Executar localmente

Pré-requisitos: Python 3.12+, compilador C++17 (`g++` ou `clang++`) e o cabeçalho
[nlohmann/json](https://github.com/nlohmann/json), versão 3.11.3 ou compatível.
No Debian/Ubuntu: `sudo apt-get install g++ nlohmann-json3-dev`.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/build_core.py
python scripts/start_local.py
```

Abrir **http://127.0.0.1:8000** e expandir **Ambiente local de desenvolvimento**.
Os quatro perfis fictícios permitem testar o fluxo completo. O script usa SQLite em
`instance/demo.sqlite3`, sem substituir uma base existente, e permite acesso somente local.
Esse login não existe na configuração de produção. O botão **Explorar exemplo** abre uma
consulta estática somente leitura, independente do banco e explicitamente identificada.

Se o compilador/cabeçalho não estiver no caminho padrão:

```bash
python scripts/build_core.py --compiler CAMINHO_DO_COMPILADOR --include PASTA_DOS_CABECALHOS
# Alternativa com Zig instalado: --zig CAMINHO_DO_ZIG --include PASTA_DOS_CABECALHOS
```

`--include` aponta para a pasta que contém `nlohmann/json.hpp`.
Para configurar uma instância própria, consultar `.env.example`. O aplicativo **não carrega
esse arquivo automaticamente**: exportar as variáveis no shell ou cadastrá-las na plataforma.
`start_local.py` usa deliberadamente configuração fictícia própria.

## Testes

```bash
python -m pytest -q
python core/benchmark.py
```

A validação local passou em **115 testes**, com **4 casos condicionais ignorados** por não
haver PostgreSQL configurado localmente. O workflow `Verificar aplicação` prepara PostgreSQL
16, compila o núcleo, executa testes, verifica sintaxe e constrói o Dockerfile. Consultar o
resultado no GitHub; a existência do workflow não comprova sua execução.

O benchmark sintético em `core/benchmark-results.json` usa 500 encontros e 60 salas.
É uma medição local, não uma garantia de latência em hospedagem gratuita. O método guloso
é determinístico e pode deixar pendências mesmo quando existe uma solução global.

## Publicação

`Dockerfile`, `render.yaml` e `.github/workflows/pages.yml` preparam a implantação descrita
no [roteiro de publicação](docs/deploy.md). Apenas `web/` é enviado ao Pages. Segredos ficam
nas variáveis do backend. A demonstração estática e os testes locais não comprovam operação
em Render/Supabase nem autenticação real. Instituição, logotipo e equipe são configurados
em `web/config.js`. A assistência de IA está declarada no [NOTICE](NOTICE.md).

## Licença

MIT, proposta para permitir estudo, reprodução e adaptação do código com preservação do
aviso de autoria. A escolha deve ser validada pela equipe e justificada ao professor.
Marcas institucionais e dados de terceiros não são licenciados por este repositório.
