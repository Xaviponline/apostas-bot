"""Diagnostico read-only de elegibilidade SCOUT e calibracao de snapshots."""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from scout_shadow import _possiveis, _liga


def _numero(v):
    try:
        x = float(v)
        return x if isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def relatorio_scout_modelo(dados, agora=None):
    agora = agora or datetime.now(timezone.utc)
    hoje = agora.astimezone(ZoneInfo("Europe/Lisbon")).date().isoformat()
    snapshots = dados.get("previsoes", []) if isinstance(dados, dict) else []
    hoje_s = [p for p in snapshots if isinstance(p, dict) and p.get("data_jogo") == hoje]
    linhas = [f"🔬 SCOUT + MODELO — {hoje}", f"📚 Snapshots do dia: {len(hoje_s)}"]
    motivos = Counter()
    top = []
    for p in hoje_s:
        candidatos, exclusoes = _possiveis([p], agora)
        motivo = next(iter(exclusoes), "elegivel") if not candidatos else "elegivel"
        motivos[motivo] += 1
        try:
            rank = int(p.get("ranking_modelo"))
        except (TypeError, ValueError, OverflowError):
            rank = 999
        if 1 <= rank <= 5:
            top.append((rank, p, motivo))
    linhas.append("🔎 Exclusões: " + (", ".join(f"{k}={v}" for k, v in motivos.most_common()) or "nenhuma"))
    for rank, p, motivo in sorted(top, key=lambda x: (x[0], x[1].get("casa", ""))):
        liga = str(p.get("liga") or "?")
        sport = _liga(p)
        linhas.extend([
            f"#{rank} {p.get('casa', '?')} vs {p.get('fora', '?')}",
            f"   {p.get('mercado', '?')} | {liga} | {motivo}",
            f"   Mapa: {sport or 'não configurado'} | Prob. {_fmt_percent(p.get('probabilidade'))} | Qualidade {p.get('qualidade', '?')}",
        ])
    # Avaliacao retrospectiva apenas de registos liquidados com dados originais.
    validos = []
    golos = []
    for p in snapshots:
        if not isinstance(p, dict) or p.get("resultado_binario") not in (0, 1):
            continue
        prob = _numero(p.get("probabilidade"))
        resultado = p.get("resultado_binario")
        if prob is not None and 0 <= prob <= 1 and resultado in (0, 1, False, True):
            validos.append((prob, int(resultado)))
        d = p.get("diagnostico_modelo")
        if not isinstance(d, dict):
            continue
        lc, lf = _numero(d.get("lambda_casa")), _numero(d.get("lambda_fora"))
        gc, gf = _numero(p.get("golos_casa")), _numero(p.get("golos_fora"))
        if None not in (lc, lf, gc, gf):
            golos.append((lc + lf, gc + gf))
    linhas.append(f"📊 Calibração histórica (seleções liquidadas): {len(validos)}")
    if validos:
        brier = sum((p-y)**2 for p,y in validos) / len(validos)
        linhas.append(f"   Prob. média {_fmt_percent(sum(p for p,_ in validos)/len(validos))} | Acerto {100*sum(y for _,y in validos)/len(validos):.1f}% | Brier {brier:.3f}")
    if golos:
        linhas.append(f"⚽ Golos previstos {sum(a for a,_ in golos)/len(golos):.2f} | Reais {sum(b for _,b in golos)/len(golos):.2f} | n={len(golos)}")
    linhas.append("ℹ️ Amostra selecionada, não mede calibração de todos os jogos. Snapshots sem dados completos são excluídos.")
    linhas.append("🔒 Leitura local, zero API, sem alterar SCOUT, V1.3, CLV ou modelo.")
    return "\n".join(linhas)


def _fmt_percent(v):
    n = _numero(v)
    return f"{100*n:.1f}%" if n is not None else "não registada"
