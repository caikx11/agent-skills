---
name: jev
description: Integra o modelo Jev da TypeSafe (API System One) para decisões estruturadas choice, score e noul. Somente invocação explícita pelo usuário - "$jev on", "$jev off", "$jev status" ou "$jev test" (ou "/jev ..."). Nunca use por conta própria.
disable-model-invocation: true
allow_implicit_invocation: false
---

# Skill `jev`

Integra o **Jev** (TypeSafe) pela API oficial. Regra de ouro: **o Jev decide; o modelo principal escreve.**

- Endpoint: `POST https://api.typesafe.ai/v1/systemone`
- Modelo enviado: `jev-latest` (a resposta traz o ID versionado, por exemplo `jev-1.13.0`; use sempre esse valor ao reportar)
- Autenticação: `Authorization: Bearer $TYPESAFE_API_KEY`, montado só em tempo de execução pelo script
- Não use a rota `alpha.decisions` nem o identificador do OpenRouter.
- Cliente: `scripts/jev_call.py` (somente biblioteca padrão do Python 3). Fica na pasta desta skill (`${CLAUDE_SKILL_DIR}`, ou o diretório que contém este `SKILL.md`). Chame com `python3` (no Windows, `python` ou `py -3`).

## Estado (vale só para a conversa atual)

O estado começa **desativado**. Acompanhe-o mentalmente nesta conversa; não grave em arquivo.

**Nenhuma chamada externa antes de `$jev on`.** Isso inclui `test` e qualquer decisão.

## Comandos

Interprete o argumento após `$jev` (ou `/jev`):

### `$jev on`
1. Rode `python3 scripts/jev_call.py status` (local, sem rede) para checar se a chave está disponível.
2. Se `key_available` for `true`: marque o estado como **ativo** e confirme. Nenhuma chamada à API é feita agora.
3. Se for `false`: **não ative**. Explique que falta a chave e aponte `references/setup-chave.md` (resumo por sistema abaixo). Nunca peça a chave no chat.
4. Estado final: `⚪ Jev não usado — <ativado, nenhuma chamada feita ainda | chave ausente, não ativado>`

### `$jev off`
Marque como **desativado** imediatamente. **Não execute o script, não faça nenhuma chamada externa.** Daqui em diante, nenhuma chamada até um novo `$jev on`.
Estado final: `⚪ Jev não usado — desativado`

### `$jev status`
Rode `python3 scripts/jev_call.py status` (local, sem rede). Informe:
- estado (ativo/desativado nesta conversa);
- modelo configurado: `jev-latest` (o ID versionado só é conhecido após uma chamada);
- existência da variável `TYPESAFE_API_KEY` e/ou do segredo no cofre do sistema (sim/não). **Nunca mostre a chave**, nem parte dela.

Estado final: `⚪ Jev não usado — apenas status consultado`

### `$jev test`
1. Se o estado não for ativo: não chame nada. `⚪ Jev não usado — desativado; use $jev on antes do teste`
2. Se for ativo, rode `python3 scripts/jev_call.py test`. O script usa um e-mail comercial **totalmente fictício** e faz as três perguntas na mesma requisição: `score` (quão promissor é o lead), `choice` (tipo de e-mail) e `noul` (precisa de resposta pessoal).
3. Mostre: o e-mail fictício, as respostas, as probabilidades, a confiança, a duração, os tokens (entrada/saída) e o custo estimado.
4. Estado final conforme o resultado (ver "Estado final").

## Uso enquanto ativo

Use o Jev **somente** para decisões dos tipos:
- `choice`: escolher uma opção entre um conjunto fechado (classificar, rotear);
- `score`: avaliar numa escala ordenada com níveis descritos;
- `noul`: pergunta de sim/não (probabilidade de "sim").

Não use o Jev para gerar texto, resumir, programar nem raciocinar em várias etapas: **o modelo principal escreve a resposta final** a partir da decisão do Jev.

Como chamar:
1. Reúna todas as perguntas pertinentes numa **única requisição** (o `state` é lido uma vez e todas as perguntas são avaliadas em paralelo).
2. Monte o JSON e envie pelo stdin (não passe conteúdo sensível como argumento de linha de comando):
   ```
   python3 scripts/jev_call.py ask < pedido.json
   ```
   onde `pedido.json` é `{"state": "...", "questions": {"id": {"type": "choice|score|noul", "instructions": "...", "criteria": ...}}}`. O script força `model: jev-latest` e rejeita tipos fora de choice/score/noul.
   - `choice`: `criteria` é um mapa `opção -> descrição`.
   - `score`: `criteria` é uma lista ordenada de descrições dos níveis (2 a 10).
   - `noul`: `criteria` opcional (`true`/`false`).
3. Envie no `state` só o texto necessário para decidir. Nunca inclua credenciais, chaves ou segredos.

### Treinar o Laya junto (opcional)

