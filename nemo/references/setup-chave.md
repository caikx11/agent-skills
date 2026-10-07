# Guardar a chave do OpenRouter com segurança

Estas etapas são para **o usuário** executar no próprio terminal. A skill `nemo` nunca as executa sem autorização explícita e nunca pede a chave no chat.

1. Crie a chave em https://openrouter.ai/keys. Se quiser, defina um limite de crédito na própria chave.
2. Para usar os modelos `:free`, permita o registro de prompts em https://openrouter.ai/settings/privacy. Sem isso, a API responde 404 ("No endpoints found matching your data policy").

Em todos os casos, a chave **nunca** vai como argumento, em arquivo de configuração nem em histórico de shell.

## Windows (PowerShell SecretManagement + SecretStore)

Se você já configurou o cofre `LocalStore` para o Jev, pule direto para o `Set-Secret`. Caso contrário, instale os módulos e registre o cofre (o `Register-SecretVault` vai em uma linha só):

```powershell
Install-Module Microsoft.PowerShell.SecretManagement -Scope CurrentUser
Install-Module Microsoft.PowerShell.SecretStore -Scope CurrentUser
Register-SecretVault -Name LocalStore -ModuleName Microsoft.PowerShell.SecretStore -DefaultVault
```

Salve a chave sem passá-la como argumento. O PowerShell pede o valor de forma oculta:

```powershell
Set-Secret -Name OPENROUTER_API_KEY -Vault LocalStore
```

Opcional, carregamento automático: o `$PROFILE` deve conter **somente** o comando de consulta:

```powershell
$env:OPENROUTER_API_KEY = Get-Secret -Name OPENROUTER_API_KEY -Vault LocalStore -AsPlainText
```

Se o cofre tiver senha, o script não consegue abri-lo de forma não interativa. Nesse caso, desbloqueie antes na sessão (`Unlock-SecretStore`) ou use o carregamento pelo `$PROFILE`.

## macOS (Keychain)

```bash
security add-generic-password -U -a "$USER" -s "openrouter-api-key" -w
```

Opcional, no `~/.zshrc` (só o comando de consulta, nunca a chave literal):

```bash
export OPENROUTER_API_KEY="$(security find-generic-password -a "$USER" -s "openrouter-api-key" -w 2>/dev/null)"
```

## Linux (Secret Service)

```bash
secret-tool store --label="OpenRouter API key" service openrouter name OPENROUTER_API_KEY
```

Em servidores headless sem Secret Service, use o gerenciador de segredos da infraestrutura e injete `OPENROUTER_API_KEY` no processo.

## Trocar de modelo

Para usar a versão paga (sem registro de prompts, conforme o provedor escolhido), defina na sessão:

```powershell
$env:NEMO_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
```
