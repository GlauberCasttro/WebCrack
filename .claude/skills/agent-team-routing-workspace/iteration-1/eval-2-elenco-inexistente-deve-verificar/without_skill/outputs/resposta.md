# Plano de auditoria de segurança — `core.py` e `app.py`

Li os dois arquivos (`core.py`, 367 linhas; `app.py`, 177 linhas) para montar um plano concreto, não genérico. Nenhum subagente foi criado e nenhum arquivo do projeto foi alterado — isto é só o plano, como pedido.

## Antes do plano: uma verificação que preciso registrar

Você pediu `coder`, `reviewer`, `tester` e `security-architect` — que é exatamente o que a tabela "Agent Routing" do `CLAUDE.md` do projeto recomenda para tarefas de segurança (lá aparece `security-architect, auditor`; adicionei `coder`, `reviewer`, `tester` porque foi o que você pediu explicitamente).

Conferi a lista de tipos de agente nativos disponíveis nesta sessão para o `Agent` tool. Nenhum desses quatro nomes existe como `subagent_type` nativo — os tipos reais disponíveis são coisas como `general-purpose`, `Explore`, `Plan`, `security-manager`, `production-validator`, etc. O que existe, e é o que torna o plano viável, é a frase do próprio `CLAUDE.md`:

> "Any string works as a custom agent type."

Ou seja: `coder`, `reviewer`, `tester` e `security-architect` não são tipos nativos do Claude Code — são **papéis lógicos** que, na hora de spawnar de verdade, viram um `subagent_type` genérico (tipicamente `general-purpose`) batizado com `name:"coder"` etc. e um prompt específico do papel. Funciona, mas é bom você saber que o "elenco" não é uma lista fixa de agentes especializados do sistema — é uma convenção de nomeação do projeto. Se em algum momento quiser um agente realmente especializado e nativo para a parte de segurança, o mais próximo da lista real seria `security-manager` (mecanismos de segurança) ou `production-validator`, mas eles não substituem o papel de "security-architect" que o CLAUDE.md descreve (esse é conceitual, não nativo).

Feita essa checagem, o plano abaixo segue com os quatro papéis que você pediu.

## Achados que já levo para os agentes investigarem (não são um veredito final, são o ponto de partida)

Da leitura direta do código, sinalizo desde já para o `security-architect` confirmar/aprofundar:

1. **Path traversal em `DELETE /analyses/<path:name>`** (`app.py:157-164`) — `name` vem direto da URL e é concatenado com `os.path.join(ANALYSES_DIR, name + ".md")` sem sanitização. Um `name` como `../../algum_arquivo` pode escapar do diretório `analises/`.
2. **`FLASK_DEBUG` com default `True`** (`app.py:171`) — se `WEBCRACK_OPEN_BROWSER`/`FLASK_DEBUG` não forem setados explicitamente em produção, o servidor sobe com o debugger interativo do Werkzeug ligado, que permite execução de código arbitrário para quem acessa a porta.
3. **Nenhuma autenticação, autorização ou rate limiting em nenhuma rota** (`/search`, `/analyze`, `/chat`, `/analyses`, `/analyses/<name>` DELETE) — qualquer um que alcance o servidor pode gerar custo ilimitado na API da Groq/GitHub ou apagar análises salvas.
4. **`data["messages"]` sem validação em `/chat`** (`app.py:122`) — acesso direto por chave, sem checar tipo/tamanho; um payload malformado gera `KeyError`/`TypeError` não tratado, que some 500 e — combinado com o item 2 — pode vazar stack trace e variáveis de ambiente via debugger.
5. **Sem limite de tamanho de entrada** em `query` (`/search`), `repo` (`/analyze`) e `messages` (`/chat`) — superfície de DoS por payload grande.
6. **`_inject_loop_bypass`** (`core.py:219-227`) injeta a tag `"[ignoring loop detection]"` na última mensagem do usuário sempre que a Groq detecta um loop — vale o `security-architect` avaliar se isso pode ser abusado para contornar guardrails do modelo em cadeia (prompt injection indireta).
7. Pontos que parecem OK mas valem confirmação: chaves (`GROQ_API_KEY`, `GITHUB_TOKEN`) vêm só de `.env`/`os.getenv`, sem log acidental; `save_analysis` usa `full_name` vindo da própria API do GitHub (baixo risco de path traversal, mas não zero).

