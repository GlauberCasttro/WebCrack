# Plano de revisão pré-commit — WebCrack

Só li o diff (`git diff`) e os arquivos completos para me situar — não editei nada. Abaixo está o plano concreto, incluindo os prompts que cada agente receberia. Não executei nenhum agente.

## 1. O que está mudando (visão rápida)

| Arquivo | Natureza da mudança |
|---|---|
| `core.py` | `get_file_tree` reescrito (API de Git Trees recursiva em vez de exploração manual por diretório); `max_tokens` 2048→4096; `readme_preview_chars` 2000→5000; `output_dir` virou caminho absoluto |
| `app.py` | Novo `_env_flag`; `PORT`, `FLASK_DEBUG` e `WEBCRACK_OPEN_BROWSER` agora vêm de env vars; `debug` default **True** (antes era `False` fixo); `use_reloader=False` adicionado |
| `agents/synthesizer.py` | Preview do README no prompt: 3000→5000 chars (hardcoded, não usa `CONFIG["readme_preview_chars"]`) |
| `templates/index.html` | Nome do modelo exibido corrigido (Llama 3.3 70B); lógica de streaming (`drainChars`/`tokenQueue`) removida — texto acumula direto em `accText` |
| `.gitignore`, `.vscode/launch.json` | Ajustes de tooling local (ruflo, porta de debug) |
| `AGENTS.md` | Deletado (59 linhas) |

Isso mistura pelo menos três mudanças de natureza diferente — refactor de performance (file tree), mudança de configuração/segurança (debug mode, porta) e simplificação de UI (streaming) — o que já é um motivo para revisar em paralelo por especialidade em vez de um único agente ler tudo sequencialmente.

## 2. Estratégia de execução

**Fan-out por especialidade + uma etapa de triagem no final.** Três revisores trabalham em paralelo sobre o mesmo diff (cada um com um recorte diferente), e depois uma etapa de síntese cruza os achados com `git log -p`/`git blame` para classificar cada ponto como **regressão** (o diff piorou algo que funcionava) ou **problema pré-existente** (já estava lá, o diff só tocou a área).

Não uso pipeline sequencial aqui porque as três revisões são independentes entre si (backend, frontend, segurança) e não há dependência de dados entre elas — só a triagem final precisa dos três resultados.

```
                ┌──────────────────┐
   git diff ──▶ │  reviewer-backend │──┐
                └──────────────────┘  │
                ┌──────────────────┐  │      ┌───────────┐
   git diff ──▶ │ reviewer-frontend│──┼─────▶│  triagem  │──▶ relatório final
                └──────────────────┘  │      │ (regressão│    (para o usuário
                ┌──────────────────┐  │      │  vs. já   │     decidir commit)
   git diff ──▶ │ reviewer-security│──┘      │  existia) │
                └──────────────────┘         └───────────┘
```

Uso os agentes já nomeados na equipe (`reviewer-backend`, `reviewer-frontend`, `reviewer-security`) para as três revisões, e a triagem final eu faço (ou um quarto agente `triage`, se preferir isolamento de contexto).

## 3. Agentes e prompts concretos

### 3.1 `reviewer-backend` — corretude em `core.py` + `app.py`

