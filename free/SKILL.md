---
name: free
description: Delega subtarefas de volume (rascunho de código, testes, resumo de arquivos/logs grandes, segunda opinião em revisão, extração para JSON) aos modelos gratuitos do FreeLLMAPI, um roteador local que junta os planos grátis de vários provedores e troca de provedor sozinho quando um falha. Somente invocação explícita pelo usuário - "$free on", "$free off", "$free status" ou "$free test" (ou "/free ..."). Nunca use por conta própria.
disable-model-invocation: true
allow_implicit_invocation: false
---

# Skill `free`

Integra o **FreeLLMAPI**, um roteador que roda na máquina do usuário (app desktop) e junta os planos gratuitos de vários provedores (Google Gemini, Groq, Cerebras, Mistral, NVIDIA, OpenRouter, Cloudflare...) atrás de uma API compatível com OpenAI. Quando um provedor esgota a cota ou falha, o roteador passa para o próximo.

Regra de ouro: **o modelo gratuito rascunha; o modelo principal revisa, decide e integra.** Nada do que volta vai para o projeto, para o usuário ou para um commit sem passar pela sua revisão.

- Endpoint: `POST http://127.0.0.1:31415/v1/chat/completions` (porta do app desktop; trocável por `FREELLMAPI_URL`)
- Modelo: `auto` (o roteador escolhe; trocável por `FREE_MODEL` ou pelo campo `model` do pedido)
- Autenticação: `Authorization: Bearer $FREELLMAPI_KEY` (token unificado `freellmapi-...`), montado só em tempo de execução
- Cliente: `scripts/free_call.py` (somente biblioteca padrão do Python 3). Caminho fixo: `~/.agents/skills/free/scripts/free_call.py`. No Windows, chame com `python`.

## Diferença para a skill `nemo`

- A `nemo` fala com um único modelo (Nemotron 3 Ultra no OpenRouter). A `free` usa o roteador: mais estável, porque troca de provedor sozinha, mas **o modelo que responde muda de chamada para chamada** e a qualidade varia junto.
- **O modelo que de fato respondeu está em `routed_via`** (ex.: `groq/qwen/qwen3.8-27b`). Reporte sempre esse valor, nunca só `auto`.
- **Os nomes `claude-*` no catálogo do FreeLLMAPI são apelidos**: pedir `claude-sonnet-4-5` cai num modelo gratuito qualquer (num teste, `gemini-3.5-flash-lite`). Nunca diga ao usuário que um modelo da Anthropic respondeu.
- Se as duas estiverem ativas, prefira a `free` pela estabilidade, e a `nemo` quando quiser especificamente o Nemotron (contexto de 1M num modelo grande).

## Estado (vale só para a conversa atual)

O estado começa **desativado**. Acompanhe-o mentalmente; não grave em arquivo.

**Nenhuma chamada antes de `$free on`.** Isso inclui `test` e qualquer delegação.

Junto com o estado, acompanhe a **autorização de envio de código** por projeto (veja "Privacidade"). Ela começa negada.

## Comandos

Interprete o argumento após `$free` (ou `/free`):

### `$free on`
1. Rode `python scripts/free_call.py status` (só localhost: verifica o `/health` do app, sem enviar a chave).
2. Se `key_available` e `app_running` forem `true`: marque como **ativo** e confirme. Lembre em uma linha que os provedores gratuitos podem registrar os prompts e que você vai pedir autorização antes de mandar código de um projeto.
3. Se faltar a chave: **não ative**; aponte `references/setup.md`. Se o app estiver fechado: **não ative**; peça para abrir o FreeLLMAPI. Nunca peça a chave no chat.
4. Estado final: `⚪ Free não usado — <ativado, nenhuma chamada feita ainda | chave ausente | app fechado>`

### `$free off`
Marque como **desativado** e revogue autorizações de envio. **Não execute o script.**
Estado final: `⚪ Free não usado — desativado`

### `$free status`
Rode `python scripts/free_call.py status`. Informe: estado (ativo/desativado), endereço do roteador, se o app está aberto, modelo configurado, existência da chave (sim/não) e projetos com envio autorizado. **Nunca mostre a chave.**
Estado final: `⚪ Free não usado — apenas status consultado`

### `$free test`
1. Se não estiver ativo: `⚪ Free não usado — desativado; use $free on antes do teste`
2. Se estiver, rode `python scripts/free_call.py test` (função Python **fictícia** `normalizar_sku` com 4 testes pytest).
3. Revise como em uso real: salve o código num arquivo temporário e rode `python -m pytest`. Mostre o código, o resultado dos testes, `routed_via`, a duração, os tokens e as flags.

## Quando delegar (enquanto ativo)

As mesmas três situações da `nemo`, em ordem de valor:
1. **Conteúdo grande para ler** (arquivo/log/dump/diff com mais de ~2.000 linhas): poupa o seu contexto. Confira no original os fatos que basearem decisões. Atenção: o modelo sorteado pode ter contexto pequeno; para conteúdo muito grande, peça um modelo de contexto longo no campo `model` (ex.: `gemini-3.5-flash`) ou use a `nemo`.
2. **Volume repetitivo** (mais de ~10 variações parecidas): `draft`/`tests` em lote, revisados por amostragem e com testes.
3. **Segunda opinião** em revisão importante, depois da sua revisão: `review`.

