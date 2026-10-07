---
name: skills-hub
description: Gerencia o repositório central de skills do usuário (Git em ~/.agents/skills, compartilhado entre Codex, Claude Code e outras IAs por atalhos). Use sempre que o usuário quiser publicar, salvar, versionar, sincronizar, desfazer, auditar ou instalar skills, conectar uma IA nova às skills, restaurar as skills num PC novo, ou perguntar onde uma skill está, mesmo que ele não diga "Git" ou "hub".
---

# skills-hub

O usuário mantém **uma única pasta real de skills**: `~/.agents/skills`, que é um repositório Git com cópia no GitHub. Cada IA enxerga essa pasta de um jeito:

- **Codex** lê `~/.agents/skills` direto.
- **Claude Code** só lê `~/.claude/skills` (e `.claude/skills` do projeto), então lá ficam **atalhos** (junctions no Windows, symlinks no Linux/macOS) apontando para `~/.agents/skills/<skill>`.
- Outras IAs: atalho na pasta de skills delas, ou leitura direta se aceitarem `~/.agents/skills`.

O objetivo é que exista **uma só versão de cada skill**. Cópias soltas criam versões divergentes, e a IA acaba usando a desatualizada. Por isso, quase toda ação aqui termina conferindo que não sobrou cópia fora do lugar.

Ambiente principal: Windows com PowerShell. Expanda `~` para `$HOME`. Confira se `git` (e `gh`, quando for usar GitHub) existem antes de usar. Responda em pt-BR.

## O que não entra no repositório

O `.gitignore` deve conter pelo menos:

```
synced/          # skills da conta Claude, o app sobrescreve sozinho
.env
*.key
__pycache__/
```

Nunca versione chaves. As skills do usuário leem chaves de variáveis de ambiente (`OPENROUTER_API_KEY`, `TYPESAFE_API_KEY`, `FREELLMAPI_KEY`), e é assim que deve continuar.

## Regras de segurança

- **Mostre antes de mudar.** Antes de commit, push, mover, apagar ou restaurar, mostre o diff ou a lista do que vai acontecer e espere o "sim" do usuário. Git desfaz quase tudo, mas apagar uma pasta real não versionada não tem volta.
- **Nunca apague uma pasta real** em `~/.claude/skills` sem antes comparar com a versão em `~/.agents/skills` (veja "Auditar"). Se forem diferentes, pergunte qual manter.
- **Não force** (`push --force`, `reset --hard`) sem pedido explícito.
- Não mexa em `~/.claude/plugins`, `synced/` nem `.system/`: são gerenciados pelos apps.

## Ações

Identifique o que o usuário quer e siga a seção correspondente. Se não ficar claro, pergunte em uma linha.

### Configurar (primeira vez)

1. Se `~/.agents/skills/.git` já existe, pule para "Auditar".
2. Crie o `.gitignore` acima (mescle se já existir), `git init`, `git add .` e mostre `git status` resumido.
3. Commit inicial após confirmação.
4. Se o usuário quiser GitHub: `gh repo create <nome> --private --source . --push`. Sugira **privado**: caminhos locais e nomes de serviços ficam visíveis.
5. Rode "Auditar".

### Publicar (salvar uma mudança)

Quando o usuário criou, instalou ou editou uma skill, por qualquer IA:

1. **Ache a skill.** Ela pode ter sido criada por outra IA, então procure nesta ordem:
   - `~/.agents/skills/<nome>` (Codex, `npx skills`): já está no lugar certo.
   - Pasta real em `~/.claude/skills/<nome>` (Claude Code) ou em `.claude/skills/<nome>` do projeto atual.
   - Pastas de skills de outras IAs: `Get-ChildItem $HOME -Directory -Force -Filter '.*' | ForEach-Object { "$($_.FullName)\skills\<nome>" } | Where-Object { Test-Path "$_\SKILL.md" }`.
   - Não achou: pergunte ao usuário onde está.
2. **Traga para o repositório.** Se ela está fora de `~/.agents/skills`, mova para `~/.agents/skills/<nome>` e deixe um atalho no lugar de onde saiu, para a IA de origem continuar enxergando. Se já existir uma versão com o mesmo nome no repositório, compare antes e pergunte qual manter. Confirme antes de mover.
3. **Conecte o Claude Code.** Se `~/.claude/skills/<nome>` não existe, crie o atalho (veja "Conectar IA"). Sem isso, a skill fica no Git mas o Claude Code não a vê.
4. **Valide** a skill (checklist em "Auditar", itens 1 a 4). Problemas bloqueantes (chave exposta, frontmatter inválido) param a publicação; avisos (caminho fixo) só são informados.
5. Mostre `git diff --stat` e o diff do `SKILL.md`.
6. Commit com mensagem no formato `<skill>: <o que mudou>`, por exemplo `free: adiciona Groq como fallback`. Skill nova: `<skill>: adiciona skill`.
7. `git push` se houver remoto.
8. **Confira que não sobrou cópia:** `~/.claude/skills/<nome>` e a pasta de origem devem ser atalhos (`LinkType` preenchido), não pastas reais.