```
Revise as mudanças não commitadas em core.py e app.py do projeto WebCrack
(rode `git diff -- core.py app.py` para ver o diff exato). Foque em CORRETUDE,
não em segurança (isso é outro agente) nem em estilo.

Pontos que exigem atenção específica:

1. core.py get_file_tree() foi reescrito para usar a API
   `GET /repos/{full_name}/git/trees/{branch}?recursive=true` em vez de
   exploração manual por diretório. Verifique:
   - O fallback para branch "master" só dispara se default_branch == "main"
     E a primeira chamada falhar. Se o repo usa outro nome de branch padrão
     (ex.: "develop", "trunk") e a chamada falhar, `data` fica None e cai
     direto no fallback de exploração manual sem nunca tentar o branch certo.
     Isso é esperado ou é um bug?
   - A filtragem por _INTERESTING_DIRS mudou de comportamento: antes
     explorava até 2 níveis abaixo de qualquer dir "interessante" nomeado
     na raiz; agora filtra por profundidade de path (`len(parts) <= 3` ou
     `len(parts) == 4 and parts[1] in _INTERESTING_DIRS`). Isso cobre os
     mesmos casos de antes? Rode mentalmente com uma árvore tipo
     `skills/foo/bar/baz/qux.py` e confirme se o resultado bate com o que
     a função antiga produziria.
   - A API de Git Trees tem um limite documentado de 100.000 entradas e
     retorna `"truncated": true` quando corta — esse campo é ignorado aqui.
     Para repos grandes isso pode silenciosamente devolver uma árvore
     incompleta sem avisar ninguém. Vale ao menos logar quando truncated=true?
   - Essa mudança reduz o número de chamadas HTTP de N (uma por diretório)
     para 1-2, o que é uma melhoria real — mas verifique se o rate limit
     de 60 req/h (sem GITHUB_TOKEN) ainda é o gargalo dominante ou se isso
     resolve o problema de fato.

2. app.py: `max_tokens` subiu de 2048 para 4096. O comentário antigo dizia
   "limitado para evitar erro 413 do Groq" — o novo comentário só diz
   "aumentado de 2048 para 4096" sem explicar por que o limite anterior
   deixou de ser necessário. Isso é uma regressão potencial (o erro 413
   pode voltar) ou o limite do Groq mudou? Verifique se há tratamento de
   erro para 413 em algum lugar do código.

3. app.py entry point: `port`, `debug` e `open_browser` agora vêm de env
   vars via `_env_flag`. Note que `app.run(..., use_reloader=False)` foi
   adicionado — isso é necessário porque `debug=True` mais o
   `threading.Timer` de abrir o browser duplicaria a abertura da aba se o
   reloader do Flask reiniciasse o processo. Confirme se essa é de fato a
   razão e se resolve o problema (o reloader do Werkzeug roda o app.py
   duas vezes por padrão quando debug=True).

4. `CONFIG["output_dir"]` virou caminho absoluto baseado em
   `os.path.dirname(os.path.abspath(__file__))`. Isso muda o comportamento
   se alguém já tinha uma pasta `analises/` relativa ao cwd anterior —
   arquivos antigos "somem" da listagem em `/analyses`? Vale mencionar.

5. Não há testes automatizados reais no projeto (test_pipeline.py é um
   smoke test que só imprime eventos, não faz assert). Para o
   get_file_tree() reescrito, rode manualmente contra 2-3 repos reais
   (um pequeno, um com branch "master", um grande com >120 arquivos) e
   reporte a árvore resultante comparada ao comportamento documentado.

Formato de saída: lista de achados, cada um marcado como
[BUG] / [RISCO] / [SUGESTÃO], com o trecho de código citado (arquivo:linha)
e o que você recomenda. Não aplique fixes, só reporte.
```

### 3.2 `reviewer-frontend` — corretude em `templates/index.html`

```
Revise as mudanças não commitadas em templates/index.html do projeto WebCrack
(rode `git diff -- templates/index.html`). Foque em CORRETUDE da lógica de
streaming SSE, não em segurança nem em CSS/visual.

Contexto: a função doAnalyze() e doChat() tinham um mecanismo de "drenagem"
de tokens (tokenQueue + drainChars com setTimeout) que simulava um efeito
de digitação caractere-por-caractere, com timers de 20ms/8ms. Esse mecanismo
foi REMOVIDO — agora o texto recebido via SSE (evento "token") é só
concatenado direto em `accText`, e um `setInterval` de 80ms redesenha o
Markdown acumulado.

Verifique:

1. Race condition entre o `renderTimer` (setInterval de 80ms) e o handler
   `.then()` do fetch: quando o SSE termina, o `.then()` roda
   `clearInterval(renderTimer)` e imediatamente escreve
   `out.innerHTML = marked.parse(sessions[currentKey].analysis)`. Existe
   uma janela em que o `renderTimer` dispara UMA última vez entre o
   recebimento do último token e o `clearInterval`? Se sim, há dupla
   renderização (inofensiva, mas desperdício) — ou pior, uma renderização
   parcial fica visível por 80ms antes da final. Constate se isso é
   perceptível ou puramente teórico.

2. O `renderTimer` só limpa `accText = ''` depois de renderizar
   (`if (accText) { out.innerHTML = ...; accText = ''; }` — confirme a
   lógica exata lendo o código). Se o SSE emitir tokens mais rápido que os
   80ms do timer, `accText` acumula corretamente? Ou existe alguma perda
   de caracteres na transição entre o loop de acúmulo e o parse final?

3. Compare o comportamento visual ANTES (efeito de "digitação" caractere a
   caractere, ~20ms/char no doAnalyze e ~8ms/char no doChat) com DEPOIS
   (atualização em blocos a cada 80ms). Isso é uma regressão de UX
   intencional (simplificação) ou pode ter sido uma remoção acidental de
   feature? Não assuma — se não houver menção a isso em nenhum lugar do
   diff/commit, marque como pergunta para o autor.

4. No `.catch()` de erro de ambas as funções, confirme que não sobrou
   nenhuma referência a `drainTimer` ou `tokenQueue` (variáveis removidas)
   — se sobrar, é ReferenceError em runtime. Faça uma busca textual por
   `drainTimer`, `tokenQueue`, `drainChars`, `sseComplete` no arquivo
   inteiro pós-diff, não só no trecho alterado.

5. A troca do nome do modelo exibido (GPT-OSS-120B → Llama 3.3 70B) bate
   com o `CONFIG["model"]` real em core.py (`llama-3.3-70b-versatile`)?
   Confirme que não é só um texto solto desatualizado em outro lugar da
   página (ex.: rodapé, tooltip, texto de ajuda).

Formato de saída: lista de achados, cada um marcado como
[BUG] / [RISCO] / [SUGESTÃO], com número de linha. Não aplique fixes.
```

