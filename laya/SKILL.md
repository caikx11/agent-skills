---
name: laya
description: Integra o modelo Laya (convaiinnovations) rodando localmente para decisões estruturadas choice, score e noul, com tarefas que acumulam exemplos e modelos ajustados salvos em LAYA_HOME (padrão `~/.laya`). Pode usar o Jev como professor. Somente invocação explícita pelo usuário - "$laya on", "$laya off", "$laya status", "$laya tasks", "$laya stats" ou "$laya ask" (ou "/laya ..."). Nunca use por conta própria.
disable-model-invocation: true
allow_implicit_invocation: false
---

# Skill `laya`

Integra o **Laya** (modelo de decisão não autoregressivo, Apache 2.0) **no PC do usuário**. Regra de ouro: **o Laya decide; o modelo principal escreve.** Equivale à skill `jev`, mas gratuita e local.

- Cliente: `scripts/laya_call.py` (biblioteca padrão do Python 3; o pacote `laya` é importado só quando necessário). Fica na pasta desta skill. No Windows use `python` ou `py -3`.
- Dados: `~/.laya` (altere com a variável `LAYA_HOME`).
  - `registry.json`: tarefas, origem do modelo, acurácia, calibração.
  - `tasks/<nome>/questions.json`, `examples.jsonl`, `history.jsonl`, `dataset.jsonl`, `model/` (modelo ajustado).
- Nenhuma chave de API. A única chamada externa possível é ao **Jev como professor**, e só com `--teacher` (ver abaixo).

## Estado (vale só para a conversa atual)

Começa **desativado**. Acompanhe mentalmente; não grave em arquivo. Nenhuma execução de `ask` antes de `$laya on`.

## Comandos

### `$laya on`
1. Rode `python scripts/laya_call.py status` (local, sem rede).
2. Se `laya_instalado` for `false`: **não ative**. Oriente `pip install laya` (e `pip install "laya[serve]"` só se quiser servidor). **Nunca instale por conta própria.**
3. Se a pasta de dados não existir, ofereça rodar `init` e espere o sim do usuário.
4. Ative e confirme. Estado: `⚪ Laya não usado — ativado, nenhuma decisão feita ainda`.

### `$laya off`
Desative. Não rode o script. Estado: `⚪ Laya não usado — desativado`.

### `$laya status`
Rode `status` e informe: estado, versão do Python, Laya instalado (sim/não), pasta de dados, se o script do Jev foi encontrado, tarefas registradas. Estado: `⚪ Laya não usado — apenas status consultado`.

### `$laya tasks`
Rode `tasks`. Mostre por tarefa: se tem modelo ajustado, nº de exemplos, acurácia, origem do modelo.

### `$laya stats <nome>`
Rode `stats <nome>` e mostre a concordância do modo sombra (total e por pergunta), nº de amostras e se está `pronto`.

### `$laya new <nome>`
Cria a tarefa. Monte o JSON `{"questions": {...}}` e envie por stdin: `python scripts/laya_call.py new-task <nome> < schema.json`. Nome em minúsculas, números, `-` ou `_`.
- `choice`: `criteria` é um mapa `opção -> descrição`. **Máximo 20 opções**; acima disso divida em duas etapas.
- `score`: `criteria` é uma lista ordenada de descrições (2 a 10). É o tipo mais fraco do Laya.
- `noul`: sim/não. Pode ficar travado em "não"; se parecer preso, troque por `choice` com chaves neutras (`A`/`B`).
- Escreva descrições claras para cada opção: é o ajuste mais barato de qualidade.

## Uso enquanto ativo

Use o Laya **somente** para decisões `choice`, `score` e `noul`. Não use para gerar texto, resumir nem raciocinar em etapas.

```
python scripts/laya_call.py ask <tarefa> < pedido.json        # só Laya
python scripts/laya_call.py ask <tarefa> --teacher < pedido.json   # Laya + Jev como professor
```
`pedido.json` é `{"state": "..."}`. As perguntas vêm da tarefa. Envie pelo stdin e só o texto necessário.

O script usa o **modelo ajustado da tarefa** se existir em `tasks/<nome>/model`; senão cai no `Router` zero-shot e o campo `modo` vem como `zero-shot`. Em zero-shot, avise que a precisão é baixa (a página do modelo mede 0,36 contra 0,77 ajustado) e que o Laya sai superconfiante.

