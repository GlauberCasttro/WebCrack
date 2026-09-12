# Plano de auditoria de segurança — core.py e app.py

## Aviso importante antes do plano: os 4 nomes pedidos não existem

Você pediu `coder`, `reviewer`, `tester` e `security-architect` porque é assim que
o `CLAUDE.md` do projeto rotula os papéis nas tabelas "Agents" e "Agent Routing".
Conferi as duas fontes reais de tipos de agente disponíveis agora:

```bash
find .claude/agents -name "*.md" | sed 's|.*/.claude/agents/||;s|\.md$||' | sort
```
→ só existem agentes de consenso/swarm (`byzantine-coordinator`, `raft-manager`,
`security-manager` de protocolos de consenso, etc.), `core/planner`, os quatro do
SPARC, e `testing/production-validator` / `testing/tdd-london-swarm`. Nenhum
`coder`, `reviewer`, `tester` ou `security-architect`.

Na lista de tipos que a própria ferramenta `Agent` expõe neste ambiente, também
não há `coder`, `reviewer`, `tester` nem `security-architect` — nem como tipo
nativo, nem como agente de plugin.

Ou seja: o `CLAUDE.md` documenta um elenco que **não está instalado neste
ambiente**. É exatamente o padrão que a skill `agent-team-routing` existe para
pegar — nome de agente gravado em doc não é garantia de que o tipo existe. Vou
usar os substitutos mais próximos disponíveis e deixar a substituição explícita,
em vez de disparar um nome que cairia silenciosamente num agente genérico.

## Substituições propostas

| Pedido no CLAUDE.md | Não existe como | Substituto real usado | Por quê |
|---|---|---|---|
| `security-architect` | tipo de agente | `code-modernization:security-auditor` | É literalmente um revisor de segurança adversarial (OWASP Top 10, CWE, CVEs de dependência, secrets, injection) — o fit mais próximo que existe de verdade |
| `reviewer` | tipo de agente | `pr-review-toolkit:code-reviewer` | Revisa código contra convenções do projeto e `CLAUDE.md`, aponta bugs e violações de estilo — cobre a correção geral que ficaria fora do escopo puramente de segurança do security-auditor |
| `tester` | tipo de agente | `pr-review-toolkit:pr-test-analyzer` | Não "roda testes" (não existe agente que faça isso aqui), mas audita cobertura: se `test_pipeline.py` cobre os caminhos sensíveis (entrada não confiável, tratamento de erro) de `core.py`/`app.py` |
| `coder` | tipo de agente | `feature-dev:code-architect` | Também não existe um "coder" genérico. Numa auditoria (só leitura) o papel de coder não é escrever código — é traduzir cada achado confirmado em um patch concreto sugerido, sem aplicá-lo |

Se preferir, posso rodar só com 2 agentes (security-auditor + code-reviewer) e
pular tester/coder — dado que `core.py` (367 linhas) e `app.py` (177 linhas)
são pequenos, 4 agentes já é o teto da faixa "diff médio, múltiplas dimensões"
da skill (3–4 agentes). Sigo com os 4 porque você pediu explicitamente as 4
perspectivas.

## Passo 1 — Vale delegar?

Sim: são 2 arquivos, mas 3 dimensões independentes que se contradizem
(segurança vs. correção geral vs. cobertura de teste), e você quer o resultado
verificado antes de virar decisão — os dois critérios que a skill usa para
justificar delegação em vez de eu revisar sozinho.

## Passo 3 — Tamanho da equipe

544 linhas ao todo, 2 arquivos, 3 dimensões → **4 agentes** (o topo da faixa
"diff médio / múltiplas dimensões" da skill), mais uma rodada de verificação
sobre os achados de severidade alta. Não vou além disso — 544 linhas não
justificam uma equipe de 6+.

## Passo 4 — Topologia

**Fan-out**: os quatro agentes atacam o mesmo par de arquivos por lentes que
não dependem umas das outras. Eu sintetizo no final. Não uso pipeline porque
não há uma saída de um agente que o próximo precise consumir antes de começar.

## Equipe que eu de fato despacharia (fan-out, uma única mensagem)

1. **`sec-auditor`** — `code-modernization:security-auditor`
   Comando de partida: `git -C /Users/glaubercastro/Repositorios/WebCrack diff -- core.py app.py` (ou leitura direta se não houver diff pendente relevante — auditar o estado atual dos dois arquivos).
   Escopo: só `core.py` e `app.py`. Ignorar `templates/index.html` e `agents/synthesizer.py`.
   Buscar: injeção (comandos, path traversal, SSRF ao consultar GitHub), segredos hardcoded, validação de entrada nas fronteiras do sistema (regra explícita do `CLAUDE.md`), tratamento de erro que mascara falha de segurança, exposição de dados sensíveis em logs/respostas Flask.
   Retorno exigido: cada achado marcado `CONFIRMADO` (linha citada + cenário de exploração concreto) ou `SUSPEITA`. Proibido editar arquivos.

2. **`reviewer`** — `pr-review-toolkit:code-reviewer`
   Mesmo escopo (`core.py`, `app.py`), mesma proibição de edição.
   Foco: bugs de lógica, aderência às regras do `CLAUDE.md` (arquivos <500 linhas, validação de entrada), qualidade geral — não duplicar o que o security-auditor já cobre, mas sinalizar se algo de segurança escapar por má prática (ex.: exceção genérica engolindo erro).
   Retorno: mesma marcação `CONFIRMADO`/`SUSPEITA`.

3. **`test-coverage`** — `pr-review-toolkit:pr-test-analyzer`
   Escopo: `test_pipeline.py` vs. `core.py`/`app.py`.
   Foco: `test_pipeline.py` é hoje um script de fumaça (não assevera nada — isso já está registrado na minha memória do projeto), então a pergunta real é se os caminhos sensíveis identificados pelo security-auditor têm QUALQUER cobertura, nem que seja manual. Apontar os gaps mais críticos, não pedir suíte completa.
   Retorno: lista de caminhos sem cobertura, priorizada pelos achados `CONFIRMADO` do security-auditor (assim que estiverem prontos).

4. **`fix-drafter`** — `feature-dev:code-architect`
   Recebe os achados `CONFIRMADO` dos três anteriores.
   Produz: para cada achado confirmado, um patch sugerido em formato diff — só como texto no relatório, sem tocar nos arquivos do repositório.

## Passo 6 — Verificação adversarial

Todo achado `CONFIRMADO` de severidade alta (principalmente os do
`sec-auditor`) passa por uma segunda rodada: peço ao `reviewer` que tente
refutar cada um assumindo que está errado até provar o contrário — lente de
correção geral, diferente da lente de segurança que gerou o achado. Isso é
diversidade de lente, não duplicação, que é o que a skill pede no Passo 6.

## O que eu reportaria a você no final

- Lista de achados por severidade, cada um com `CONFIRMADO`/`SUSPEITA` e se
  sobreviveu à tentativa de refutação.
- Gaps de cobertura de teste ligados a cada achado confirmado.
- Patches sugeridos (não aplicados) para os achados confirmados.
- Registro explícito de que `security-architect`, `reviewer`, `tester` e
  `coder` do jeito que o `CLAUDE.md` nomeia **não existem neste ambiente**, e
  quais tipos reais usei no lugar — para você decidir se quer instalar agentes
  de projeto com esses nomes ou manter o `CLAUDE.md` como está sabendo que ele
  descreve um elenco aspiracional, não instalado.

**Nada disso foi disparado ainda** — isto é só o plano, como pedido. Se
aprovar, disparo os 4 agentes numa única mensagem em fan-out.
