---
name: agent-team-routing
description: |
  Monta e despacha equipes de subagentes reais para tarefas que abrangem vários
  arquivos ou exigem mais de uma perspectiva. Verifica quais tipos de agente
  realmente existem antes de despachar, dimensiona a equipe ao tamanho do
  trabalho, e exige verificação adversarial dos achados. Use sempre que o
  usuário pedir revisão ampla, auditoria de segurança, refatoração cross-module,
  investigação de bug em código desconhecido, ou mencionar swarm, orquestração,
  equipe de agentes, paralelizar, fan-out, ou "manda vários agentes". Use
  também quando a tarefa claramente exigir perspectivas independentes (correção
  + segurança + performance) mesmo que o usuário não peça delegação
  explicitamente — e use para decidir NÃO delegar quando o trabalho for pequeno.
---

# Roteamento de equipes de agentes

## Por que esta skill existe

Skills de orquestração apodrecem de um jeito específico e silencioso: elas gravam
nomes de agente no texto (`v3-queen-coordinator`, `security-implementer`) e, meses
depois, esses tipos não existem mais — ou nunca existiram. O despacho não dá erro.
Ele simplesmente não acontece, ou cai num agente genérico, e o relatório volta
parecendo legítimo.

O antídoto é inverter a ordem: **descubra o elenco disponível primeiro, escale
depois**. Um nome de agente é um fato sobre o ambiente atual, não uma constante
que se possa escrever num documento.

## Passo 1 — Decidir se vale delegar

Delegar custa: cada subagente relê contexto que você já tem. O ganho aparece
quando o trabalho é **largo** (muitos arquivos) ou **plural** (várias perspectivas
independentes sobre o mesmo material).

Não delegue para: edição de arquivo único, correção de 1–2 linhas, ajuste de
config, mudança de documentação, ou perguntas que você responde lendo um arquivo.
Nesses casos a resposta certa desta skill é "faça direto" — e dizer isso em voz
alta é um resultado válido, não uma falha.

Delegue quando houver pelo menos um destes:
- o material não cabe confortavelmente em uma leitura (3+ arquivos substanciais)
- a mesma mudança precisa ser julgada por lentes que se contradizem (correção vs.
  performance vs. segurança)
- há um achado que você quer ver alguém **tentar derrubar** antes de reportar
- a busca é ampla e você só precisa da conclusão, não do despejo de arquivos

## Passo 2 — Verificar o elenco antes de escalar

Antes de escrever qualquer prompt, descubra o que existe. Duas fontes:

```bash
# agentes definidos no projeto
find .claude/agents -name "*.md" 2>/dev/null | sed 's|.claude/agents/||;s|\.md$||' | sort
```

E a lista de tipos disponíveis no ambiente, que aparece na descrição da ferramenta
`Agent` — ela inclui agentes de plugin (`feature-dev:*`, `pr-review-toolkit:*`,
`code-modernization:*`) que não têm arquivo em `.claude/agents/`.

Um tipo desconhecido normalmente não falha alto: ele vira um agente genérico com o
prompt que você passou. Isso é pior que um erro, porque parece ter funcionado. Se
um tipo que você queria não existir, escolha o mais próximo que existe e **diga ao
usuário qual substituição você fez** — a transparência aqui é o que impede a skill
de apodrecer de novo.

Quando nenhum tipo especializado servir, `general-purpose` com um prompt bem
escrito costuma render mais que um tipo especializado com prompt vago. O prompt
carrega mais peso que o rótulo.

## Passo 3 — Dimensionar a equipe ao trabalho

O número de agentes sai do tamanho do material, nunca de um número bonito. Equipes
grandes em bases pequenas produzem relatórios redundantes que você depois precisa
deduplicar na mão.

| Tamanho do trabalho | Equipe | Observação |
|---|---|---|
| 1–2 arquivos, mudança localizada | 0 — faça direto | delegar aqui é puro custo |
| 3–8 arquivos, uma dimensão | 1–2 | ex.: um explorador + um revisor |
| diff médio, múltiplas dimensões | 3–4 | uma dimensão por agente |
| auditoria ampla / base desconhecida | 4–6 | acrescente verificadores |
| migração ou varredura em massa | 6+ | só quando há itens independentes de verdade |

Passar de 6 exige justificativa concreta: itens que não se tocam e que realmente
podem correr em paralelo. "Quero ser minucioso" não é justificativa — minúcia vem
de verificação adversarial, não de contagem de agentes.

## Passo 4 — Escolher a topologia

**Fan-out** — cada agente ataca uma dimensão independente e reporta para você, que
sintetiza. É o padrão certo para revisão, auditoria e pesquisa. Use quando os
agentes não precisam do resultado um do outro.

**Pipeline** — `A → B → C`, cada um recebe a saída do anterior. Use quando há
dependência real: arquitetura antes de implementação, implementação antes de teste.
O custo é latência: o pipeline inteiro anda na velocidade do estágio mais lento.

