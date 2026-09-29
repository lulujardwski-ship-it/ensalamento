# Roteiro de demonstração e estudo

Usar uma base de demonstração identificada como fictícia. Não usar o atalho de login local
como evidência de que Google ou Microsoft funcionaram na hospedagem.

## Sequência de apresentação

1. **Entrada e identidade:** entrar com Google, sair e entrar com Microsoft; demonstrar
   uma conta permitida e a recusa de uma conta fora das regras. Explicar identificador
   estável, e-mail, pré-cadastro e diferença entre identidade e papel.
2. **Administrador:** mostrar período, campus, prédio, sala, curso, disciplina, professor,
   turma e encontros. Importar CSV válido com prévia. Apresentar também um CSV inválido e
   o relatório por linha; verificar que os registros corretos continuam intactos.
3. **Coordenador:** editar somente as turmas de seu curso, preencher tamanho e necessidades,
   enviar a solicitação e mostrar o bloqueio de edição. Demonstrar a devolução justificada
   pelo administrador. O coordenador não pode publicar nem alterar curso de outro escopo.
4. **Núcleo:** gerar proposta; mostrar as restrições verificadas, os pesos e as preferências.
   Criar uma turma maior que todas as salas e explicar a pendência. Corrigir o dado e gerar
   novamente. Mostrar que acessibilidade obrigatória não é compensada por preferência.
5. **Movimento manual:** escolher uma sala válida e justificar. Tentar uma sala pequena ou
   já ocupada: o servidor deve recusar. Uma alocação bloqueada deve sobreviver à regeneração.
6. **Publicação:** comparar a proposta, publicar a versão e mostrar número, data e autor.
   Antes disso, o aluno não deve enxergar o rascunho.
7. **Aluno:** confirmar turma; atualizar a página e mostrar que a escolha foi lembrada.
   Alternar agenda diária/semanal e abrir localização da sala. Outro usuário no mesmo
   navegador não deve herdar automaticamente a preferência do anterior.
8. **Professor:** entrar com professor pré-cadastrado e mostrar suas aulas, sem escolher turma.
9. **Revisão:** alterar uma sala em rascunho; consultar em outro navegador e mostrar a versão
   anterior. Publicar a revisão, voltar à aba e verificar atualização e destaque Alterada.
10. **Auditoria:** identificar autor, data, motivo e valores anteriores/novos. Cancelar uma
    turma em nova revisão e explicar por que o histórico continua existindo.
11. **Novo período:** criar/ativar um período diferente e comprovar que a seleção de turma
    do aluno precisa ser feita novamente.
12. **Qualidade:** executar testes, apresentar as medições com contexto e exportar a agenda
    para `.ics`. Expor as limitações conhecidas e a assistência de IA declarada.

## Perguntas que cada integrante deve conseguir responder

- Onde está o código C++ responsável por rejeitar uma sala pequena?
- Por que pontuar salas antes de eliminar as inválidas seria incorreto?
- Como são representados encontros recorrentes, datas excepcionais e datas excluídas?
- Por que 09:00–10:00 e 10:00–11:00 não conflitam?
- Como é calculado o índice de adequação e qual o critério de desempate?
- Por que a heurística pode deixar uma turma pendente mesmo havendo outra combinação viável?
- O que ocorre se duas abas tentarem modificar a mesma revisão?
- Como uma alteração no cadastro não modifica silenciosamente a versão já publicada?
- Onde a autorização de coordenador é aplicada no servidor?
- Qual a diferença entre cookie de sessão e preferência de turma no localStorage?
- Por que o banco está em um serviço separado? Quais são os custos dessa arquitetura?
- Como o projeto se comporta se a API ou o banco estiver indisponível?
- Quais dados podem revelar a localização de alguém? Como limitar essa exposição?
- Quais partes cada integrante realmente implementou, revisou e testou?

## Registro de evidências

Guardar links dos commits, pull requests e revisões reais. Não criar contribuições artificiais
para simular equilíbrio. Registrar a data, ambiente e resultado de testes de login, publicação,
restauração e acessibilidade. Medições locais devem ser identificadas como locais.

## Dados acadêmicos a preencher

Em `web/config.js`: instituição, caminho do logotipo autorizado e participantes com seus
papéis reais. Conferir a licença MIT proposta e inserir qualquer orientação adicional do
professor. O grupo não deve atribuir resultados sintéticos à instituição.
