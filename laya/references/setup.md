# Setup do Laya no PC (Windows)

Faça você mesmo; a skill não instala nada.

## 1. Instalar
```powershell
pip install laya
```
Python 3.10 ou mais novo. Se a carga do modelo travar, rode com `USE_TF=0` (o script já define isso).

## 2. Pasta de dados
Padrão: `~/.laya` (pasta `.laya` dentro do seu usuário). Para mudar:
```powershell
setx LAYA_HOME "D:\minha\pasta\laya"
```
Crie a estrutura com `python scripts/laya_call.py init`.

## 3. Primeiro teste (zero-shot)
```powershell
python scripts/laya_call.py new-task triagem-email < schema.json
'{"state": "Fui cobrado duas vezes em março, reembolsem."}' | python scripts/laya_call.py ask triagem-email
```
Na primeira vez o Laya baixa o checkpoint (cerca de 650 a 800 MB).

## 4. Treino
Notebook oficial no Kaggle (2x T4 grátis): link no README de https://github.com/NandhaKishorM/laya e na página do modelo.
1. `python scripts/laya_call.py export <tarefa>` gera `dataset.jsonl`.
2. Suba o dataset no Kaggle (de preferência como dataset privado).
3. Rode o notebook: treina, ajusta as temperaturas de calibração e envia ao seu Hub.
4. `python scripts/laya_call.py import-model <tarefa> <usuario/repo>`.
5. `python scripts/laya_call.py set-calibration <tarefa> < temperaturas.json`.

## 5. Token do Hugging Face (só se repositório privado)
Crie em Settings → Access Tokens e guarde com `huggingface-cli login` no seu terminal. Nunca cole no chat.

## Pontos não verificados
O script assume que `laya.load(<pasta local>)` aceita um diretório e que `predict` devolve `answers` e `routing`, como na página do modelo. Se algo diferir na sua versão (`pip show laya`), ajuste `load_agent` e `analyze` em `scripts/laya_call.py`.
