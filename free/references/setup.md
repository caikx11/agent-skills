# Configurar o FreeLLMAPI para a skill `free`

Estas etapas são para **o usuário** executar. A skill nunca as executa sem autorização e nunca pede chaves no chat.

## 1. Instalar e abrir o app

Baixe o instalador do Windows (`FreeLLMAPI-Setup-<versão>.exe`) na página de releases do projeto (github.com/tashfeenahmed/freellmapi) e confira o SHA-256 antes de instalar:

```powershell
Get-FileHash "$env:USERPROFILE\Downloads\FreeLLMAPI-Setup-<versão>.exe" -Algorithm SHA256
```

O app desktop roda em `http://127.0.0.1:31415` (a documentação do projeto cita a porta 3001, que é a da instalação via Docker). Ele precisa estar aberto para a skill e o `claude-free` funcionarem.

## 2. Cadastrar os provedores

No painel do app, cadastre as chaves dos provedores gratuitos. Recomendados (grátis, sem cartão, bons para código): Google AI Studio, Groq, Cerebras, Mistral, NVIDIA NIM, OpenRouter, GitHub Models, Cloudflare Workers AI (formato `account_id:token`, com token criado pelo modelo de permissão "Workers AI").

Evite provedores que exigem carteira cripto, verificação de identidade chinesa ou cartão, e os que você não consegue identificar.

## 3. Guardar o token unificado

O token `freellmapi-...` (gerado no painel) é o que a skill usa. Salve no cofre; o PowerShell pede o valor de forma oculta:

```powershell
Set-Secret -Name FREELLMAPI_KEY -Vault LocalStore
```

Confira se colou inteiro: o prompt oculto não mostra o que foi digitado.

macOS: `security add-generic-password -U -a "$USER" -s "freellmapi-key" -w`
Linux: `secret-tool store --label="FreeLLMAPI token" service freellmapi name FREELLMAPI_KEY`

## 4. Variáveis opcionais

- `FREELLMAPI_URL`: endereço do roteador, se não for `http://127.0.0.1:31415`.
- `FREE_MODEL`: modelo padrão, se não quiser `auto`.

## Plano B (`claude-free`)

Quando o limite do Claude acabar, rode `claude-free` num terminal, na pasta do projeto. Ele abre o Claude Code com os modelos gratuitos, só naquela janela. Aceita os argumentos do `claude` (ex.: `claude-free --continue`).
