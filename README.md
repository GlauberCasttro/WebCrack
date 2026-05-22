# WebCrack — Deep GitHub Analyzer

Analisa repositórios GitHub em profundidade usando um pipeline multi-agente com streaming via Groq LLM.

## Como funciona

1. Busque um repositório pelo nome, `owner/repo` ou URL do GitHub
2. Clique em **Analisar** — o pipeline coleta README, árvore de arquivos e conteúdo relevante
3. Leia a análise gerada em tempo real (markdown progressivo)
4. Use o **Chat** ao lado para perguntar qualquer coisa sobre o repo

## Pipeline de agentes

```
Decomposer → Explorer → Planner → Fetcher → Synthesizer
```

| Agente | Responsabilidade |
|---|---|
| **Decomposer** | Interpreta a intenção da query |
| **Explorer** | Mapeia diretórios relevantes via GitHub API |
| **Planner** | Decide quais arquivos ler |
| **Fetcher** | Busca o conteúdo dos arquivos |
| **Synthesizer** | Gera a resposta com o LLM |

## Stack

- **Backend**: Python + Flask
- **LLM**: Groq — `llama-3.3-70b-versatile`
- **Streaming**: Server-Sent Events (SSE)
- **Frontend**: HTML/CSS/JS vanilla + marked.js

## Instalação

```bash
# Clone o repo
git clone https://github.com/GlauberCasttro/WebCrack.git
cd WebCrack

# Crie o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instale as dependências
pip install -r requirements.txt

# Configure as variáveis de ambiente
cp .env.example .env
# Edite .env com suas chaves
```

## Variáveis de ambiente

```env
GROQ_API_KEY=sua_chave_aqui        # obrigatório
GITHUB_TOKEN=seu_token_aqui        # opcional (evita limite de 60 req/h)
```

- **GROQ_API_KEY**: obtenha em [console.groq.com](https://console.groq.com)
- **GITHUB_TOKEN**: gere em GitHub → Settings → Developer settings → Personal access tokens

## Rodando

```bash
./run.sh
# ou
python3 app.py
```

Abre automaticamente em `http://localhost:5000`.