### Conectar IA

Crie um atalho por skill na pasta da IA, apontando para `~/.agents/skills/<skill>`:

```powershell
$destino = "$HOME\.claude\skills"   # pasta de skills da IA
New-Item -ItemType Directory -Force $destino | Out-Null
Get-ChildItem "$HOME\.agents\skills" -Directory |
  Where-Object { $_.Name -notin @('synced', '.git') -and (Test-Path "$($_.FullName)\SKILL.md") } |
  ForEach-Object {
    $alvo = "$destino\$($_.Name)"
    if (-not (Test-Path $alvo)) { New-Item -ItemType Junction -Path $alvo -Target $_.FullName | Out-Null; "criado: $($_.Name)" }
  }
```

Se o destino já tem uma **pasta real** com o mesmo nome, não sobrescreva: trate como duplicata (veja "Auditar").

Pastas conhecidas: Claude Code `~/.claude/skills`; Codex lê `~/.agents/skills` direto. Para outra IA, confira na documentação dela onde ficam as skills antes de criar atalhos. Se ela não lê skills do disco mas aceita MCP, explique que precisaria de um servidor (por exemplo, OpenViking) e que isso é uma etapa à parte.

### Restaurar num PC novo

1. `git clone <url> "$HOME\.agents\skills"` (se a pasta existir e não estiver vazia, pergunte antes).
2. Rode "Conectar IA" para cada IA instalada.
3. Lembre o usuário de recriar as variáveis de ambiente das chaves e de checar caminhos locais apontados no "Auditar" (por exemplo, `LAYA_HOME`, que aponta para a pasta de dados do `laya`).

### Histórico e desfazer

- O que mudou: `git log --oneline -- <skill>/` e, se pedirem detalhe, `git show <commit> -- <skill>/`. Resuma em linguagem simples.
- Desfazer: mostre o log, confirme qual versão, então `git restore --source <commit> -- <skill>/` e publique como novo commit (`<skill>: volta para <commit>`). Prefira isso a reescrever o histórico.
- Testar sem risco: `git switch -c teste-<skill>`; para descartar, `git switch main`.

### Atualizar skills de terceiros

Skills instaladas por `npx skills` (como o pacote do Matt Pocock) têm origem externa. Atualize com `npx skills update`, depois mostre o diff e publique (`terceiros: atualiza pacote`). Se o usuário editou uma delas localmente, avise que a atualização pode sobrescrever as edições.

### Auditar

Rode quando o usuário pedir, depois de configurar e quando algo parecer estranho. Gere um relatório curto agrupado por gravidade (🔴 bloqueante, 🟡 atenção, ✅ ok).

Por skill em `~/.agents/skills` (ignorando `synced/` e `.git`):

1. **Frontmatter:** existe, tem `name` e `description`, e `name` é igual ao nome da pasta. 🔴 se faltar.
2. **Segredos:** procure chaves reais no texto e nos scripts (padrões como `sk-`, `sk-or-`, `ghp_`, `freellmapi-` seguidos de muitos caracteres, ou `API_KEY = "..."` com valor). Citar o *nome* da variável é ok; o *valor* é 🔴.
3. **Caminhos fixos:** caminhos absolutos como `D:\...`, `C:\Users\<nome>\...`. 🟡 se não houver alternativa; ✅ com nota se o texto já oferece uma variável de ambiente (ex.: `LAYA_HOME`). Funciona neste PC, quebra em outro.
4. **Referências quebradas:** arquivos citados no `SKILL.md` (por exemplo, `scripts/x.py`, `references/y.md`) que não existem. 🟡.
5. **Dependências entre skills:** quando uma skill chama arquivos de outra (ex.: `jev` grava exemplos usados pelo `laya`, e o `laya` usa o `jev` como professor), registre a dependência no relatório. Ao mover, renomear ou desfazer uma delas, avise que a outra pode quebrar.

Entre pastas:

6. **Pastas reais em `~/.claude/skills`:** liste entradas sem `LinkType`. Se a skill também existe em `~/.agents/skills`, compare (hash dos arquivos) e diga se são iguais ou diferentes. Se só existe ali, é uma skill fora do repositório: proponha movê-la.
7. **Atalhos quebrados:** atalhos cujo alvo não existe. Proponha remover.
8. **Skills sem atalho** no Claude Code: proponha "Conectar IA".
9. **Git:** mudanças não commitadas e commits não enviados (`git status -sb`).
10. **Conflito com instruções globais:** se `~/.codex/AGENTS.md` ou `~/.claude/CLAUDE.md` repetem regras que já estão numa skill, aponte a duplicação e sugira deixar a regra num lugar só (de preferência na skill, para valer em todas as IAs).

Comando útil para o item 6:

```powershell
Get-ChildItem "$HOME\.claude\skills" -ErrorAction SilentlyContinue |
  Select-Object Name, @{n='Tipo';e={ if ($_.LinkType) { "atalho -> $($_.Target)" } else { 'pasta real' } }}
```

Termine o relatório com as correções propostas numeradas e pergunte quais aplicar.