### 3.3 `reviewer-security` — passe de segurança em todos os arquivos alterados

```
Faça uma revisão de segurança das mudanças não commitadas no projeto
WebCrack (core.py, app.py, agents/synthesizer.py, templates/index.html).
Rode `git diff` para ver o que mudou exatamente, mas você TEM PERMISSÃO
para olhar os arquivos completos (não só o diff) porque um risco de
segurança pode nascer da interação entre uma linha alterada e uma linha
que não mudou.

Pontos a verificar (comece por estes, mas não se limite a eles):

1. **app.py, linha do app.run()**: `debug = _env_flag("FLASK_DEBUG",
   default=True)` — o default mudou de `debug=False` (hardcoded, antes do
   diff) para `True` por padrão agora. O debugger do Werkzeug com
   `debug=True` expõe um console interativo (Werkzeug debugger) acessível
   por HTTP a quem conseguir disparar uma exceção não tratada — isso é
   RCE se o processo for exposto além de 127.0.0.1. Hoje o bind é
   implícito em 127.0.0.1 (só localhost) via `webbrowser.open`, mas nada
   no código impede rodar com `--host 0.0.0.0` ou atrás de um proxy.
   Avalie: esse default deveria ser `False`, com o dev tendo que optar
   explicitamente por `FLASK_DEBUG=1`? Isso é uma REGRESSÃO clara em
   relação ao estado anterior (antes era `debug=False` fixo, sem
   possibilidade de erro de configuração).

2. **app.py `/analyses/<path:name>` (delete_analysis)**: `path =
   os.path.join(ANALYSES_DIR, name + ".md")` — o conversor `<path:name>`
   do Flask aceita barras. Teste se `name` com `../` permite escapar de
   `ANALYSES_DIR` (path traversal) e deletar arquivos arbitrários do
   sistema de arquivos acessíveis ao processo. Esta rota NÃO foi alterada
   neste diff — confirme se já existia antes (`git log -p -- app.py` ou
   `git show <commit-anterior>:app.py`) para classificá-la como
   pré-existente, mas reporte de qualquer forma porque é grave e está na
   mesma superfície que está sendo tocada agora.

3. **templates/index.html**: `out.innerHTML = marked.parse(...)` e
   `botBubble.innerHTML = marked.parse(...)` em múltiplos pontos (linhas
   ~609, ~620, ~662, ~687, ~730, ~754) — não há sanitização (nenhum
   DOMPurify ou equivalente) entre o output do LLM/README e a inserção
   como HTML. Como o prompt em synthesizer.py e core.py injeta o
   README/conteúdo de arquivos do repositório analisado diretamente no
   contexto do LLM, um README malicioso poderia induzir o modelo a
   ecoar HTML/JS na resposta, resultando em XSS refletido/armazenado
   quando renderizado. Esse padrão não foi introduzido por este diff,
   mas o diff aumenta a superfície (preview do README foi de 2000/3000
   para 5000 chars, mais conteúdo passa pelo pipeline). Confirme se é
   pré-existente e reporte a severidade.

4. **core.py CONFIG["readme_preview_chars"] 2000→5000 e max_tokens
   2048→4096**: mais conteúdo de terceiros (README de repositórios
   arbitrários no GitHub) entra no prompt enviado à Groq. Isso não é uma
   vulnerabilidade nova, mas aumenta a superfície de prompt injection
   (um README pode conter instruções tipo "ignore instruções anteriores").
   Veja se `_inject_loop_bypass` ou qualquer outro mecanismo em
   `stream_llm` poderia ser abusado por conteúdo malicioso do README goal
   (por exemplo, um README que contenha o texto exato
   "[ignoring loop detection]" — isso poderia interferir na lógica de
   bypass de detecção de loop do Groq?).

5. **agents/synthesizer.py**: `readme[:5000]` está hardcoded, NÃO usa
   `core.CONFIG["readme_preview_chars"]` (que também foi setado para
   5000, mas de forma independente). Isso é um code smell de
   inconsistência — se alguém mudar `CONFIG["readme_preview_chars"]`
   futuramente, synthesizer.py não vai refletir a mudança, e os dois
   pontos podem divergir silenciosamente. Não é uma vulnerabilidade em
   si, mas gera risco de manutenção que pode reintroduzir bugs de
   segurança (ex.: alguém reduz o limite em core.py por causa de um
   incidente e esquece do segundo lugar).

6. **.gitignore**: novo bloco ignora `.swarm/` e `.claude-flow/`. Confirme
   que nenhum desses diretórios já está commitado no repo (rode
   `git ls-files | grep -E "^(\.swarm|\.claude-flow)/"`) — se já tiver
   arquivo rastreado ali, adicionar ao .gitignore não remove do
   histórico, e pode conter estado/memória local com dados sensíveis.

7. Segredos: confirme que nenhum arquivo alterado ou novo (`.mcp.json`,
   `CLAUDE.md`, `.claude/`) contém chave de API, token do GitHub ou
   qualquer credencial. Rode uma busca por padrões de chave
   (`gsk_`, `ghp_`, `sk-`, etc.) nesses arquivos antes de aprovar o commit.

Classifique cada achado como [REGRESSÃO] (o diff piora o que já era
seguro) ou [PRÉ-EXISTENTE] (já era um problema antes, o diff só toca a
área) — usando `git log -p`/`git show` no arquivo para confirmar o estado
anterior antes de afirmar. Priorize por severidade (crítico/alto/médio/
baixo). Não aplique fixes, só reporte.
```

