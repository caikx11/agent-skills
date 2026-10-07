#!/usr/bin/env python3
"""Cliente mínimo (somente biblioteca padrão) do OpenRouter para a skill `nemo`.

Delega subtarefas ao NVIDIA Nemotron 3 Ultra (550B, MoE) e devolve o resultado para o
modelo principal revisar. Regra: o Nemo rascunha; o modelo principal revisa e integra.

Subcomandos:
  status           Informa se a variável/cofre existe. Não faz chamada de rede e não revela a chave.
  ask              Lê um JSON de tarefa no stdin e chama a API (formato na SKILL.md).
  test             Chama a API com uma tarefa de programação totalmente fictícia.
  Opção --dry-run  (ask/test) Mostra o corpo da requisição e sai: sem chave, sem rede.

Segurança: a chave é lida apenas em memória, o cabeçalho é montado só na hora da chamada,
nada que contenha a chave é impresso ou gravado, e o conteúdo enviado passa por um bloqueio
de arquivos e padrões de segredo antes de sair da máquina.
"""
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---- Constantes (todas num único lugar, para revisão fácil) -----------------------------
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
MODEL_ENV = "NEMO_MODEL"           # permite trocar o modelo (ex.: a versão paga) sem editar o script
ENV_VAR = "OPENROUTER_API_KEY"
VAULT_SERVICE = "openrouter-api-key"   # macOS Keychain
LINUX_SERVICE = "openrouter"           # Linux Secret Service

TASKS = {"draft", "tests", "summarize", "review", "extract", "ask"}
EFFORTS = {"low", "medium", "high"}

DEFAULT_MAX_TOKENS = 8000
MAX_MAX_TOKENS = 60000
DEFAULT_MAX_INPUT_CHARS = 400_000      # ~100k tokens; evita mandar repositórios inteiros por engano
HARD_MAX_INPUT_CHARS = 2_000_000
MAX_FILE_BYTES = 1_500_000

MAX_RETRIES = 3          # retentativas além da 1ª tentativa (429, 502, 503, 529)
RETRY_CODES = (429, 502, 503, 529)
BACKOFF_BASE_S = 2.0     # 2s, 4s, 8s ... (com jitter), respeitando retry-after
BACKOFF_CAP_S = 30.0
TIMEOUT_S = 300          # modelo grande no tier gratuito pode demorar

# Instruções de sistema por tipo de tarefa. Curtas de propósito: o pedido detalhado vem em `instructions`.
SYSTEM_PROMPTS = {
    "draft": (
        "Você é um engenheiro de software sênior. Gere código completo e funcional para o pedido, "
        "seguindo o estilo, as convenções e as bibliotecas do contexto fornecido. Não invente APIs "
        "que não aparecem no contexto. Responda só com o código (em blocos com a linguagem) e, no "
        "fim, no máximo 5 linhas de observações sobre suposições feitas."
    ),
    "tests": (
        "Você é um engenheiro de testes. Escreva testes automatizados para o código fornecido, usando "
        "o framework indicado (ou o que o contexto já usa). Cubra o caminho feliz, bordas e erros. "
        "Não altere o código testado. Responda só com o código dos testes e uma lista curta dos casos cobertos."
    ),
    "summarize": (
        "Resuma o conteúdo fornecido com precisão. Cite nomes de arquivos, funções e linhas quando "
        "existirem. Não invente nada que não esteja no texto; se algo for incerto, diga. Use tópicos."
    ),
    "review": (
        "Você é um revisor de código rigoroso. Procure bugs reais, falhas de segurança, condições de "
        "corrida e erros de lógica no código fornecido. Para cada achado, dê: arquivo/trecho, o problema, "
        "um cenário concreto que o dispara e a correção sugerida. Ignore estilo. Se não houver problemas "
        "reais, diga isso. Ordene do mais grave ao menos grave."
    ),
    "extract": (
        "Extraia do conteúdo fornecido exatamente as informações pedidas e responda somente com JSON "
        "válido, sem texto antes ou depois. Use null quando a informação não existir."
    ),
    "ask": (
        "Responda ao pedido de forma direta e técnica, baseando-se no contexto fornecido. Se o contexto "
        "não for suficiente, diga o que falta em vez de inventar."
    ),
}