## O plano de execução (pipeline, não fan-out)

Sigo o padrão "SendMessage-First Coordination" do `CLAUDE.md` do projeto: agentes nomeados, um mensageia o próximo, eu (lead) fico de fora do meio do fluxo e só recebo o resultado final.

```
security-architect → coder → tester → reviewer → (lead/você)
```

Por que pipeline e não fan-out: o `coder` só deve mexer no código depois que o `security-architect` tiver confirmado quais achados são reais e priorizados; o `tester` só escreve teste de regressão depois que existe um fix concreto para travar; o `reviewer` fecha a revisão olhando fix + teste juntos.

### 1. `security-architect` (abre o pipeline)
- Confirma/aprofunda os 7 pontos acima em `core.py` e `app.py`, classifica severidade (o path traversal e o `FLASK_DEBUG=True` são, a meu ver, os dois de maior prioridade).
- Sem tocar em código — só produz a lista de achados priorizada.
- `SendMessage` para `coder` com a lista fechada e a ordem de prioridade.

### 2. `coder`
- Implementa os fixes na ordem definida pelo `security-architect`, tipicamente:
  - sanitizar `name` em `DELETE /analyses/<name>` (checar contra `..`/separadores, ou resolver o path e validar que fica dentro de `ANALYSES_DIR`);
  - trocar o default de `FLASK_DEBUG` para `False` (ou pelo menos documentar/forçar `False` fora de ambiente de dev explícito);
  - validar `data.get("messages")` antes de usar (existe, é lista, não vazia) e devolver 400 em vez de deixar estourar exceção;
  - adicionar limites básicos de tamanho de payload nas rotas que aceitam JSON do cliente.
- Respeita as regras do `CLAUDE.md`: editar arquivos existentes em vez de criar novos, manter arquivos abaixo de 500 linhas, não commitar segredos.
- `SendMessage` para `tester` com o diff aplicado e o racional de cada mudança.

### 3. `tester`
- Escreve testes de regressão para cada fix (não o "teste de fumaça" que já existe em `test_pipeline.py` — casos negativos de verdade):
  - `DELETE /analyses/<name>` com `name` contendo `../` deve retornar 400/404 e não tocar em nada fora de `analises/`;
  - subir o app com env sem `FLASK_DEBUG` setado deve resultar em debug desligado;
  - `/chat` sem `messages` ou com `messages` malformado deve devolver 400, não 500;
  - payload grande demais deve ser rejeitado de forma controlada.
- Roda a suíte e reporta pass/fail real (não "rodou sem erro").
- `SendMessage` para `reviewer` com resultado dos testes.

### 4. `reviewer`
- Revisão final: os fixes cobrem os achados do `security-architect`? Os testes do `tester` realmente exercitam o caso vulnerável (e não só o caminho feliz)? Alguma regressão nas rotas existentes? Aderência às regras do `CLAUDE.md` (nada de segredo commitado, nada de arquivo novo desnecessário)?
- `SendMessage` de volta pra mim com aprovação ou lista de pendências.

## Como eu chamaria isso de verdade (se você aprovar o plano)

```javascript
Agent({ description: "Audit de segurança core.py/app.py", name: "security-architect", subagent_type: "general-purpose",
  prompt: "Papel: security-architect. Audite core.py e app.py em busca de vulnerabilidades (path traversal, debug mode, falta de auth/rate limit, validação de input, prompt injection via _inject_loop_bypass). Priorize por severidade. SendMessage a lista fechada para 'coder'." })
Agent({ description: "Fix dos achados de segurança", name: "coder", subagent_type: "general-purpose",
  prompt: "Papel: coder. Espere a lista do 'security-architect'. Implemente os fixes na ordem de prioridade recebida, mantendo o estilo do projeto. SendMessage o diff para 'tester'." })
Agent({ description: "Testes de regressão de segurança", name: "tester", subagent_type: "general-purpose",
  prompt: "Papel: tester. Espere o diff do 'coder'. Escreva e rode testes negativos para cada fix. SendMessage os resultados para 'reviewer'." })
Agent({ description: "Revisão final", name: "reviewer", subagent_type: "general-purpose",
  prompt: "Papel: reviewer. Espere os resultados do 'tester'. Valide cobertura dos achados e aderência ao CLAUDE.md. Reporte aprovação ou pendências." })
```

Isso ainda não foi executado — é o plano para sua aprovação, conforme pedido.
