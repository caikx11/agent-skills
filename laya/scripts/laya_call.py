#!/usr/bin/env python3
"""Cliente local do Laya (convaiinnovations) para a skill `laya`.

Tudo roda no seu PC. Os ajustes (tunings), exemplos e histórico ficam em LAYA_HOME
(padrão: ~/.laya).

Subcomandos:
  status                      Python, pacote laya, pasta de dados e tarefas (sem rede).
  init                        Cria a pasta de dados e o registro.
  tasks                       Lista as tarefas registradas.
  new-task NOME < schema.json Cria a tarefa. O JSON é {"questions": {...}}.
  ask NOME [--teacher]        Lê {"state": ...} no stdin e decide com o Laya.
                              --teacher também pergunta ao Jev e guarda como exemplo.
  correct NOME                Lê {"state": ..., "answers": {...}} no stdin e guarda a correção.
  export NOME                 Gera dataset.jsonl da tarefa para treinar no Kaggle/Colab.
  import-model NOME REPO_ID   Baixa o modelo ajustado do Hub para a pasta da tarefa.
  set-calibration NOME < json Guarda as temperaturas ajustadas, ex.: {"choice_3": 1.7}.

Não instala nada, não faz treino e não lê chaves. A chamada ao Jev (professor) reaproveita o
script da skill `jev`, que cuida da chave.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("USE_TF", "0")  # evita o travamento do transformers com TensorFlow

HOME = Path(os.environ.get("LAYA_HOME", Path.home() / ".laya"))
REGISTRY = HOME / "registry.json"
JEV_SCRIPT = Path.home() / ".agents" / "skills" / "jev" / "scripts" / "jev_call.py"

LOW_CONFIDENCE = 0.60
SPLIT_GAP = 0.20
NOUL_BAND = (0.35, 0.65)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")


def emit(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    sys.exit(code)


def fail(message, code=1, **extra):
    emit({"ok": False, "message": message, **extra}, code)

def read_stdin_json():
    """Lê JSON do stdin tolerando BOM (o PowerShell 5.1 envia UTF-8 com BOM)."""
    raw = sys.stdin.buffer.read()
    return json.loads(raw.decode("utf-8-sig"))


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---- Registro ----------------------------------------------------------------------------
def load_registry():
    if not REGISTRY.exists():
        return {"tasks": {}}
    return json.loads(REGISTRY.read_text(encoding="utf-8-sig"))


def save_registry(reg):
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def task_dir(name):
    if not NAME_RE.match(name or ""):
        fail("nome de tarefa inválido: use minúsculas, números, '-' ou '_'", 64)
    return HOME / "tasks" / name


def get_task(name):
    reg = load_registry()
    if name not in reg["tasks"]:
        fail(f"tarefa '{name}' não existe. Crie com new-task.", 66)
    return reg, reg["tasks"][name]


def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def count_lines(path):
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def has_tuned_model(name):
    model = task_dir(name) / "model"
    return model.exists() and any(model.iterdir())


# ---- Perguntas ---------------------------------------------------------------------------
def validate_questions(questions):
    if not isinstance(questions, dict) or not questions:
        raise ValueError("'questions' precisa ser um objeto não vazio")
    for qid, q in questions.items():
        if not isinstance(q, dict) or q.get("type") not in ("choice", "score", "noul"):
            raise ValueError(f"pergunta '{qid}': tipo deve ser choice, score ou noul")
        if q["type"] == "choice" and isinstance(q.get("criteria"), dict) and len(q["criteria"]) > 20:
            raise ValueError(f"pergunta '{qid}': mais de 20 opções funciona mal no Laya; divida em duas etapas")


def analyze(answers):
    """Mesmos critérios de incerteza da skill jev. Tolerante a chaves ausentes."""
    flags = {}
    for qid, ans in (answers or {}).items():
        if not isinstance(ans, dict):
            continue
        qflags = []
        conf = ans.get("confidence")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE:
            qflags.append("confianca_baixa")
        probs = ans.get("probabilities")
        if isinstance(probs, dict) and len(probs) >= 2:
            values = sorted((float(v) for v in probs.values()), reverse=True)
            if values[0] - values[1] < SPLIT_GAP:
                qflags.append("probabilidades_divididas")
        noul = ans.get("noul")
        if isinstance(noul, (int, float)) and NOUL_BAND[0] <= noul <= NOUL_BAND[1]:
            qflags.append("noul_proximo_de_0_5")
        if qflags:
            flags[qid] = qflags
    return {"needs_review": bool(flags), "flags": flags}


# ---- Comandos ----------------------------------------------------------------------------
def cmd_status():
    try:
        import importlib.util
        laya_ok = importlib.util.find_spec("laya") is not None
    except Exception:
        laya_ok = False
    reg = load_registry() if HOME.exists() else {"tasks": {}}
    emit({
        "python": sys.version.split()[0],
        "laya_instalado": laya_ok,
        "pasta_dados": str(HOME),
        "pasta_existe": HOME.exists(),
        "script_jev_encontrado": JEV_SCRIPT.exists(),
        "tarefas": list(reg["tasks"].keys()),
    })


def cmd_init():
    (HOME / "tasks").mkdir(parents=True, exist_ok=True)
    if not REGISTRY.exists():
        save_registry({"tasks": {}})
    emit({"ok": True, "pasta_dados": str(HOME)})


def cmd_tasks():
    reg = load_registry()
    out = {}
    for name, info in reg["tasks"].items():
        d = task_dir(name)
        out[name] = {
            "modelo_ajustado": has_tuned_model(name),
            "exemplos": count_lines(d / "examples.jsonl"),
            "origem_modelo": info.get("model_repo"),
            "acuracia": info.get("accuracy"),
            "criada_em": info.get("created"),
        }
    emit({"ok": True, "tarefas": out})


def cmd_new_task(name):
    d = task_dir(name)
    try:
        data = read_stdin_json()
        validate_questions(data.get("questions"))
    except (ValueError, json.JSONDecodeError, AttributeError) as err:
        fail(str(err), 64)
    HOME.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    if name in reg["tasks"]:
        fail(f"tarefa '{name}' já existe", 65)
    d.mkdir(parents=True, exist_ok=True)
    (d / "model").mkdir(exist_ok=True)
    (d / "questions.json").write_text(
        json.dumps(data["questions"], ensure_ascii=False, indent=2), encoding="utf-8")
    reg["tasks"][name] = {"created": now(), "model_repo": None, "accuracy": None, "calibration": {}}
    save_registry(reg)
    emit({"ok": True, "tarefa": name, "pasta": str(d)})


def load_agent(name):
    """Modelo ajustado da tarefa se existir; senão o Router (zero-shot)."""
    try:
        import laya
    except ImportError:
        fail("pacote 'laya' não instalado. Oriente: pip install laya (não instale por conta própria).", 2)
    if has_tuned_model(name):
        return laya.load(str(task_dir(name) / "model")), "ajustado"
    return laya.Router(), "zero-shot"


def run_teacher(state, questions):
    if not JEV_SCRIPT.exists():
        return {"ok": False, "message": "script da skill jev não encontrado"}
    payload = json.dumps({"state": state, "questions": questions}, ensure_ascii=False)
    res = subprocess.run([sys.executable, str(JEV_SCRIPT), "ask"], input=payload,
                         capture_output=True, text=True, timeout=120)
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "message": (res.stderr or res.stdout or "sem resposta")[:300]}


def cmd_ask(name, use_teacher):
    reg, info = get_task(name)
    d = task_dir(name)
    questions = json.loads((d / "questions.json").read_text(encoding="utf-8"))
    try:
        req = read_stdin_json()
        state = req["state"]
    except (KeyError, TypeError, json.JSONDecodeError):
        fail("JSON precisa ter 'state'", 64)
    agent, modo = load_agent(name)
    started = time.monotonic()
    result = agent.predict(state, questions)
    elapsed = int((time.monotonic() - started) * 1000)
    answers = result.get("answers") if isinstance(result, dict) else None
    out = {"ok": True, "tarefa": name, "modo": modo, "answers": answers,
           "routing": result.get("routing") if isinstance(result, dict) else None,
           "elapsed_ms": elapsed, **analyze(answers)}
    append_jsonl(d / "history.jsonl", {"ts": now(), "modo": modo, "state_chars": len(str(state)),
                                       "answers": answers, "flags": out["flags"]})
    if use_teacher:
        teacher = run_teacher(state, questions)
        out["teacher"] = {"ok": teacher.get("ok"), "model": teacher.get("model"),
                          "est_cost_display": teacher.get("est_cost_display")}
        if teacher.get("ok"):
            append_jsonl(d / "examples.jsonl", {"ts": now(), "source": "jev", "state": state,
                                                "answers": teacher.get("answers")})
            out["exemplos_total"] = count_lines(d / "examples.jsonl")
        else:
            out["teacher"]["message"] = teacher.get("message")
    emit(out)


def cmd_correct(name):
    get_task(name)
    try:
        req = read_stdin_json()
        state, answers = req["state"], req["answers"]
    except (KeyError, TypeError, json.JSONDecodeError):
        fail("JSON precisa ter 'state' e 'answers'", 64)
    d = task_dir(name)
    append_jsonl(d / "examples.jsonl", {"ts": now(), "source": "usuario", "state": state, "answers": answers})
    emit({"ok": True, "exemplos_total": count_lines(d / "examples.jsonl")})


def cmd_export(name):
    get_task(name)
    d = task_dir(name)
    src = d / "examples.jsonl"
    if not src.exists():
        fail("sem exemplos para exportar", 66)
    questions = json.loads((d / "questions.json").read_text(encoding="utf-8"))
    dst = d / "dataset.jsonl"
    rows = 0
    skipped = 0
    with src.open(encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            ex = json.loads(line)
            if ex.get("needs_review") and "--all" not in sys.argv:
                skipped += 1
                continue
            fout.write(json.dumps({"state": ex["state"], "questions": questions,
                                   "answers": ex["answers"], "source": ex.get("source")},
                                  ensure_ascii=False) + "\n")
            rows += 1
    emit({"ok": True, "arquivo": str(dst), "linhas": rows, "puladas_por_incerteza": skipped,
          "aviso": "revise uma amostra à mão antes de treinar; dados podem ter informação pessoal"})


def cmd_import_model(name, repo_id):
    reg, info = get_task(name)
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        fail("huggingface_hub não instalado (vem junto com transformers).", 2)
    target = task_dir(name) / "model"
    snapshot_download(repo_id=repo_id, local_dir=str(target))
    info["model_repo"] = repo_id
    info["imported"] = now()
    save_registry(reg)
    emit({"ok": True, "tarefa": name, "modelo": repo_id, "pasta": str(target)})


def cmd_set_calibration(name):
    reg, info = get_task(name)
    try:
        temps = read_stdin_json()
        assert isinstance(temps, dict)
    except (AssertionError, json.JSONDecodeError):
        fail("JSON precisa ser um objeto, ex.: {\"choice_3\": 1.7}", 64)
    info["calibration"] = temps
    save_registry(reg)
    emit({"ok": True, "tarefa": name, "calibration": temps})


def main(argv):
    usage = "uso: laya_call.py status|init|tasks|new-task N|ask N [--teacher]|correct N|export N|import-model N REPO|set-calibration N"
    if len(argv) < 2:
        print(usage, file=sys.stderr)
        sys.exit(64)
    cmd, args = argv[1], argv[2:]
    plain = [a for a in args if not a.startswith("--")]
    try:
        if cmd == "status":
            cmd_status()
        elif cmd == "init":
            cmd_init()
        elif cmd == "tasks":
            cmd_tasks()
        elif cmd == "new-task" and plain:
            cmd_new_task(plain[0])
        elif cmd == "ask" and plain:
            cmd_ask(plain[0], "--teacher" in args)
        elif cmd == "correct" and plain:
            cmd_correct(plain[0])
        elif cmd == "export" and plain:
            cmd_export(plain[0])
        elif cmd == "import-model" and len(plain) >= 2:
            cmd_import_model(plain[0], plain[1])
        elif cmd == "set-calibration" and plain:
            cmd_set_calibration(plain[0])
        else:
            print(usage, file=sys.stderr)
            sys.exit(64)
    except SystemExit:
        raise
    except Exception as err:  # erro inesperado: mensagem curta, sem traceback com dados
        fail(f"{type(err).__name__}: {str(err)[:300]}", 1)


if __name__ == "__main__":
    main(sys.argv)