# Arquivos que nunca saem da máquina, mesmo que listados em `files`.
BLOCKED_NAME_PATTERNS = [
    r"^\.env(\..*)?$", r".*\.pem$", r".*\.key$", r".*\.pfx$", r".*\.p12$", r".*\.kdbx$",
    r"^id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$", r"^\.npmrc$", r"^\.pypirc$", r"^\.netrc$",
    r"^credentials(\..*)?$", r"^secrets?(\..*)?$", r".*\.keystore$", r".*\.jks$",
]
# Padrões de segredo no conteúdo. Bloqueiam o envio; o valor encontrado nunca é impresso.
SECRET_PATTERNS = {
    "chave_privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "aws_access_key": r"\bAKIA[0-9A-Z]{16}\b",
    "chave_openai_anthropic_openrouter": r"\bsk-(?:or-|ant-|proj-)?[A-Za-z0-9_-]{20,}",
    "token_github": r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    "token_slack": r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
    "chave_google": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "jwt": r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "atribuicao_de_segredo": (
        r"(?i)\b(?:password|passwd|senha|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b"
        r"\s*[:=]\s*[\"']?[^\s\"'<>{}$]{8,}"
    ),
    "url_com_credencial": r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]{4,}@",
}


# ---- Chave ------------------------------------------------------------------------------
def _run_quiet(cmd):
    """Executa um comando e devolve a saída (str) ou None. Nunca imprime stdout/stderr."""
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    value = res.stdout.strip()
    return value or None


def _vault_commands():
    system = platform.system()
    if system == "Darwin":
        user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        return [["security", "find-generic-password", "-a", user, "-s", VAULT_SERVICE, "-w"]]
    if system == "Windows":
        script = f"Get-Secret -Name {ENV_VAR} -Vault LocalStore -AsPlainText"
        cmds = []
        for shell in ("pwsh", "powershell"):
            if shutil.which(shell):
                cmds.append([shell, "-NoProfile", "-NonInteractive", "-Command", script])
        return cmds
    if shutil.which("secret-tool"):
        return [["secret-tool", "lookup", "service", LINUX_SERVICE, "name", ENV_VAR]]
    return []


def get_key():
    """Devolve (chave, origem). Origem: 'env', 'vault' ou None. A chave nunca é impressa."""
    value = os.environ.get(ENV_VAR, "").strip()
    if value:
        return value, "env"
    for cmd in _vault_commands():
        value = _run_quiet(cmd)
        if value:
            return value, "vault"
    return None, None


def sanitize(text, key=None):
    text = str(text)
    if key:
        text = text.replace(key, "[REDACTED]")
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-or-[A-Za-z0-9_-]+", "[REDACTED]", text)
    return text[:400]


def current_model():
    return os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL


# ---- Montagem do conteúdo e guardrails --------------------------------------------------
def _blocked_name(path):
    name = path.name.lower()
    return any(re.match(p, name) for p in BLOCKED_NAME_PATTERNS)


def load_files(paths):
    """Lê arquivos de texto. Devolve (lista de (rótulo, texto), erros)."""
    loaded, errors = [], []
    for raw in paths:
        path = Path(os.path.expanduser(str(raw)))
        label = str(raw)
        if _blocked_name(path):
            errors.append({"file": label, "reason": "arquivo_sensivel_bloqueado"})
            continue
        if not path.is_file():
            errors.append({"file": label, "reason": "nao_encontrado"})
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append({"file": label, "reason": "grande_demais"})
            continue
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            errors.append({"file": label, "reason": "binario"})
            continue
        loaded.append((label, data.decode("utf-8", "replace")))
    return loaded, errors


