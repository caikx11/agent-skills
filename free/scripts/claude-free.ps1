<#
  Plano B: abre o Claude Code usando o FreeLLMAPI (modelos gratuitos) no lugar da Anthropic.
  Use quando o seu limite do Claude acabar. Os argumentos são repassados ao `claude`
  (ex.: claude-free -p "pergunta", claude-free --continue).

  As variáveis valem só para esta execução e são removidas ao sair; o `claude` normal não muda.
  Variáveis opcionais: FREELLMAPI_URL (padrão http://127.0.0.1:31415) e FREE_MODEL (padrão auto).
#>
$ErrorActionPreference = 'Stop'

$base  = if ($env:FREELLMAPI_URL) { $env:FREELLMAPI_URL.TrimEnd('/') } else { 'http://127.0.0.1:31415' }
# O roteador aceita qualquer nome e escolhe o modelo gratuito; um nome que o Claude Code conhece
# evita o aviso de "modelo desconhecido" e mantém a janela de contexto padrão.
$model = if ($env:FREE_MODEL) { $env:FREE_MODEL } else { 'claude-sonnet-4-5' }

try {
    Invoke-WebRequest -Uri "$base/health" -UseBasicParsing -TimeoutSec 5 | Out-Null
} catch {
    Write-Host "O FreeLLMAPI não está respondendo em $base. Abra o app e tente de novo." -ForegroundColor Red
    exit 1
}

$key = $env:FREELLMAPI_KEY
if (-not $key) {
    try {
        $key = Get-Secret -Name FREELLMAPI_KEY -Vault LocalStore -AsPlainText -ErrorAction Stop
    } catch {
        Write-Host "Token FREELLMAPI_KEY não encontrado no cofre LocalStore." -ForegroundColor Red
        Write-Host "Salve com: Set-Secret -Name FREELLMAPI_KEY -Vault LocalStore"
        exit 1
    }
}

$vars = @{
    ANTHROPIC_BASE_URL                       = $base
    ANTHROPIC_AUTH_TOKEN                     = $key
    ANTHROPIC_MODEL                          = $model
    ANTHROPIC_DEFAULT_OPUS_MODEL             = $model
    ANTHROPIC_DEFAULT_SONNET_MODEL           = $model
    ANTHROPIC_DEFAULT_HAIKU_MODEL            = $model
    ANTHROPIC_SMALL_FAST_MODEL               = $model
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = '1'
}
$key = $null

# Variáveis de autenticação de uma sessão do Claude (app desktop, terminal integrado) teriam
# prioridade sobre o token do FreeLLMAPI; são tiradas do processo filho e devolvidas no fim.
$hostVars = Get-ChildItem Env: | Where-Object {
    $_.Name -match '^(CLAUDECODE|CLAUDE_CODE_.*|CLAUDE_AGENT_SDK_.*|USE_LOCAL_OAUTH|USE_STAGING_OAUTH|ANTHROPIC_.*)$'
} | ForEach-Object { @{ Name = $_.Name; Value = $_.Value } }

# Banner sem acentos de propósito: o console do Windows nem sempre usa UTF-8.
Write-Host ''
Write-Host ' PLANO B: Claude Code via FreeLLMAPI (modelos gratuitos, NAO e o Claude) ' -ForegroundColor Black -BackgroundColor Yellow
Write-Host " Roteador: $base  |  nome de modelo enviado: $model (o roteador escolhe o real)" -ForegroundColor Yellow
Write-Host ' Qualidade menor: revise tudo antes de aceitar edicoes. Nao envie codigo sigiloso.' -ForegroundColor Yellow
Write-Host ''

try {
    foreach ($v in $hostVars) { Remove-Item -Path "Env:$($v.Name)" -ErrorAction SilentlyContinue }
    foreach ($k in $vars.Keys) { Set-Item -Path "Env:$k" -Value $vars[$k] }
    & claude @args
    $code = $LASTEXITCODE
} finally {
    foreach ($k in $vars.Keys) { Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue }
    foreach ($v in $hostVars) { Set-Item -Path "Env:$($v.Name)" -Value $v.Value }
    $vars = $null; $hostVars = $null
}
exit $code
