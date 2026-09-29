# Configuração e publicação

Este roteiro exige acesso às contas GitHub, Render, Supabase, Google e ao tenant Microsoft.
O código não cria contas nem contém credenciais. Não enviar senhas, client secrets ou a URL
privada do banco em issues, commits, capturas de tela ou conversas públicas.

## 1. PostgreSQL no Supabase

1. Criar um projeto na conta da equipe e guardar a senha do banco em local seguro.
2. Na área **Connect**, copiar a conexão PostgreSQL apropriada. Quando não houver IPv6 no
   serviço consumidor, usar a conexão **Session pooler** com suporte IPv4, conforme a
   disponibilidade da conta. Acrescentar `sslmode=require` à conexão de produção.
3. Guardar o valor como `DATABASE_URL` no Render, não no código ou em `web/config.js`.
   Como alternativa, omitir a senha da URI e salvá-la separadamente em `PGPASSWORD`
   no ambiente do Render. Isso evita problemas de codificação dos caracteres da senha.
4. O backend cria sua estrutura ao iniciar. Usar um usuário de banco dedicado e limitar o
   acesso. As tabelas da aplicação não devem ser liberadas para leitura/escrita anônima pela
   API REST do Supabase. O navegador fala apenas com a API do projeto.
5. Não usar a chave pública anon como substituto da URL PostgreSQL: o servidor usa psycopg.

