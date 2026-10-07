---
name: nemo
description: Delega subtarefas de volume (rascunho de código, testes, resumo de arquivos/logs grandes, segunda opinião em revisão, extração para JSON) ao NVIDIA Nemotron 3 Ultra 550B via OpenRouter (tier gratuito). Somente invocação explícita pelo usuário - "$nemo on", "$nemo off", "$nemo status" ou "$nemo test" (ou "/nemo ..."). Nunca use por conta própria.
disable-model-invocation: true
allow_implicit_invocation: false
---

# Skill `nemo`

Integra o **Nemotron 3 Ultra** (NVIDIA, 550B total / 55B ativos, MoE híbrido Mamba-2, contexto de ~1M tokens) pelo OpenRouter. O Nemo é um modelo **generalista**: diferente do Jev, ele **gera conteúdo**.

Regra de ouro: **o Nemo rascunha; o modelo principal revisa, decide e integra.** Nada que o Nemo devolve vai para o projeto, para o usuário ou para um commit sem passar pela sua revisão.

- Endpoint: `POST https://openrouter.ai/api/v1/chat/completions`
- Modelo: `nvidia/nemotron-3-ultra-550b-a55b:free` (pode ser trocado pela variável `NEMO_MODEL`, por exemplo para a versão paga sem `:free`)
- Autenticação: `Authorization: Bearer $OPENROUTER_API_KEY`, montado só em tempo de execução pelo script
- Cliente: `scripts/nemo_call.py` (somente biblioteca padrão do Python 3). Fica na pasta desta skill (`${CLAUDE_SKILL_DIR}`, ou o diretório que contém este `SKILL.md`; caminho fixo: `~/.agents/skills/nemo/scripts/nemo_call.py`). No Windows, chame com `python`.

## Estado (vale só para a conversa atual)

O estado começa **desativado**. Acompanhe-o mentalmente nesta conversa; não grave em arquivo.

**Nenhuma chamada externa antes de `$nemo on`.** Isso inclui `test` e qualquer delegação.

Junto com o estado, acompanhe a **autorização de envio de código** por projeto (veja "Privacidade"). Ela começa negada.

## Comandos

Interprete o argumento após `$nemo` (ou `/nemo`):

### `$nemo on`
1. Rode `python scripts/nemo_call.py status` (local, sem rede) para checar se a chave está disponível.
2. Se `key_available` for `true`: marque o estado como **ativo** e confirme. Lembre em uma linha que o tier `:free` pode registrar os prompts e que você vai pedir autorização antes de mandar código do projeto. Nenhuma chamada à API é feita agora.
3. Se for `false`: **não ative**. Explique que falta a chave e aponte `references/setup-chave.md`. Nunca peça a chave no chat.
4. Estado final: `⚪ Nemo não usado — <ativado, nenhuma chamada feita ainda | chave ausente, não ativado>`

### `$nemo off`
Marque como **desativado** imediatamente e revogue autorizações de envio. **Não execute o script, não faça nenhuma chamada externa.**
Estado final: `⚪ Nemo não usado — desativado`

### `$nemo status`
Rode `python scripts/nemo_call.py status` (local, sem rede). Informe: estado (ativo/desativado), modelo configurado (e se foi trocado por `NEMO_MODEL`), existência da chave na variável e/ou no cofre (sim/não), e os projetos com envio autorizado nesta conversa. **Nunca mostre a chave**, nem parte dela.
Estado final: `⚪ Nemo não usado — apenas status consultado`

### `$nemo test`
1. Se o estado não for ativo: não chame nada. `⚪ Nemo não usado — desativado; use $nemo on antes do teste`
2. Se for ativo, rode `python scripts/nemo_call.py test`. O script pede uma função Python **totalmente fictícia** (`normalizar_sku`) com 4 testes pytest.
3. **Revise a saída como faria em uso real**: salve o código num arquivo temporário e rode os testes com `python -m pytest` (o pytest está instalado no Python do usuário, mas o comando `pytest` sozinho não está no PATH). Mostre: o código gerado, se os testes passaram, a duração, os tokens (entrada/saída/raciocínio), o custo e as flags.
4. Estado final conforme o resultado.

## Quando delegar (enquanto ativo)

### O que já se sabe do modelo (teste de 07/10/2026)

- Código limpo e bem organizado, mas com **bug sutil não percebido pelo próprio modelo**: usou `NFKD` em vez de `NFD` e o teste que ele mesmo escreveu falhava. Revisão e testes não são opcionais.
- Latência alta e instável no `:free`: ~45 s numa tarefa pequena, com 503 ("Nvidia overloaded") resolvido só na 3ª tentativa. Conte com isso ao decidir se compensa.
- Custo zero no `:free`.

