"""Prova documental, somente leitura, da odd de entrada e CLV V1.3.

Compara exclusivamente campos originais da coorte fixa com observações locais
rastreáveis do mesmo ID de jogo + mercado. Não reconstitui CLV, não altera
fechos nem infere odds executáveis numa casa de apostas.
"""
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import json

from odds_rastreio import RastreioOdds

MAX_RESTANTES = 6


def _numero(valor, *, odd=False):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    if not isfinite(n) or (odd and not (1 < n < 1000)):
        return None
    return n


def _preco(valor):
    n = _numero(valor, odd=True)
    return f"{n:.2f}".replace(".", ",") if n is not None else "não registada"


def _hora(valor):
    if not valor:
        return "não registada"
    try:
        if type(valor) in (float, int):
            dt = datetime.fromtimestamp(float(valor), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return "sem fuso registado"
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("Europe/Lisbon")).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError, OverflowError, OSError):
        return "inválida"


def _texto(valor, limite=95):
    return str(valor).replace("\r", " ").replace("\n", " ")[:limite] if valor not in (None, "") else "não registado"


def _historico(rastreio, p):
    path = getattr(rastreio, "path", None)
    if path is None:
        return 0, [], "não configurado"
    path = Path(path)
    if not path.exists():
        return 0, [], "sem ficheiro"
    if path.is_symlink() or path.stat().st_size > RastreioOdds.MAX_BYTES:
        raise RuntimeError("Rastreio inseguro ou acima do limite")
    event = str(p.get("event_id") or "")
    market = str(p.get("mercado") or "")
    if not event or not market:
        return 0, [], "identidade original incompleta"
    ts = _numero(p.get("timestamp_jogo"))
    total = 0
    recentes = []
    with path.open("r", encoding="utf-8") as f:
        for linha in f:
            if not linha.strip():
                continue
            o = json.loads(linha)
            if not isinstance(o, dict):
                raise ValueError("Linha inválida no rastreio")
            if str(o.get("event_id_modelo") or "") != event:
                continue
            if str(o.get("mercado_modelo") or "") != market:
                continue
            inicio = _numero(o.get("timestamp_jogo"))
            if ts is None or inicio is None or abs(ts - inicio) > 60:
                continue
            total += 1
            recentes.append(o)
            recentes = recentes[-MAX_RESTANTES:]
    return total, recentes, "ok"


def relatorio_prova_preco_v13(registo, rastreio, argumento):
    arg = str(argumento or "").strip()
    if not arg.isascii() or not arg.isdecimal() or not 1 <= len(arg) <= 6:
        return "🔎 Uso: /v13_prova_preco 399 — só OWNER (snapshot fixo V1.3)."
    indice = int(arg)
    metricas = registo.metricas_v13_comercial()
    coorte = metricas.get("coorte")
    originais = registo.dados.get("previsoes") if isinstance(registo.dados, dict) else None
    if not isinstance(coorte, list) or not isinstance(originais, list):
        raise ValueError("Coorte V1.3 inválida")
    item = next((e for e in coorte if isinstance(e, dict)
                 and type(e.get("snapshot")) is int and e["snapshot"] == indice), None)
    if item is None:
        return f"⚪ Snapshot #{indice} não pertence à coorte fixa V1.3. Zero consultas externas."
    if indice < 1 or indice > len(originais) or not isinstance(originais[indice - 1], dict):
        raise ValueError("Snapshot inexistente ou corrompido")
    p = originais[indice - 1]
    if str(item.get("mercado")) != str(p.get("mercado")):
        raise ValueError("Identidade do mercado divergente na coorte")
    entrada = _numero(item.get("odd_entrada"), odd=True)
    fecho = _numero(item.get("odd_fecho"), odd=True)
    clv = _numero(item.get("clv"))
    recalculado = entrada / fecho - 1 if entrada is not None and fecho is not None else None
    if recalculado is not None and (clv is None or abs(recalculado-clv) > 1e-8):
        raise ValueError("CLV da coorte não reconcilia com os preços oficiais")
    linhas = [
        f"🔬 PROVA DA ODD / CLV — V1.3 SHADOW #{indice}",
        f"⚽ {_texto(p.get('casa'))} vs {_texto(p.get('fora'))} | {_texto(p.get('data_jogo'))}",
        f"🏆 {_texto(p.get('liga'))}",
        f"🎯 {_texto(p.get('mercado'))} | ID modelo {_texto(p.get('event_id'))}",
        f"📅 Início modelo: {_hora(p.get('timestamp_jogo'))}",
        "",
        "💼 CAMPOS OFICIAIS DA COORTE (não recalculados)",
        f"• Entrada coorte: @{_preco(entrada)}"
        f" | Odd inicial snapshot: @{_preco(p.get('odd_real'))}",
        f"• Odd confirmada: @{_preco(p.get('odd_valor_confirmado'))}"
        f" | Em: {_hora(p.get('valor_confirmado_em'))}",
        f"• Fecho CLV: @{_preco(fecho)}"
        f" | Capturado: {_hora(p.get('odd_fecho_capturada_em'))}",
        f"• CLV oficial: {f'{clv*100:+.2f}%'.replace('.', ',') if clv is not None else 'sem fecho'}"
        " (entrada/fecho − 1)",
        f"• Última odd de mercado no snapshot: @{_preco(p.get('odd_mercado_atual'))}"
        f" | Em: {_hora(p.get('odd_mercado_atual_em'))}",
        f"• Fonte snapshot: {_texto(p.get('odds_fonte'))}"
        f" | Fixture fornecedor: {_texto(p.get('odds_event_id'))}",
        "",
    ]
    total, recentes, estado = _historico(rastreio, p)
    linhas += [f"🔎 RASTREIO LOCAL DO MESMO EVENTO/MERCADO: {total} observações"
              + (f" ({estado})" if estado != "ok" else "")]
    for o in reversed(recentes):
        linhas += [
            f"• {_hora(o.get('observado_em'))} | odd @{_preco(o.get('odd_observada'))}"
            f" | fixture {_texto(o.get('fixture_id_fonte'),45)}",
            f"  mercado {_texto(o.get('mercado_nome_fonte'),40)}"
            f" | linha {_texto(o.get('linha_fonte'),15)}"
            f" | seleção {_texto(o.get('selecao_nome_fonte'),25)}"
            f" | ref {_texto(o.get('outcome_ref_fonte'),30)}",
        ]
    linhas += [
        "",
        "ℹ️ O rastreio comprova observações guardadas, mas NÃO prova que fossem executáveis na Betano.",
        "ℹ️ Uma cotação posterior à janela de fecho oficial não substitui o campo odd_fecho.",
        "🔒 Zero HTTP / zero escrita: coorte, CLV, ROI, V1.2 e V1.3 intactos.",
    ]
    return "\n".join(linhas)