Consultar [as opções de conexão do Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

## 2. Serviço Docker no Render

1. Conectar o repositório e criar um **Blueprint** usando `render.yaml`, ou um Web Service
   com runtime Docker e o Dockerfile da raiz. Não criar um Static Site para o servidor.
2. Selecionar a branch de produção `main`. O Dockerfile compila o C++ e instala o backend.
3. Configurar as variáveis da tabela abaixo. Campos marcados como segredo devem ficar no
   ambiente do serviço. O Render gera `SECRET_KEY` no Blueprint.
4. Usar `/api/health` como health check. Ler os logs se o serviço recusar a configuração.
5. Anotar a URL HTTPS atribuída ao serviço e registrar os callbacks OAuth com esse endereço.
6. Confirmar `DEV_LOGIN_ENABLED=false`. Nunca habilitar contas fictícias de desenvolvimento
   em um serviço público para contornar a autenticação exigida.

| Variável | Valor |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | Conexão PostgreSQL privada com TLS |
| `PGPASSWORD` | Senha privada do banco, quando omitida de `DATABASE_URL` |
| `SECRET_KEY` | Segredo aleatório de pelo menos 32 caracteres |
| `FRONTEND_URL` | URL completa do frontend, sem fragmento |
| `ADMIN_EMAILS` | E-mails reais autorizados como administradores, separados por vírgula |
| `ALLOWED_DOMAINS` | Domínios estudantis autorizados, separados por vírgula; não usar domínio público amplo por conveniência |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Cliente web Google |
| `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | Cliente web Microsoft |
| `MICROSOFT_TENANT_ID` | Identificador do tenant autorizado |
| `DEV_LOGIN_ENABLED` | `false` |
| `TRUST_PROXY` | `true` no Render, atrás de um proxy confiável; `false` localmente |

O plano indicado no Blueprint é `free`, quando disponível para a conta. Conferir na tela
de criação as condições, limites e eventual cobrança antes de contratar recursos. Planos
que suspendem serviços ociosos podem aumentar a primeira resposta; testar antes da entrega.

Referências: [Docker no Render](https://render.com/docs/docker),
[Blueprint](https://render.com/docs/blueprint-spec).

## 3. Google

1. Criar ou selecionar um projeto no Google Cloud e configurar a tela de consentimento.
2. Criar um cliente OAuth do tipo **Web application**.
3. Cadastrar como redirect URI exatamente `https://SEU-SERVICO.onrender.com/auth/google/callback`.
4. Copiar ID e segredo para o ambiente do Render. Em modo de teste, cadastrar os usuários
   de teste na configuração de audiência do Google.
5. Reiniciar o serviço e testar conta permitida e conta não autorizada.

O backend solicita os escopos de identidade necessários à autenticação. Não armazena a
senha Google e não precisa de acesso à caixa de e-mail.
Referência: [OAuth para aplicações web](https://developers.google.com/identity/protocols/oauth2/web-server).

## 4. Microsoft

1. No Microsoft Entra do tenant autorizado, registrar um aplicativo web.
2. Configurar a URL de redirecionamento `https://SEU-SERVICO.onrender.com/auth/microsoft/callback`.
3. Copiar o Application (client) ID e o Directory (tenant) ID.
4. Criar um client secret e colocar seu **valor**, não seu identificador, no Render.
5. Confirmar políticas de consentimento e autorização com a instituição; pode ser necessário
   apoio do administrador do tenant. Não substituir o tenant por `common` para ignorar essa etapa.
6. Testar a identidade e os vínculos com um usuário previamente cadastrado.

Referência: [Fluxo authorization code da Microsoft](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

## 5. GitHub Pages

1. Em **Settings → Pages → Build and deployment**, selecionar **GitHub Actions** como fonte.
2. Editar `web/config.js` e definir `API_BASE` como a origem HTTPS do backend, sem barra final.
   Este endereço é público; não adicionar segredos ao arquivo.
3. Definir `FRONTEND_URL` do servidor como `https://lulujardwski-ship-it.github.io/ensalamento/`.
4. Publicar a alteração na `main`. O workflow **Publicar interface** envia somente `web/`.
5. Conferir Actions e acessar o endereço retornado pelo deployment. Um workflow criado sem
   habilitar Pages ainda não confirma publicação.

Referência: [Workflows do GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

### Cookies entre sites

GitHub Pages e Render usam domínios diferentes. O backend configura cookies seguros e CORS
restrito, mas alguns navegadores bloqueiam cookies de terceiros. Validar o login no navegador
da apresentação. Há duas opções operacionais:

- Usar domínios próprios do mesmo site para Pages e API, mantendo a infraestrutura exigida.
- Usar a cópia do frontend servida pela API para a área autenticada, com `FRONTEND_URL`
  apontando para ela. O Pages continua disponível como interface pública/demonstração.

A segunda opção deve ser explicitada ao professor, pois a experiência autenticada passa a
ser servida pelo Render. Não afirmar que o caminho Pages autenticado foi validado se somente
a alternativa da mesma origem foi testada.

## 6. Dados e verificação final

Cadastrar os períodos, estrutura física, recursos, cursos, disciplinas, usuários, turmas e
encontros. Usar dados fictícios identificados na demonstração. Importações CSV precisam de
prévia e confirmação; um relatório com erro não autoriza substituir os registros corretos.

Executar o [roteiro de demonstração](defense.md) com as quatro funções. Conferir a versão
publicada a partir de um segundo navegador, alterar uma sala no rascunho e verificar que a
consulta só muda após nova publicação. Testar o Google e a Microsoft separadamente.

## Backup e restauração

Para cópia integral do PostgreSQL, usar as ferramentas do PostgreSQL com conexão obtida de
variável de ambiente. Arquivos de backup contêm dados e ficam fora do Git.

```bash
mkdir -p backups
pg_dump "$DATABASE_URL" --format=custom --file=backups/ensalamento.dump
pg_restore --dbname="$RESTORE_DATABASE_URL" --no-owner backups/ensalamento.dump
```

`RESTORE_DATABASE_URL` deve apontar para um banco **novo e vazio**, separado da produção.
Iniciar uma instância da aplicação conectada ao banco restaurado e conferir períodos,
versões, auditoria e consulta. Não executar `--clean` sobre o banco em uso. Registrar a data,
responsável e resultado de um ensaio real de restauração; este roteiro não prova que ele ocorreu.

## O que configura uma entrega online concluída

- Código avaliado e testes passando na `main`.
- Frontend acessível no Pages e API saudável no endereço informado.
- PostgreSQL persistindo dados após reinício do serviço.
- Ambos os provedores autenticando e autorizando os perfis corretamente.
- Uma versão válida publicada e consultável por aluno/professor.
- Informações acadêmicas completas no site, com equipe, instituição, metodologia e referências.

Ter o código no GitHub ou uma demonstração estática acessível, isoladamente, não conclui
essas verificações.
