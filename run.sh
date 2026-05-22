#!/bin/bash

# Verifica se o ambiente virtual existe
if [ ! -d ".venv" ]; then
    echo "Erro: Ambiente virtual (.venv) não encontrado."
    echo "Certifique-se de que o ambiente foi criado corretamente."
    exit 1
fi

# Ativa o ambiente e executa o app
echo "Ativando ambiente virtual e iniciando o Analyzer..."
source .venv/bin/activate
python3 app.py