Se existir uma tarefa do Laya (`python ~/.agents/skills/laya/scripts/laya_call.py tasks`) com **as mesmas perguntas** que você vai enviar, acrescente ao pedido o campo `"laya_task": "<nome>"`. Quando a chamada ao Jev der certo, o script grava o texto, as respostas e as probabilidades em `LAYA_HOME\tasks\<nome>\examples.jsonl` (padrão `~/.laya`), junto com `needs_review` e `flags`. O campo nunca é enviado à API.

- Só inclua `laya_task` quando o usuário já tiver a tarefa criada e o uso for o mesmo. Nunca crie tarefas sozinho.
- Confira o campo `laya_log` na saída: `saved: true` ou o motivo (`tarefa_nao_existe`, `perguntas_diferentes_da_tarefa`...). Informe o resultado em uma linha, junto do estado final.
- O texto fica gravado em disco local. Se o `state` tiver dado pessoal sensível, **não** use `laya_task` nessa chamada.
- Não treina nada: só acumula exemplos. O treino segue o fluxo da skill `laya`.

### Revisão de incerteza

O script devolve `needs_review` e `flags` por pergunta, usando limites definidos no topo do script: confiança < 0,60 (`confianca_baixa`), duas maiores probabilidades com diferença < 0,20 (`probabilidades_divididas`), `noul` entre 0,35 e 0,65 (`noul_proximo_de_0_5`).

Se houver qualquer flag: **revise a decisão com o modelo principal** (releia o `state` e a pergunta, avalie se a resposta do Jev faz sentido) e **sinalize a incerteza** ao usuário, citando a pergunta e o motivo. Se, após a revisão, a decisão não puder ser aproveitada, use o estado 🟡.

## Estado final (obrigatório)

Toda resposta desta skill termina com **exatamente um** destes estados:

- `⚡ Jev usado — modelo: <modelo retornado pela API> · tipos: <choice/score/noul usados>`
- `🟡 Jev consultado, mas não utilizado — confiança insuficiente`
- `⚪ Jev não usado — <motivo>`
- `🔴 Jev falhou — resposta produzida pelo modelo principal`

Regras:
- Mostre `⚡` **somente** depois de uma chamada real bem-sucedida (`ok: true`), com o ID versionado do campo `model` da resposta.
- Sempre que houve chamada à API (⚡, 🟡 ou 🔴), acrescente logo abaixo: `Confiança: <valor ou faixa> · Tempo: <ms> · Custo estimado: <valor>`. Na falha, use `—` para o que não existir.
- Sem chamada (on, off, status, ativo mas sem decisão a tomar): use `⚪` com o motivo.
- Falha (🔴): mostre o **status HTTP e a mensagem sanitizada** que o script devolveu, e responda normalmente com o modelo principal. O script já faz retentativas limitadas com backoff para 429 e 529; não repita manualmente em loop.

## Segurança da chave

- **Nunca peça a chave no chat** e nunca a aceite colada na conversa.
- O script procura primeiro `TYPESAFE_API_KEY` no ambiente; se não existir, consulta o cofre do sistema: macOS Keychain (`security find-generic-password -a "$USER" -s "typesafe-api-key" -w`), Windows com PowerShell (`Get-Secret -Name TYPESAFE_API_KEY -Vault LocalStore -AsPlainText`) ou Linux com Secret Service (`secret-tool lookup service typesafe-ai name TYPESAFE_API_KEY`).
- O valor fica apenas em memória. Nunca grave, imprima, registre ou revele a chave, nem coloque em skill, código, argumentos ou logs. Nunca execute esses comandos de cofre diretamente no shell: use somente o script, que não exibe a saída.
- **Nunca execute por conta própria** o cadastro da chave, a instalação de módulos/pacotes, o registro de cofres nem edições de `~/.zshrc` ou `$PROFILE`. Só oriente o usuário, usando `references/setup-chave.md`, e faça algo disso apenas com autorização explícita.
- Em servidores headless sem Secret Service, o certo é injetar `TYPESAFE_API_KEY` no processo pelo gerenciador de segredos da infraestrutura.

## Se a chave não existir

Explique em poucas linhas e aponte `references/setup-chave.md`. Resumo:
- **macOS:** `security add-generic-password -U -a "$USER" -s "typesafe-api-key" -w` (com `-w` por último, o terminal pede a chave sem guardá-la no histórico).
- **Windows:** instalar `Microsoft.PowerShell.SecretManagement` e `Microsoft.PowerShell.SecretStore` (`-Scope CurrentUser`), registrar o cofre `LocalStore` como padrão e rodar `Set-Secret -Name TYPESAFE_API_KEY -Vault LocalStore` (o PowerShell pede o valor de forma oculta).
- **Linux:** `secret-tool store --label="TypeSafe API key" service typesafe-ai name TYPESAFE_API_KEY`.
