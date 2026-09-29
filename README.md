# Ensalamento

Aplicação acadêmica para organizar a distribuição de turmas em salas, publicar versões
oficiais dos horários e orientar alunos e professores. Projeto da disciplina **Prática
Profissional em Desenvolvimento Web — Engenharia de Software**, 2026.

> Desenvolvimento e validação em andamento. A publicação de produção depende de configurar
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

As instruções de compilação, execução e testes serão consolidadas após a validação da implementação.

## Licença

MIT, proposta para permitir estudo, reprodução e adaptação do código com preservação do
aviso de autoria. A escolha deve ser validada pela equipe e justificada ao professor.
Marcas institucionais e dados de terceiros não são licenciados por este repositório.

