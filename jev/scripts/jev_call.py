#!/usr/bin/env python3
"""Cliente mínimo (somente biblioteca padrão) da API System One da TypeSafe para a skill `jev`.

Subcomandos:
  status           Informa se a variável/cofre existe. Não faz chamada de rede e não revela a chave.
  ask              Lê um JSON {"state": ..., "questions": {...}} no stdin e chama a API.
  test             Chama a API com um e-mail comercial totalmente fictício.
  Opção --dry-run  (ask/test) Mostra o corpo da requisição e sai: sem chave, sem rede.

Segurança: a chave é lida apenas em memória, o cabeçalho é montado só na hora da chamada,
e nada que contenha a chave é impresso ou gravado.
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
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
ENV_VAR = "TYPESAFE_API_KEY"
ALLOWED_TYPES = {"choice", "score", "noul"}

# Preço documentado: US$ 0,042 por milhão de tokens de entrada; saída é gratuita.
PRICE_PER_INPUT_TOKEN_USD = 0.042 / 1_000_000

MAX_RETRIES = 3          # retentativas além da 1ª tentativa (apenas 429/529)
BACKOFF_BASE_S = 1.0     # 1s, 2s, 4s ... (com jitter), respeitando retry-after
BACKOFF_CAP_S = 20.0
TIMEOUT_S = 60

LOW_CONFIDENCE = 0.60    # choice/score abaixo disso: revisar
SPLIT_GAP = 0.20         # diferença entre as 2 maiores probabilidades abaixo disso: dividido
NOUL_BAND = (0.35, 0.65)  # noul nessa faixa: próximo de 0,5


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
        return [["security", "find-generic-password", "-a", user, "-s", "typesafe-api-key", "-w"]]
    if system == "Windows":
        script = f"Get-Secret -Name {ENV_VAR} -Vault LocalStore -AsPlainText"
        cmds = []
        for shell in ("pwsh", "powershell"):
            if shutil.which(shell):
                cmds.append([shell, "-NoProfile", "-NonInteractive", "-Command", script])
        return cmds
    if shutil.which("secret-tool"):
        return [["secret-tool", "lookup", "service", "typesafe-ai", "name", ENV_VAR]]
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
    return text[:300]


# ---- Chamada ----------------------------------------------------------------------------
def call_api(payload, key):
    """POST com retentativas limitadas (429/529). Retorna dict de resultado ou de erro."""
    body = json.dumps(payload).encode("utf-8")
    started = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        req = urllib.request.Request(ENDPOINT, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + key)  # montado só em tempo de execução
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            elapsed = int((time.monotonic() - started) * 1000)
            return {"ok": True, "data": data, "elapsed_ms": elapsed, "attempts": attempts}
        except urllib.error.HTTPError as err:
            raw = ""
            try:
                raw = err.read().decode("utf-8", "replace")
            except Exception:
                pass
            if err.code in (429, 529) and attempts <= MAX_RETRIES:
                retry_after = err.headers.get("retry-after") if err.headers else None
                try:
                    delay = float(retry_after) if retry_after else None
                except ValueError:
                    delay = None
                if delay is None:
                    delay = BACKOFF_BASE_S * (2 ** (attempts - 1))
                delay = min(delay, BACKOFF_CAP_S) + random.uniform(0, 0.25)
                time.sleep(delay)
                continue
            elapsed = int((time.monotonic() - started) * 1000)
            return {
                "ok": False,
                "status": err.code,
                "message": sanitize(raw or err.reason, key),
                "elapsed_ms": elapsed,
                "attempts": attempts,
            }
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            elapsed = int((time.monotonic() - started) * 1000)
            return {
                "ok": False,
                "status": None,
                "message": sanitize("falha de conexão: " + str(err), key),
                "elapsed_ms": elapsed,
                "attempts": attempts,
            }
        except ValueError:
            elapsed = int((time.monotonic() - started) * 1000)
            return {
                "ok": False,
                "status": None,
                "message": "resposta não é JSON válido",
                "elapsed_ms": elapsed,
                "attempts": attempts,
            }


# ---- Análise de incerteza ---------------------------------------------------------------
def _top_two_gap(probs):
    values = sorted((float(v) for v in probs.values()), reverse=True)
    if len(values) < 2:
        return 1.0
    return values[0] - values[1]


def analyze(answers):
    flags = {}
    confidences = {}
    for qid, ans in answers.items():
        qflags = []
        kind = ans.get("type")
        if kind in ("choice", "score"):
            conf = ans.get("confidence")
            if conf is not None:
                confidences[qid] = conf
                if conf < LOW_CONFIDENCE:
                    qflags.append("confianca_baixa")
            probs = ans.get("probabilities") or {}
            if probs and _top_two_gap(probs) < SPLIT_GAP:
                qflags.append("probabilidades_divididas")
        elif kind == "noul":
            value = ans.get("noul")
            if value is not None and NOUL_BAND[0] <= value <= NOUL_BAND[1]:
                qflags.append("noul_proximo_de_0_5")
        if qflags:
            flags[qid] = qflags
    return {
        "needs_review": bool(flags),
        "flags": flags,
        "confidences": confidences,
    }


def build_output(result):
    if not result["ok"]:
        return {
            "ok": False,
            "status": result["status"],
            "message": result["message"],
            "elapsed_ms": result["elapsed_ms"],
            "attempts": result["attempts"],
        }
    data = result["data"]
    usage = data.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    cost = input_tokens * PRICE_PER_INPUT_TOKEN_USD
    out = {
        "ok": True,
        "model": data.get("model"),
        "answers": data.get("answers"),
        "usage": usage,
        "elapsed_ms": result["elapsed_ms"],
        "attempts": result["attempts"],
        "est_cost_usd": round(cost, 9),
        "est_cost_display": "US$ {:.6f}".format(cost),
    }
    out.update(analyze(data.get("answers") or {}))
    return out


# ---- Requisições ------------------------------------------------------------------------
def validate_request(obj):
    if not isinstance(obj, dict) or "state" not in obj or "questions" not in obj:
        raise ValueError("JSON precisa ter 'state' e 'questions'")
    questions = obj["questions"]
    if not isinstance(questions, dict) or not questions:
        raise ValueError("'questions' precisa ser um objeto não vazio")
    for qid, q in questions.items():
        qtype = q.get("type") if isinstance(q, dict) else None
        if qtype not in ALLOWED_TYPES:
            raise ValueError(f"pergunta '{qid}': tipo deve ser choice, score ou noul")
    return {"state": obj["state"], "model": MODEL, "questions": questions}


def fictional_test_request():
    email = (
        "De: Marina Teixeira <marina@exemplo.invalid>\n"
        "Assunto: Orçamento para 300 uniformes\n\n"
        "Olá! Sou compradora da Cobalto Têxtil (empresa fictícia). Precisamos de "
        "300 uniformes até o fim do mês e queremos fechar com um fornecedor ainda "
        "esta semana. Podem enviar prazo e preço por unidade? Posso ligar amanhã."
    )
    questions = {
        "lead_promissor": {
            "type": "score",
            "instructions": "Quão promissor é este e-mail como lead comercial?",
            "criteria": [
                "Sem potencial: spam ou irrelevante",
                "Potencial baixo: curiosidade vaga",
                "Potencial médio: interesse real, sem urgência",
                "Potencial alto: necessidade clara e prazo",
                "Potencial muito alto: pronto para fechar",
            ],
        },
        "tipo_email": {
            "type": "choice",
            "instructions": "Que tipo de e-mail é este?",
            "criteria": {
                "pedido_orcamento": "Pede preço, prazo ou proposta",
                "suporte": "Problema com algo já comprado",
                "parceria": "Propõe parceria ou revenda",
                "spam": "Mensagem em massa ou irrelevante",
                "outro": "Nenhuma das anteriores",
            },
        },
        "precisa_resposta_pessoal": {
            "type": "noul",
            "instructions": "Este e-mail precisa de uma resposta pessoal (humana), e não só automática?",
        },
    }
    return email, {"state": email, "model": MODEL, "questions": questions}


# ---- Comandos ---------------------------------------------------------------------------
def emit(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.exit(code)


def cmd_status():
    env_present = bool(os.environ.get(ENV_VAR, "").strip())
    vault_found = None
    if not env_present:
        key, source = get_key()
        vault_found = source == "vault"
        key = None  # descarta imediatamente
    emit(
        {
            "model": MODEL,
            "endpoint": ENDPOINT,
            "env_var_present": env_present,
            "vault_key_found": vault_found,
            "key_available": env_present or bool(vault_found),
            "platform": platform.system(),
        }
    )


def log_to_laya(task, payload, out):
    """Grava a decisão do Jev como exemplo de treino da tarefa `task` do Laya.

    Só grava se a tarefa já existir e tiver exatamente as mesmas perguntas. Nunca derruba a
    chamada ao Jev: qualquer problema vira um aviso em `laya_log`. Não imprime o texto do state.
    """
    home = Path(os.environ.get("LAYA_HOME", Path.home() / ".laya"))
    try:
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,60}$", str(task)):
            return {"saved": False, "reason": "nome_de_tarefa_invalido"}
        tdir = home / "tasks" / task
        qfile = tdir / "questions.json"
        if not qfile.exists():
            return {"saved": False, "reason": "tarefa_nao_existe"}
        saved_q = json.loads(qfile.read_text(encoding="utf-8-sig"))
        sent_q = payload["questions"]
        same = set(saved_q) == set(sent_q) and all(
            saved_q[k].get("type") == sent_q[k].get("type") for k in saved_q
        )
        if not same:
            return {"saved": False, "reason": "perguntas_diferentes_da_tarefa"}
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "jev",
            "teacher_model": out.get("model"),
            "state": payload["state"],
            "answers": out.get("answers"),
            "needs_review": out.get("needs_review", False),
            "flags": out.get("flags", {}),
        }
        with (tdir / "examples.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"saved": True, "task": task}
    except Exception as err:
        return {"saved": False, "reason": sanitize("erro: " + type(err).__name__)}


def run_request(payload, dry_run, laya_task=None):
    if dry_run:
        emit({"dry_run": True, "endpoint": ENDPOINT, "request_body": payload})
    key, _source = get_key()
    if not key:
        emit(
            {
                "ok": False,
                "status": "no_key",
                "message": (
                    f"{ENV_VAR} não encontrada na variável de ambiente nem no cofre do "
                    "sistema. Oriente o usuário a cadastrá-la (instruções na skill); "
                    "nunca peça a chave no chat."
                ),
            },
            2,
        )
    result = call_api(payload, key)
    out = build_output(result)
    key = None
    if out["ok"] and laya_task:
        out["laya_log"] = log_to_laya(laya_task, payload, out)
    emit(out, 0 if out["ok"] else 1)


def main(argv):
    if len(argv) < 2 or argv[1] not in ("status", "ask", "test"):
        print("uso: jev_call.py status | ask [--dry-run] < pedido.json | test [--dry-run]", file=sys.stderr)
        sys.exit(64)
    command = argv[1]
    dry_run = "--dry-run" in argv[2:]
    if command == "status":
        cmd_status()
    elif command == "ask":
        try:
            raw_req = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
            laya_task = raw_req.get("laya_task") if isinstance(raw_req, dict) else None
            payload = validate_request(raw_req)  # laya_task nunca vai para a API
        except (ValueError, json.JSONDecodeError) as err:
            emit({"ok": False, "status": "invalid_request", "message": str(err)}, 64)
        run_request(payload, dry_run, laya_task)
    else:
        email, payload = fictional_test_request()
        if dry_run:
            run_request(payload, True)
        key, _ = get_key()
        if not key:
            run_request(payload, False)  # emite o erro de chave ausente
        result = call_api(payload, key)
        key = None
        out = build_output(result)
        out["test_email"] = email
        emit(out, 0 if out["ok"] else 1)


if __name__ == "__main__":
    main(sys.argv)
