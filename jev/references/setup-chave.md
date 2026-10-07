# Guardar a chave da TypeSafe com segurança

Estas etapas são para **o usuário** executar no próprio terminal. A skill `jev` nunca as executa sem autorização explícita e nunca pede a chave no chat. A chave é criada em https://console.typesafe.ai/keys.

Em todos os casos, a chave **nunca** vai como argumento, em arquivo de configuração nem em histórico de shell.

## macOS (Keychain)

Execute uma vez. O `-w` precisa ser o **último** argumento, para o terminal pedir a chave sem guardá-la no histórico:

```bash
security add-generic-password -U -a "$USER" -s "typesafe-api-key" -w
```

Opcional, para novos terminais: adicione ao `~/.zshrc` apenas o comando de consulta (nunca a chave literal):

```bash
export TYPESAFE_API_KEY="$(security find-generic-password -a "$USER" -s "typesafe-api-key" -w 2>/dev/null)"
```

## Windows (PowerShell SecretManagement + SecretStore)

Instale os módulos no escopo do usuário e registre o cofre padrão `LocalStore` (o `Register-SecretVault` vai em uma linha só):

```powershell
Install-Module Microsoft.PowerShell.SecretManagement -Scope CurrentUser
Install-Module Microsoft.PowerShell.SecretStore -Scope CurrentUser
Register-SecretVault -Name LocalStore -ModuleName Microsoft.PowerShell.SecretStore -DefaultVault
```

Salve a chave sem passá-la como argumento. O PowerShell pede o valor de forma oculta:

```powershell
Set-Secret -Name TYPESAFE_API_KEY -Vault LocalStore
```

Opcional, carregamento automático: o `$PROFILE` deve conter **somente** o comando de consulta:

```powershell
$env:TYPESAFE_API_KEY = Get-Secret -Name TYPESAFE_API_KEY -Vault LocalStore -AsPlainText
```

Observação: os módulos instalados no PowerShell 7 (`pwsh`) e no Windows PowerShell 5.1 ficam em pastas diferentes. O script tenta `pwsh` e depois `powershell`; instale no que você usa.

## Linux (Secret Service)

Instale o `secret-tool` pelo pacote `libsecret-tools` (Debian/Ubuntu) ou `libsecret` (Fedora). Para salvar (em um terminal, ele pede o segredo sem exibi-lo):

```bash
secret-tool store --label="TypeSafe API key" service typesafe-ai name TYPESAFE_API_KEY
```

Para recuperar (é o que o script faz):

```bash
secret-tool lookup service typesafe-ai name TYPESAFE_API_KEY
```

Em servidores headless sem Secret Service, use o gerenciador de segredos da infraestrutura e injete `TYPESAFE_API_KEY` no processo.