Consequência prática: o Nemo compensa em três situações, em ordem de valor:
1. **Conteúdo grande para ler** (arquivo/log/dump/diff com mais de ~2.000 linhas): o ganho principal é poupar o seu contexto. Use `summarize` ou `extract` e confira no original os fatos que basearem decisões.
2. **Volume repetitivo** (mais de ~10 variações parecidas): `draft`/`tests` em lote, revisados por amostragem e com testes rodando (`python -m pytest`).
3. **Segunda opinião** em revisão importante, depois da sua revisão: `review`.

Fora disso, faça você mesmo: em tarefas pequenas e no trabalho do dia a dia você é mais rápido e erra menos do que o ciclo delegar + revisar.

### Tipos de tarefa

| `task` | Use para | Você ainda faz |
|---|---|---|
| `draft` | boilerplate, CRUD, scaffolding, conversões mecânicas entre linguagens/formatos, várias variações parecidas | ler tudo, ajustar ao projeto, rodar lint/testes |
| `tests` | gerar uma bateria inicial de testes para código já escrito | rodar os testes; descartar os que testam comportamento errado |
| `summarize` | arquivos, logs ou diffs grandes que só precisam ser entendidos em linhas gerais | conferir no original qualquer fato que vá basear uma decisão |
| `review` | segunda opinião depois da **sua** revisão | verificar cada achado no código antes de reportar; descartar falsos positivos |
| `extract` | transformar texto/logs/docs em JSON estruturado (aceita `json_schema`) | validar o JSON e amostrar alguns itens |
| `ask` | pergunta técnica pontual em que um segundo modelo ajuda | comparar com o seu próprio raciocínio |

**Não delegue:**
- tarefas pequenas, em que a chamada (que pode levar dezenas de segundos) custa mais tempo do que fazer;
- decisões de arquitetura, segurança, migrações de dados ou qualquer coisa difícil de desfazer;
- a resposta final ao usuário: você escreve;
- conteúdo com segredo, dado pessoal ou código que o usuário não autorizou enviar;
- classificação/pontuação/sim-ou-não: isso é trabalho do `laya`/`jev`.

Se o usuário pedir explicitamente ("pede pro Nemo", "manda pro Nemotron"), delegue mesmo que você faria sozinho, respeitando privacidade e segurança.

## Como chamar

1. Monte o pedido em JSON e envie pelo **stdin** (nunca como argumento de linha de comando). Escreva o JSON num arquivo do scratchpad e redirecione:
   ```
   python scripts/nemo_call.py ask < tarefa.json
   ```
   Formato:
   ```json
   {
     "task": "draft|tests|summarize|review|extract|ask",
     "instructions": "pedido detalhado e autossuficiente",
     "context": "convenções do projeto, assinaturas, exemplos (opcional)",
     "files": ["caminho/absoluto/arquivo.py"],
     "effort": "low|medium|high",
     "max_tokens": 8000,
     "json_schema": { "...": "só para extract (opcional)" }
   }
   ```
2. Prefira `files` a colar o conteúdo: o script lê os arquivos, bloqueia nomes sensíveis (`.env*`, `*.pem`, `*.key`, `id_rsa`, `credentials*`, `secrets*`, `.npmrc`...) e binários, e procura padrões de segredo (chaves privadas, tokens de API, `password=`, URLs com credencial). Se achar algo, **nada é enviado** e a saída diz o tipo encontrado, sem o valor.
3. Escreva `instructions` como se fosse para alguém que não vê a conversa: o Nemo só sabe o que está no pedido. Diga a linguagem, o framework, as convenções e o formato de saída.
4. Envie só o necessário. O limite padrão é 400 mil caracteres (`max_input_chars`, até 2 milhões). Só aumente quando o arquivo grande for o objetivo (por exemplo, resumir um log) e o usuário tiver autorizado o envio.
5. `effort`: `low` para mecânico, `medium` (padrão), `high` para lógica difícil. O raciocínio do modelo não volta na resposta, só o resultado.
6. Use `--dry-run` para conferir o que sairia da máquina sem chave e sem rede.

## Revisão obrigatória

A saída sempre vem com `needs_review: true`. Além disso, o script marca `flags`:
- `truncado_por_max_tokens`: a resposta foi cortada; refaça com `max_tokens` maior ou divida a tarefa;
- `resposta_vazia`, `filtrado`, `json_invalido`, `sem_bloco_de_codigo`.