### 3.4 Triagem final (eu, ou um 4º agente `triage` isolado)

```
Você recebeu três relatórios independentes (reviewer-backend,
reviewer-frontend, reviewer-security) sobre o mesmo diff não commitado no
WebCrack. Sua tarefa:

1. Consolidar os achados em uma lista única, removendo duplicatas (ex.: a
   inconsistência do readme_preview_chars pode aparecer tanto no relatório
   de backend quanto no de segurança).
2. Para cada achado, confirmar a classificação [REGRESSÃO] vs
   [PRÉ-EXISTENTE] rodando `git log -p --follow -- <arquivo>` ou
   `git show <commit>:<arquivo>` para ver o estado antes do diff atual —
   não confie cegamente na classificação que o agente individual deu,
   verifique.
3. Ordenar por: (a) severidade, (b) se é regressão (regressões introduzidas
   agora pesam mais que problemas antigos, porque o usuário está prestes a
   commitar isso).
4. Produzir uma lista final de "bloqueadores para commit" (bugs/riscos que
   deveriam ser corrigidos antes) separada de "notas/débito técnico
   pré-existente" (registrar mas não bloquear).
5. Não editar nenhum arquivo — só reportar.
```

## 4. Achados preliminares (do meu reconhecimento, não é revisão completa)

Já vi o suficiente lendo o diff para adiantar 2 pontos que classificaria como prováveis bloqueadores, para os agentes aprofundarem:

- **`app.py`: `FLASK_DEBUG` default `True`** — antes deste diff o código tinha `app.run(debug=False, ...)` fixo. Agora, se ninguém setar `FLASK_DEBUG=0` no ambiente de produção, o servidor sobe com o debugger do Werkzeug ativo. Isso é uma **regressão de segurança real**, não teórica — mesmo rodando em localhost, qualquer coisa que exponha a porta (túnel, proxy reverso mal configurado, `ngrok`) vira RCE.
- **`agents/synthesizer.py`: `readme[:5000]` hardcoded, não lê de `core.CONFIG`** — não é regressão de segurança, mas é uma duplicação de "fonte da verdade" que o diff introduziu (o valor certo por coincidência, mas o mecanismo é frágil).

O resto (path traversal em `delete_analysis`, XSS via `marked.parse` sem sanitização) já existia antes deste diff — vale reportar porque o diff toca a mesma área, mas não são regressões desta mudança específica.

## 5. Depois dos relatórios

Com a lista final de bloqueadores vs. débito técnico pré-existente, a decisão de commitar (ou corrigir antes) é sua. Posso, se quiser, aplicar os fixes que forem consenso (ex.: `FLASK_DEBUG` default `False`) antes do commit — mas isso é um passo separado, fora do escopo deste plano de revisão.