def scan_secrets(text):
    """Devolve a lista de tipos de segredo encontrados (sem os valores)."""
    return sorted(kind for kind, pat in SECRET_PATTERNS.items() if re.search(pat, text))


def build_user_message(req, files):
    parts = [f"## Pedido\n{req['instructions'].strip()}"]
    if req.get("context"):
        parts.append(f"## Contexto\n{str(req['context']).strip()}")
    for label, text in files:
        parts.append(f"## Arquivo: {label}\n```\n{text}\n```")
    return "\n\n".join(parts)


def validate_request(obj):
    if not isinstance(obj, dict):
        raise ValueError("o pedido precisa ser um objeto JSON")
    task = obj.get("task")
    if task not in TASKS:
        raise ValueError("'task' deve ser um de: " + ", ".join(sorted(TASKS)))
    if not str(obj.get("instructions") or "").strip():
        raise ValueError("'instructions' é obrigatório")
    files = obj.get("files") or []
    if not isinstance(files, list):
        raise ValueError("'files' precisa ser uma lista de caminhos")
    effort = obj.get("effort", "medium")
    if effort not in EFFORTS:
        raise ValueError("'effort' deve ser low, medium ou high")
    max_tokens = int(obj.get("max_tokens") or DEFAULT_MAX_TOKENS)
    if not 1 <= max_tokens <= MAX_MAX_TOKENS:
        raise ValueError(f"'max_tokens' deve ficar entre 1 e {MAX_MAX_TOKENS}")
    max_input = int(obj.get("max_input_chars") or DEFAULT_MAX_INPUT_CHARS)
    if not 1 <= max_input <= HARD_MAX_INPUT_CHARS:
        raise ValueError(f"'max_input_chars' deve ficar entre 1 e {HARD_MAX_INPUT_CHARS}")
    schema = obj.get("json_schema")
    if schema is not None and task != "extract":
        raise ValueError("'json_schema' só vale para task 'extract'")
    return {
        "task": task,
        "instructions": str(obj["instructions"]),
        "context": obj.get("context"),
        "files": files,
        "effort": effort,
        "max_tokens": max_tokens,
        "max_input_chars": max_input,
        "json_schema": schema,
        "temperature": obj.get("temperature"),
    }


def build_payload(req):
    """Monta o corpo da API ou devolve um erro de guardrail (dict com ok: False)."""
    files, file_errors = load_files(req["files"])
    if file_errors:
        return None, {"ok": False, "status": "files_rejected", "file_errors": file_errors,
                      "message": "Corrija ou remova os arquivos listados. Nada foi enviado."}
    user_msg = build_user_message(req, files)
    found = scan_secrets(user_msg)
    if found:
        return None, {"ok": False, "status": "secret_detected", "secret_kinds": found,
                      "message": "Possível segredo no conteúdo. Remova ou mascare antes de enviar. "
                                 "Nada foi enviado."}
    if len(user_msg) > req["max_input_chars"]:
        return None, {"ok": False, "status": "input_too_large", "chars": len(user_msg),
                      "limit": req["max_input_chars"],
                      "message": "Conteúdo maior que o limite. Envie só os trechos necessários "
                                 "ou aumente 'max_input_chars' conscientemente. Nada foi enviado."}
    payload = {
        "model": current_model(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[req["task"]]},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": req["max_tokens"],
        "reasoning": {"effort": req["effort"], "exclude": True},
        "temperature": req["temperature"] if req["temperature"] is not None
        else (0.2 if req["task"] in ("draft", "tests", "extract", "review") else 0.4),
    }
    if req["task"] == "extract":
        if req["json_schema"]:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "extracao", "strict": True, "schema": req["json_schema"]},
            }
        else:
            payload["response_format"] = {"type": "json_object"}
    meta = {"files_sent": [label for label, _ in files], "input_chars": len(user_msg)}
    return (payload, meta), None


