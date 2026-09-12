# Plano de revisão — mudanças não commitadas no WebCrack

Não executei nada disso — nem `Agent`, nem edições. Isto é só o plano, seguindo a skill
`agent-team-routing`. Abaixo, os 7 passos aplicados a este caso concreto.

## Passo 1 — Vale delegar?

Sim. Você tem 4 arquivos tocados (`core.py`, `app.py`, `agents/synthesizer.py`,
`templates/index.html`), duas linguagens (Python + JS embutido no template), e pelo
menos três lentes que se contradizem: corretude de backend, segurança, e corretude de
frontend. Isso é exatamente o padrão "diff médio, múltiplas dimensões" — não é
1–2 arquivos nem correção pontual, então delegar compensa.

Já olhei o diff (`git diff --stat`): 76 inserções / 67 remoções, nada gigante, mas com
uma reescrita real de lógica em `core.py` (a função `get_file_tree`) e uma mudança de
comportamento em `app.py` (flag de debug). Isso não é ruído — é material que merece
mais de um par de olhos.

## Passo 2 — Elenco disponível (verificado agora, não presumido)

```bash
find .claude/agents -name "*.md" | sed 's|.claude/agents/||;s|\.md$||' | sort
```
retornou só stubs genéricos do ruflo/claude-flow: `consensus/*`, `sparc/*`,
`swarm/*`, `core/planner`, `testing/*`. Nenhum é um revisor de código de verdade —
são coordenadores de consenso distribuído e fases SPARC, sem relação com este projeto.
**Não vou usar nenhum desses.**

A lista nativa da ferramenta `Agent` (a que importa) tem, entre os relevantes:
`pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter`,
`feature-dev:code-reviewer`, `feature-dev:code-explorer`,
`code-modernization:security-auditor`, `general-purpose`, `Explore`.

**Achado mais importante deste passo:** esta sessão já tem três teammates ativos e
endereçáveis por `SendMessage` — `reviewer-backend`, `reviewer-frontend`,
`reviewer-security` (aparecem no reminder de "Other agents active in this session").
Os nomes batem quase perfeitamente com as três dimensões que eu escolheria do zero.
Isso muda a execução real: em vez de `Agent(...)` criando processos novos, o
despacho vira `SendMessage({to: "reviewer-backend", message: "<prompt abaixo>"})`
para cada um — reaproveitando agentes que talvez já tenham contexto de sessão, em
vez de duplicar trabalho com cópias novas. Registro isso como a substituição/decisão
de roteamento deste plano: **uso os três teammates existentes, não novos `Agent()`**,
e caio para `general-purpose` só se algum deles não responder.

## Passo 3 — Tamanho da equipe

Diff médio, 3 dimensões independentes → **3 agentes** (a tabela da skill recomenda
1–2 para 3–8 arquivos numa dimensão, 3–4 para diff médio com múltiplas dimensões;
aqui ficam 4 arquivos mas 3 dimensões reais, então 3 agentes é o número certo, não 6).
Acrescento **1 verificador adversarial** pontual só para o achado de maior severidade
que aparecer (ver Passo 6) — não uma segunda rodada completa.

## Passo 4 — Topologia