### Revisão de incerteza
Se `needs_review` for `true` (confiança < 0,60, duas maiores probabilidades com diferença < 0,20, ou `noul` entre 0,35 e 0,65): revise com o modelo principal, e sinalize a incerteza citando a pergunta e o motivo. Os campos `confidence` e `probabilities` dependem do que o Laya devolve; se não existirem, diga que a confiança não está disponível.

## Aprender com o uso

1. **Correção do usuário:** quando ele disser a resposta certa, grave com `correct <tarefa>` (`{"state": "...", "answers": {...}}` no stdin).
2. **Jev como professor (`--teacher`):** só se o usuário pedir explicitamente **e** o Jev estiver ativo (`$jev on`). Antes, avise que o texto será enviado à API do Jev, e pergunte se os e-mails estão anonimizados. Confira também se os termos da TypeSafe permitem usar as saídas para treinar outro modelo. O script reaproveita `~/.agents/skills/jev/scripts/jev_call.py`, que cuida da chave; esta skill nunca lê chaves.
3. **Modo sombra (modelo principal como professor, grátis):** o principal decide como faria de qualquer forma e manda a própria decisão junto com o pedido. A sugestão do Laya **não é seguida**, só medida.
   ```
   python scripts/laya_call.py ask <tarefa> < pedido.json   # {"state": "...", "shadow": {"<pergunta>": "<resposta do principal>"}}
   ```
   A resposta do principal vira exemplo (`source: principal`) e o histórico registra se os dois concordaram. Use em tarefas que você mesmo está decidindo, como a `rotear-modelo`.
   - `stats <tarefa> [--last N]` mostra a concordância das últimas N sombras (padrão 50) com o modelo atual e grava em `acuracia` no registro. `pronto: true` quando passa de 85% com 50+ amostras; aí o Laya pode começar a decidir de verdade.
   - Concordância mede o quanto o Laya imita o principal, não se o principal acertou. Correções do usuário (`correct`) continuam valendo mais.
4. **Treinar:** com cerca de 100 exemplos, a calibração já ajuda. Com 200+, vale o fine-tuning.
   - `export <tarefa>` gera `dataset.jsonl`. Peça ao usuário para revisar 50 a 100 linhas à mão.
   - O treino roda no **Kaggle (2x T4 grátis)** ou Colab, com o notebook oficial do Laya. **Esta skill não treina** e nunca dispara treino sozinha.
   - O notebook envia o resultado ao Hub do usuário. Depois: `import-model <tarefa> <usuario/repo>` baixa para `tasks/<nome>/model` (token só se o repositório for privado, e fora do chat).
   - Guarde as temperaturas que o notebook produzir com `set-calibration <tarefa>`.
5. Antes de dizer que ficou bom, meça: separe 50 exemplos conhecidos e compare. Acima de 85 a 90% e com erro de baixo custo, pode usar.

## Estado final (obrigatório)

Toda resposta termina com **exatamente um**:

- `⚡ Laya usado — modo: <zero-shot|ajustado> · tarefa: <nome> · tipos: <choice/score/noul>`
- `🟡 Laya consultado, mas não utilizado — confiança insuficiente`
- `⚪ Laya não usado — <motivo>`
- `🔴 Laya falhou — resposta produzida pelo modelo principal`

Regras:
- `⚡` só depois de `ok: true` do script.
- Após cada `ask`, acrescente: `Tempo: <ms> · Exemplos da tarefa: <n>`. Com `--teacher`, some `Professor: <modelo Jev> · Custo estimado: <valor>`.
- Falha (🔴): mostre a mensagem curta do script e responda com o modelo principal. Não repita em loop.

## Segurança e privacidade

- Nunca peça nem aceite chaves ou tokens no chat. Token do Hugging Face só no ambiente do usuário.
- **Nunca instale pacotes, rode treino nem apague a pasta de dados** por conta própria.
- `examples.jsonl` e `history.jsonl` podem conter texto de e-mails reais. Não publique `dataset.jsonl` nem repositórios do Hub com esses dados sem o usuário confirmar. Prefira repositório privado.
- Cada modelo ajustado tem cerca de 800 MB; avise quando a pasta crescer muito.
- Detalhes de setup: `references/setup.md`.