Não delegue tarefas pequenas, decisões de arquitetura/segurança, a resposta final ao usuário nem classificação/pontuação/sim-não (isso é do `laya`/`jev`). Se o usuário pedir explicitamente, delegue respeitando privacidade e segurança.

## Como chamar

1. Monte o pedido em JSON e envie pelo **stdin**:
   ```
   python scripts/free_call.py ask < tarefa.json
   ```
   ```json
   {
     "task": "draft|tests|summarize|review|extract|ask",
     "instructions": "pedido detalhado e autossuficiente",
     "context": "convenções do projeto, assinaturas, exemplos (opcional)",
     "files": ["caminho/absoluto/arquivo.py"],
     "model": "auto (opcional; ou um id do catálogo)",
     "max_tokens": 8000
   }
   ```
2. Prefira `files` a colar conteúdo: o script bloqueia nomes sensíveis (`.env*`, `*.pem`, `*.key`, `id_rsa`, `credentials*`...), binários e padrões de segredo (chaves privadas, tokens de API incluindo `freellmapi-`/`gsk_`/`AIza`, `password=`, URLs com credencial). Se achar algo, **nada é enviado**.
3. Escreva `instructions` para quem não vê a conversa: linguagem, framework, convenções e formato de saída.
4. Limite padrão de 400 mil caracteres (`max_input_chars`, até 2 milhões).
5. `--dry-run` mostra o que sairia da máquina, sem chave e sem rede.

## Revisão obrigatória

A saída sempre vem com `needs_review: true` e pode ter `flags`: `truncado_por_max_tokens`, `resposta_vazia`, `filtrado`, `json_invalido`, `sem_bloco_de_codigo`.

- **Código e testes:** leia por inteiro, confira as APIs contra o código real e rode lint/testes (`python -m pytest`).
- **Revisão:** confirme cada achado no código antes de reportar; diga quais vieram do modelo gratuito.
- **Resumo e extração:** confira no original o que for basear decisões.

Se a saída não servir, faça você mesmo e use 🟡. No máximo uma nova tentativa com o pedido melhorado (o roteador pode sortear outro modelo).

## Privacidade

- Os planos gratuitos podem registrar e usar os prompts (o Google e vários outros avisam isso). **Antes do primeiro envio de código ou documento de um projeto**, peça autorização em uma linha, dizendo o projeto e o que será enviado. Vale até o fim da conversa ou até `$free off`.
- Conteúdo fictício, público ou genérico não precisa de autorização.
- Nunca envie chaves, `.env`, credenciais, dados pessoais de terceiros ou dados de clientes.

## Estado final (obrigatório)

Toda resposta desta skill termina com **exatamente um** destes estados:

- `⚡ Free usado — via: <routed_via> · tarefas: <draft/tests/summarize/review/extract/ask>`
- `🟡 Free consultado, mas não utilizado — <motivo curto>`
- `⚪ Free não usado — <motivo>`
- `🔴 Free falhou — resposta produzida pelo modelo principal`

Regras:
- `⚡` só depois de chamada real bem-sucedida cujo resultado você revisou e aproveitou ao menos em parte. Use `routed_via`.
- Sempre que houve chamada (⚡, 🟡, 🔴), acrescente: `Tempo: <ms> · Tokens: <entrada>/<saída> · Custo: US$ 0 · Aproveitamento: <integral | parcial | nenhum>`.
- Bloqueio do guardrail (`files_rejected`, `secret_detected`, `input_too_large`) não é chamada: use `⚪`.
- Falha (🔴): mostre status, mensagem sanitizada e `hint`, e faça a tarefa normalmente. Não repita em loop.

## Plano B: quando o limite do Claude acabar

Esta skill não ajuda nesse momento, porque quem a chama é o modelo principal. Para isso existe o comando **`claude-free`** (em `~/.local/bin`, script em `scripts/claude-free.ps1`): ele abre o Claude Code apontado para o FreeLLMAPI, só naquela janela. Envia o nome `claude-sonnet-4-5` (que o Claude Code conhece), mas o roteador escolhe o modelo gratuito real. Se o usuário perguntar o que fazer quando o limite acabar, indique `claude-free` (aceita os mesmos argumentos do `claude`, como `--continue`). Avise que a qualidade é menor e que o modelo muda conforme o roteador.

## Segurança da chave

- **Nunca peça a chave no chat** e nunca a aceite colada na conversa.
- O script procura `FREELLMAPI_KEY` no ambiente e depois no cofre: Windows SecretStore (`Get-Secret -Name FREELLMAPI_KEY -Vault LocalStore -AsPlainText`), macOS Keychain (serviço `freellmapi-key`) ou Linux Secret Service (`secret-tool lookup service freellmapi name FREELLMAPI_KEY`).
- O valor fica só em memória. Nunca o grave, imprima ou registre. Nunca execute os comandos de cofre diretamente no shell: use só o script.
- **Nunca execute por conta própria** cadastro de chave, instalação de pacotes, registro de cofres ou edição de perfis de shell. Só oriente, usando `references/setup.md`.