**Fan-out** para os três revisores: nenhum depende do resultado do outro, cada um
ataca um recorte de arquivo diferente. Isso casa com a orientação da skill ("na
dúvida, fan-out").

**Pequeno pipeline de 1 elo** só para a verificação: o cético de segurança só entra
depois que `reviewer-security` reportar, porque ele precisa de um achado concreto
para tentar derrubar — não faz sentido rodá-lo em paralelo sem alvo.

## Passo 5 — Os prompts (o que cada agente receberia)

### → `reviewer-backend` (corretude — `core.py` + `agents/synthesizer.py`)

```
Escopo: SOMENTE core.py e agents/synthesizer.py. Não olhe app.py nem
templates/index.html — outros agentes cobrem esses.

Comece com:
  git -C /Users/glaubercastro/Repositorios/WebCrack diff -- core.py agents/synthesizer.py
Depois leia os arquivos inteiros para ter o contexto ao redor do diff:
  cat core.py agents/synthesizer.py

Pontos que quero que você julgue com atenção (não são as únicas coisas a olhar,
mas não pode deixar de cobrir):

1. get_file_tree foi reescrita para usar a API de "git trees" recursiva do GitHub
   em vez da exploração sequencial antiga. Ela tenta main, cai para master, e só
   se ambas falharem usa o método antigo como fallback. Essa lógica de fallback
   está correta? O que acontece se o repo usa um default_branch diferente de
   main/master (ex.: "develop") — o parâmetro default_branch vem de
   fetch_repo_context via repo_info.get("default_branch"), então na teoria não
   deveria cair no hardcoded "main"/"master" nunca, exceto no fallback de erro.
   Confirme se esse raciocínio está certo lendo fetch_repo_context.
2. CONFIG["max_tokens"] subiu de 2048 para 4096 e o comentário antigo dizia que
   2048 era para evitar erro 413 do Groq. Isso foi removido/ignorado — é uma
   regressão de correção deliberada ou um esquecimento? Veja se há alguma
   validação de tamanho de payload em outro lugar que compense.
3. CONFIG["readme_preview_chars"] subiu de 2000 para 5000, mas
   agents/synthesizer.py também mudou seu slice hardcoded de readme[:3000] para
   readme[:5000] — isso bate com o novo valor de CONFIG, só que como literal
   duplicado, não como referência a CONFIG. Isso é uma dívida de manutenção real
   (drift futuro) — marque como achado de qualidade, não como bug hoje.
4. output_dir passou de "analises" (relativo) para um caminho absoluto derivado
   de __file__. Verifique se algum outro lugar do código ainda assume o caminho
   relativo antigo (grep por "analises" e por CONFIG["output_dir"] no repo todo).

Formato de saída: lista de achados, cada um com:
- CONFIRMADO (você leu o código e traçou o caminho) ou SUSPEITA (não confirmou)
- REGRESSÃO (o diff piorou algo que funcionava) ou PRÉ-EXISTENTE (já era assim)
- cenário concreto: entrada X → comportamento errado Y (nada de "pode causar
  problemas" sem exemplo)

Não edite nenhum arquivo. Isto é revisão, não correção.
```

### → `reviewer-security` (segurança — `app.py` + rede em `core.py`)

```
Escopo: app.py inteiro, e em core.py só as partes que tocam rede
(_get_json, get_file_tree, fetch_repo_context) e o uso de GROQ_API_KEY. Não
julgue a lógica de negócio de get_file_tree — isso é do reviewer-backend.

Comece com:
  git -C /Users/glaubercastro/Repositorios/WebCrack diff -- app.py core.py
  cat app.py
  find /Users/glaubercastro/Repositorios/WebCrack -maxdepth 1 -iname "run.sh" -o -iname "Procfile" -o -iname "Dockerfile"

O achado que mais me preocupa e que você precisa investigar a fundo:

1. app.py agora tem `debug = _env_flag("FLASK_DEBUG", default=True)` e
   `app.run(debug=debug, ...)`. Antes era hardcoded `debug=False`. Um debug=True
   por padrão liga o debugger interativo do Werkzeug, que permite execução de
   código arbitrário via o console web SE o app for alcançável e o PIN não
   estiver protegido/for vazado. Isso é uma regressão real de postura de
   segurança (o padrão anterior era o seguro; agora o padrão é o inseguro).
   Antes de marcar como CONFIRMADO alta severidade, verifique:
   - qual host o Flask usa aqui (app.run não passa host= — confirme se o
     default do Flask é 127.0.0.1, o que limitaria a exposição a acesso local)
   - se run.sh ou algo no repo seta FLASK_DEBUG explicitamente em algum fluxo
     "de produção" real, ou se isso só roda localmente hoje
   Dê a severidade real, não a teórica.
2. PORT agora vem de os.getenv("PORT", "5000") — isso por si só não é um
   problema de segurança, mas combine com o ponto acima: se PORT for exposto
   publicamente (ex.: em container/PaaS) E debug ficar True, o cenário de
   exposição fica muito mais plausível. Diga se essas duas mudanças juntas
   mudam sua avaliação do achado 1.
3. get_file_tree monta a URL com
   f"https://api.github.com/repos/{full_name}/git/trees/{default_branch}?recursive=true".
   full_name e default_branch vêm de dados de repositório do GitHub — rastreie
   de onde full_name entra no sistema (a rota /analyze em app.py) e se há
   validação de formato antes de cair nessa interpolação. Isso é injeção de URL
   ou está adequadamente restrito ao formato "owner/repo"?
4. Confirme que GROQ_API_KEY nunca é logado, nunca aparece em mensagens de erro
   devolvidas ao cliente (UserFacingError e afins), e não mudou de tratamento
   neste diff.

Formato de saída: mesmo padrão do reviewer-backend — CONFIRMADO/SUSPEITA,
REGRESSÃO/PRÉ-EXISTENTE, cenário concreto, sem edição de arquivos.
```

### → `reviewer-frontend` (corretude — `templates/index.html`)

```
Escopo: SOMENTE templates/index.html, e só as funções doAnalyze e doChat
(região do diff). Não julgue app.py nem core.py.

Comece com:
  git -C /Users/glaubercastro/Repositorios/WebCrack diff -- templates/index.html
Depois leia as funções inteiras no arquivo (não só o trecho do diff) para
confirmar o comportamento antes/depois:
  grep -n "function doAnalyze\|function doChat" templates/index.html

O que aconteceu: o código removia caractere por caractere de uma fila
(tokenQueue + drainChars com setTimeout) para simular "digitação" do streaming;
o diff elimina essa fila inteira e passa a acumular direto em accText, com um
setInterval de 80ms fazendo o flush visual, e o render final acontece no
.then() da fetch lendo sessions[...].analysis diretamente.

1. Trace a corrida entre o setInterval (renderTimer) e o .then(): quando a
   fetch conclui, o .then() já dá clearInterval e escreve o innerHTML final via
   marked.parse(sessions[currentKey].analysis) — isso lê o texto acumulado
   completo, não o accText do timer. Isso está correto (não perde texto), ou
   existe uma janela onde o setInterval ainda dispara depois do clearInterval
   por causa de um tick já enfileirado? Dê um cenário concreto se achar um bug,
   não "pode ter race condition" genérico.
2. O innerHTML final é montado com marked.parse() a partir de texto que veio de
   um LLM analisando o README de um repositório de terceiros — e o
   readme_preview_chars subiu de 2000/3000 para 5000 neste mesmo conjunto de
   mudanças (ver diff de core.py/agents/synthesizer.py, que outro agente está
   revisando). O padrão marked.parse(...) → innerHTML sem sanitização
   adicional já existia antes deste diff (não é uma regressão de código), mas
   a superfície de conteúdo de terceiros que chega até ele cresceu. Marque isso
   como PRÉ-EXISTENTE no padrão, mas sinalize o aumento de superfície como
   observação relevante para quem for decidir sobre esse commit.
3. Confirme que não sobrou nenhuma referência morta a tokenQueue/drainTimer em
   outro ponto do arquivo (grep no arquivo inteiro, não só no diff).

Formato de saída: mesmo padrão — CONFIRMADO/SUSPEITA, REGRESSÃO/PRÉ-EXISTENTE,
cenário concreto, sem edição de arquivos.
```

## Passo 6 — Verificação adversarial

Se `reviewer-security` voltar com o achado do `FLASK_DEBUG` default `True` marcado
como CONFIRMADO e severidade alta, esse é o único achado deste diff que eu não
reportaria sem uma segunda passada tentando derrubá-lo — é o tipo de coisa que
parece grave na teoria e pode ser irrelevante na prática (ex.: se o app só roda
localmente hoje). Dispararia um quarto agente, com uma lente diferente
(reprodutibilidade, não segurança de novo):

```
→ novo agente, general-purpose, nome "verificador-debug-flag"
(só dispara DEPOIS que reviewer-security responder)

Tente refutar: "app.py agora liga debug=True por padrão via FLASK_DEBUG,
expondo o debugger interativo do Werkzeug." Assuma que está errado até provar
o contrário.

Verifique concretamente:
  grep -n "app.run\|host=" /Users/glaubercastro/Repositorios/WebCrack/app.py
- Flask sem host= explícito binda em 127.0.0.1 por padrão — isso por si só já
  limita a exposição a acesso local da máquina que roda o processo.
- Existe algum Dockerfile, run.sh, ou script de deploy no repo que passe
  host="0.0.0.0" ou exponha a porta publicamente? Se não existir nenhum, o
  cenário de exploração real hoje é: alguém com acesso à própria máquina/rede
  local do desenvolvedor. Isso ainda é uma regressão de postura (o padrão
  seguro virou inseguro), mas a severidade é bem menor que "RCE remoto".

Se não conseguir um cenário concreto de exposição além de acesso local, marque
REFUTADO PARA SEVERIDADE ALTA e proponha a severidade real (provavelmente
"correção recomendada, mas não bloqueante", já que trocar o default por False
é uma correção de uma linha e sem custo).

Não edite nenhum arquivo.
```

## Passo 7 — Como eu sintetizaria (quando os relatórios voltarem)

- Uma lista única, por severidade, cruzando os três relatórios — sem repassar o
  texto bruto de cada agente.
- Cada achado etiquetado REGRESSÃO ou PRÉ-EXISTENTE, porque é o que você pediu
  explicitamente e é o eixo mais fácil de perder numa síntese apressada.
- Se algum dos três teammates não responder, eu digo isso explicitamente em vez
  de presumir "sem achados" — silêncio de agente não é aprovação.
- O achado do `FLASK_DEBUG` chega com o resultado da verificação já embutido
  (severidade ajustada, não a teórica), não como dois achados separados.
- Fecho com o que **ninguém olhou**: por exemplo, se nenhum dos três prompts
  cobrir tratamento de erro/exceções (try/except que engole falha
  silenciosamente), eu digo isso como buraco de cobertura, não deixo implícito.

## Resumo da decisão de roteamento

| Dimensão | Quem eu acionaria | Como |
|---|---|---|
| Corretude backend (`core.py`, `agents/synthesizer.py`) | `reviewer-backend` (já ativo) | `SendMessage` |
| Segurança (`app.py`, rede em `core.py`) | `reviewer-security` (já ativo) | `SendMessage` |
| Corretude frontend (`templates/index.html`) | `reviewer-frontend` (já ativo) | `SendMessage` |
| Verificação adversarial do achado crítico de segurança | novo `general-purpose` | `Agent`, só se necessário, depois do passo anterior |

Nenhum agente do `.claude/agents` local (`consensus/*`, `sparc/*`, `swarm/*`) entra
neste plano — são stubs de coordenação genérica, sem relação com revisão de código
Python/JS deste projeto.