**Supervisor** — você mantém o plano e despacha em rodadas, reavaliando entre elas.
Use quando o próprio escopo é incerto e cada rodada muda a próxima.

Na dúvida, fan-out. Dependência sequencial é mais rara do que parece, e um pipeline
onde não havia dependência é só um fan-out lento.

## Passo 5 — Escrever prompts que rendem

Um subagente não vê esta conversa. Ele acorda sabendo apenas o que você escreveu.
Prompts vagos produzem relatórios vagos, e essa é a causa mais comum de delegação
decepcionante — não a escolha do tipo de agente.

Cada prompt precisa carregar:

- **O comando exato para começar.** `git -C <caminho> diff -- <arquivos>`, não
  "olhe as mudanças". O agente não sabe seu diretório nem o que está pendente.
- **Escopo explícito, com as exclusões.** "Só `core.py` e `app.py`; ignore o
  template, outro agente cuida disso." Sem isso, dois agentes revisam a mesma coisa.
- **O que devolver, e em que forma.** O texto final do agente É o retorno — ele não
  conversa com o usuário. Peça markdown estruturado, sem preâmbulo.
- **Uma trava contra achado inventado.** Exija cenário concreto de falha (entrada X
  → comportamento errado Y) e marcação `CONFIRMADO` (li o código e tracei o caminho)
  vs. `SUSPEITA`. Sem isso, revisores de LLM produzem achados plausíveis e falsos.
- **Regressão vs. pré-existente**, quando o alvo é um diff. É o eixo mais útil de
  uma revisão de mudança, e o que mais se perde sem instrução explícita.
- **Limites de escrita.** Revisão é leitura: diga "não edite nenhum arquivo".

Nomeie os agentes (`name: "revisor-backend"`). O nome vira endereço: dá para
cobrar o relatório depois com `SendMessage`, e para encerrar com `TaskStop` sem
ter guardado id nenhum.

Dispare todos numa única mensagem, com múltiplas chamadas de ferramenta, para que
rodem de fato em paralelo.

## Passo 6 — Verificar antes de reportar

Achado não verificado é rumor. Para qualquer conclusão que vá virar decisão do
usuário, rode um segundo passe cuja tarefa é **derrubá-la**, não confirmá-la:

> "Tente refutar: <achado>. Assuma que está errado até provar o contrário.
>  Se não conseguir um cenário concreto de falha, marque como refutado."

Quando o achado pode falhar de mais de um jeito, dê a cada verificador uma lente
distinta (corretude, segurança, reprodutibilidade) em vez de três céticos idênticos
— diversidade acha o que redundância não acha.

## Passo 7 — Sintetizar, e ser honesto sobre buracos

Você é quem entrega, não os agentes. Ao consolidar:

- diga o que foi **confirmado**, o que ficou **suspeita**, e o que **ninguém olhou**
- se um agente não voltou, diga isso — silêncio de agente não é ausência de problema
- se você substituiu um tipo de agente por outro, registre a substituição
- não repasse o relatório bruto: o usuário pediu a conclusão, não o transcript

## Anti-padrões

**Gravar nomes de agente como se fossem permanentes.** É o que mata skills de
orquestração. Verifique no Passo 2, sempre.

**Escalar por número.** "15 agentes" não é arquitetura. Num projeto de mil linhas,
quinze agentes escrevem quinze versões do mesmo parágrafo.

**Tratar ocioso como concluído.** Um agente pode sinalizar idle sem ter entregue
relatório. Se o relatório não chegou, cobre — não presuma, e nunca invente o que
ele teria dito.

**Pipeline por estética.** Encadear estágios que não dependem entre si só adiciona
espera.

**Delegar o que você já sabe.** Se você acabou de ler o arquivo, revisar você mesmo
é mais rápido e mais preciso que explicar o contexto todo para um agente.

## Exemplo curto

Tarefa: *"revisa o que está mexido antes de eu commitar"* — 4 arquivos modificados,
Python + template.

1. Vale delegar? Sim: 4 arquivos, dimensões que se contradizem (corretude vs. segurança).
2. Elenco: `find .claude/agents` mostra o que há; a lista do `Agent` acrescenta
   `pr-review-toolkit:code-reviewer`, `code-modernization:security-auditor`,
   `feature-dev:code-reviewer`.
3. Tamanho: diff médio, 3 dimensões → 3 agentes.
4. Topologia: fan-out — as dimensões não dependem entre si.
5. Prompts: cada um recebe seu `git diff -- <arquivos>`, escopo com exclusões,
   pedido de `CONFIRMADO`/`SUSPEITA` e `REGRESSÃO`/`PRÉ-EXISTENTE`, e proibição de editar.
6. Verificação: cada achado de severidade alta vai para um cético que tenta refutá-lo.
7. Síntese: lista consolidada por severidade, com o que ficou sem cobertura.