# ---- Chamada ----------------------------------------------------------------------------
def _error_hint(status, message):
    low = message.lower()
    if status == 404 and ("data policy" in low or "no endpoints" in low):
        return ("Os modelos :free exigem que a conta permita o registro de prompts. Ajuste em "
                "openrouter.ai/settings/privacy, ou use a versão paga com NEMO_MODEL.")
    if status == 401:
        return "Chave inválida ou revogada. Gere outra em openrouter.ai/keys e salve no cofre."
    if status == 402:
        return "Sem créditos para este modelo/requisição."
    if status == 429:
        return "Limite de requisições do tier gratuito atingido. Tente mais tarde."
    if status in (502, 503, 529):
        return ("Provedor sobrecarregado ou fora do ar (comum no tier :free). Tente mais tarde "
                "ou use a versão paga com NEMO_MODEL.")
    return None


def _backoff(attempts, retry_after=None):
    try:
        delay = float(retry_after) if retry_after else None
    except ValueError:
        delay = None
    if delay is None:
        delay = BACKOFF_BASE_S * (2 ** (attempts - 1))
    time.sleep(min(delay, BACKOFF_CAP_S) + random.uniform(0, 0.5))


def call_api(payload, key):
    """POST com retentativas limitadas. Retorna dict de resultado ou de erro."""
    body = json.dumps(payload).encode("utf-8")
    started = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        req = urllib.request.Request(ENDPOINT, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + key)  # montado só em tempo de execução
        req.add_header("X-Title", "nemo skill")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # O OpenRouter às vezes devolve HTTP 200 com o erro do provedor no corpo.
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                msg = sanitize(err.get("message", err), key)
                code = err.get("code")
                if code in RETRY_CODES and attempts <= MAX_RETRIES:
                    _backoff(attempts)
                    continue
                elapsed = int((time.monotonic() - started) * 1000)
                return {"ok": False, "status": code, "message": msg,
                        "hint": _error_hint(code, msg), "elapsed_ms": elapsed, "attempts": attempts}
            elapsed = int((time.monotonic() - started) * 1000)
            return {"ok": True, "data": data, "elapsed_ms": elapsed, "attempts": attempts}
        except urllib.error.HTTPError as err:
            raw = ""
            try:
                raw = err.read().decode("utf-8", "replace")
            except Exception:
                pass
            if err.code in RETRY_CODES and attempts <= MAX_RETRIES:
                _backoff(attempts, err.headers.get("retry-after") if err.headers else None)
                continue
            elapsed = int((time.monotonic() - started) * 1000)
            msg = raw
            try:
                msg = json.loads(raw).get("error", {}).get("message", raw)
            except Exception:
                pass
            msg = sanitize(msg or err.reason, key)
            return {"ok": False, "status": err.code, "message": msg,
                    "hint": _error_hint(err.code, msg), "elapsed_ms": elapsed, "attempts": attempts}
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            elapsed = int((time.monotonic() - started) * 1000)
            return {"ok": False, "status": None,
                    "message": sanitize("falha de conexão: " + str(err), key),
                    "elapsed_ms": elapsed, "attempts": attempts}
        except ValueError:
            elapsed = int((time.monotonic() - started) * 1000)
            return {"ok": False, "status": None, "message": "resposta não é JSON válido",
                    "elapsed_ms": elapsed, "attempts": attempts}


# ---- Análise do resultado ---------------------------------------------------------------
def analyze(task, content, finish_reason):
    flags = []
    if not content.strip():
        flags.append("resposta_vazia")
    if finish_reason == "length":
        flags.append("truncado_por_max_tokens")
    if finish_reason == "content_filter":
        flags.append("filtrado")
    parsed = None
    if task == "extract" and content.strip():
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            parsed = json.loads(text)
        except ValueError:
            flags.append("json_invalido")
    if task in ("draft", "tests") and content.strip() and "```" not in content:
        flags.append("sem_bloco_de_codigo")
    return flags, parsed