Antes de usar o resultado:
- **Código e testes:** leia por inteiro, confira as APIs contra o código real do projeto (o Nemo pode inventar funções) e rode lint/testes quando houver.
- **Revisão:** confirme cada achado abrindo o trecho citado. Reporte só os confirmados e diga quais vieram do Nemo.
- **Resumo e extração:** confira no original qualquer fato que vá basear uma decisão.

Se a saída não servir (errada, incompleta ou com flag que impede o uso), faça você mesmo e use o estado 🟡. Não repita a mesma chamada em loop: no máximo uma nova tentativa com o pedido melhorado.

## Privacidade

- O tier `:free` pode registrar e usar os prompts para treino. Por isso, **antes do primeiro envio de código ou documento de um projeto**, peça autorização ao usuário em uma linha, dizendo o projeto e o que será enviado. A autorização vale para aquele projeto até o fim da conversa ou até `$nemo off`.
- Conteúdo fictício, público ou genérico (que não vem do projeto) não precisa de autorização.
- Nunca envie: chaves, `.env`, credenciais, dados pessoais de terceiros, dados de clientes. Se o usuário pedir para enviar algo assim, recuse e sugira mascarar.
- Para código sensível, sugira ao usuário trocar para a versão paga (`NEMO_MODEL=nvidia/nemotron-3-ultra-550b-a55b`) com um provedor que não registre prompts, mas não altere variáveis por conta própria.

## Estado final (obrigatório)

Toda resposta desta skill termina com **exatamente um** destes estados:

- `⚡ Nemo usado — modelo: <modelo retornado pela API> · tarefas: <draft/tests/summarize/review/extract/ask>`
- `🟡 Nemo consultado, mas não utilizado — <motivo curto: saída incorreta | truncada | pior que a minha>`
- `⚪ Nemo não usado — <motivo>`
- `🔴 Nemo falhou — resposta produzida pelo modelo principal`

Regras:
- Mostre `⚡` **somente** depois de uma chamada real bem-sucedida (`ok: true`) cujo resultado você revisou e aproveitou, ao menos em parte. Use o campo `model` da resposta.
- Sempre que houve chamada à API (⚡, 🟡 ou 🔴), acrescente logo abaixo: `Tempo: <ms> · Tokens: <entrada>/<saída> · Custo: <valor> · Aproveitamento: <integral | parcial | nenhum>`. Na falha, use `—` para o que não existir.
- Bloqueio pelo guardrail (`files_rejected`, `secret_detected`, `input_too_large`) não é chamada: use `⚪` com o motivo.
- Falha (🔴): mostre o **status HTTP, a mensagem sanitizada e a dica (`hint`)** que o script devolveu, e faça a tarefa normalmente. O script já faz retentativas com backoff para 429/502/503/529; não repita manualmente.
- Ativo, mas sem tarefa que valha delegar: `⚪ Nemo não usado — tarefa não compensava delegar`.

## Segurança da chave

- **Nunca peça a chave no chat** e nunca a aceite colada na conversa.
- O script procura primeiro `OPENROUTER_API_KEY` no ambiente; se não existir, consulta o cofre: macOS Keychain (serviço `openrouter-api-key`), Windows PowerShell SecretStore (`Get-Secret -Name OPENROUTER_API_KEY -Vault LocalStore -AsPlainText`) ou Linux Secret Service (`secret-tool lookup service openrouter name OPENROUTER_API_KEY`).
- O valor fica só em memória. Nunca grave, imprima, registre ou revele a chave, nem a coloque em skill, código, argumentos ou logs. Nunca execute os comandos de cofre diretamente no shell: use somente o script, que não exibe a saída.
- **Nunca execute por conta própria** o cadastro da chave, a instalação de módulos/pacotes, o registro de cofres nem edições de `~/.zshrc` ou `$PROFILE`. Só oriente o usuário, usando `references/setup-chave.md`.

## Se a chave não existir

Explique em poucas linhas e aponte `references/setup-chave.md`. Resumo:
- **Windows:** `Set-Secret -Name OPENROUTER_API_KEY -Vault LocalStore` (o PowerShell pede o valor de forma oculta).
- **macOS:** `security add-generic-password -U -a "$USER" -s "openrouter-api-key" -w`
- **Linux:** `secret-tool store --label="OpenRouter API key" service openrouter name OPENROUTER_API_KEY`
- A chave é criada em https://openrouter.ai/keys. Para usar os modelos `:free`, a conta precisa permitir o registro de prompts em https://openrouter.ai/settings/privacy.