def build_output(task, result, meta):
    if not result["ok"]:
        out = {k: result.get(k) for k in ("status", "message", "hint", "elapsed_ms", "attempts")}
        out["ok"] = False
        return out
    data = result["data"]
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    finish = choice.get("finish_reason")
    usage = data.get("usage") or {}
    cost = usage.get("cost")
    flags, parsed = analyze(task, content, finish)
    out = {
        "ok": True,
        "model": data.get("model"),
        "provider": data.get("provider"),
        "task": task,
        "content": content,
        "finish_reason": finish,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        },
        "est_cost_usd": cost,
        "est_cost_display": "US$ {:.6f}".format(float(cost)) if cost is not None else "US$ 0 (free)",
        "elapsed_ms": result["elapsed_ms"],
        "attempts": result["attempts"],
        "needs_review": True,     # sempre: a saída do Nemo é rascunho
        "flags": flags,
    }
    if parsed is not None:
        out["parsed_json"] = parsed
    out.update(meta)
    return out


# ---- Teste fictício ---------------------------------------------------------------------
def fictional_test_request():
    return {
        "task": "draft",
        "instructions": (
            "Escreva em Python 3 uma função `normalizar_sku(texto: str) -> str` para a loja fictícia "
            "Papelaria Lua Azul. Regras: remover acentos, converter para maiúsculas, trocar espaços e "
            "underlines por hífen, remover caracteres que não sejam A-Z, 0-9 ou hífen, colapsar hífens "
            "repetidos e remover hífens nas pontas. Inclua 4 testes pytest."
        ),
        "context": "Exemplos fictícios: 'caderno   espiral_A4' -> 'CADERNO-ESPIRAL-A4'; "
                   "'  Lápis nº2 ' -> 'LAPIS-N2'.",
        "files": [],
        "effort": "low",
        "max_tokens": 3000,
        "max_input_chars": DEFAULT_MAX_INPUT_CHARS,
        "json_schema": None,
        "temperature": None,
    }


# ---- Comandos ---------------------------------------------------------------------------
def emit(obj, code=0):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.exit(code)


def cmd_status():
    env_present = bool(os.environ.get(ENV_VAR, "").strip())
    vault_found = None
    if not env_present:
        key, source = get_key()
        vault_found = source == "vault"
        key = None  # descarta imediatamente
    emit({
        "model": current_model(),
        "model_overridden": bool(os.environ.get(MODEL_ENV, "").strip()),
        "endpoint": ENDPOINT,
        "env_var_present": env_present,
        "vault_key_found": vault_found,
        "key_available": env_present or bool(vault_found),
        "platform": platform.system(),
    })


def run_request(req, dry_run):
    built, error = build_payload(req)
    if error:
        emit(error, 3)
    payload, meta = built
    if dry_run:
        emit({"dry_run": True, "endpoint": ENDPOINT, "request_body": payload, **meta})
    key, _source = get_key()
    if not key:
        emit({"ok": False, "status": "no_key",
              "message": (f"{ENV_VAR} não encontrada na variável de ambiente nem no cofre do "
                          "sistema. Oriente o usuário a cadastrá-la (references/setup-chave.md); "
                          "nunca peça a chave no chat.")}, 2)
    result = call_api(payload, key)
    key = None
    out = build_output(req["task"], result, meta)
    emit(out, 0 if out["ok"] else 1)


def main(argv):
    if len(argv) < 2 or argv[1] not in ("status", "ask", "test"):
        print("uso: nemo_call.py status | ask [--dry-run] < tarefa.json | test [--dry-run]",
              file=sys.stderr)
        sys.exit(64)
    command = argv[1]
    dry_run = "--dry-run" in argv[2:]
    if command == "status":
        cmd_status()
    elif command == "ask":
        try:
            raw_req = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
            req = validate_request(raw_req)
        except (ValueError, TypeError, json.JSONDecodeError) as err:
            emit({"ok": False, "status": "invalid_request", "message": str(err)}, 64)
        run_request(req, dry_run)
    else:
        run_request(fictional_test_request(), dry_run)


if __name__ == "__main__":
    main(sys.argv)
