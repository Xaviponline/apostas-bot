"""Diagnóstico manual de nomes OddsPapi — só catálogo, nunca odds ou associação.

Reutiliza normalização atual apenas para APRESENTAR hipóteses, não para
identificar fixtures. OWNER-only é imposto pelo handler do Telegram.
"""
from contextlib import nullcontext
from datetime import datetime
from zoneinfo import ZoneInfo

from odds_auditoria import AuditoriaOdds

TZ = ZoneInfo("Europe/Lisbon")
MAX_CANDIDATOS = 8


def _num_id(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = int(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if 0 < n < 2_147_483_647 else None


def _nome_curto(valor):
    """Só texto legível curto, nunca comandos/links ou payload integral."""
    nome = " ".join(str(valor or "").split())
    nome = "".join(c for c in nome if c.isprintable())
    return nome[:72]


def diagnosticar_nomes(previsoes, odds, argumento, permite_quota, agora=None):
    agora = (agora or datetime.now(TZ)).astimezone(TZ)
    arg = str(argumento or "").strip()
    if not arg.isascii() or not arg.isdecimal() or len(arg) > 3:
        return "Formato: /odds_nomes 3 (ranking V1.2 do dia; OWNER)."
    rank = int(arg)
    if rank < 1:
        return "Formato: /odds_nomes 3 (ranking V1.2 do dia; OWNER)."
    jogos = [
        p for p in previsoes or []
        if isinstance(p, dict)
        and p.get("data_jogo") == agora.date().isoformat()
        and p.get("modelo_versao") == "V1.2"
        and p.get("ranking_modelo") == rank
    ]
    if len(jogos) != 1:
        return "⚪ Ranking inexistente ou repetido no dia. Zero OddsPapi."
    if getattr(odds, "provider", None) != "oddspapi" or not getattr(odds, "configurada", False):
        return "⚪ OddsPapi indisponível. Zero consultas externas."
    if not callable(permite_quota) or not permite_quota("ODDS_AUTO", 25):
        return "⛔ Pesquisa de nomes suspensa pelo orçamento diário/reserva CLV. Zero consultas externas."

    # Não depende do jogo estar por começar. Nunca pede odds nem faz
    # recuperações retroativas — só lê catálogo de nomes.
    contexto = getattr(odds, "contexto_operacao", None)
    with (contexto("MANUAL") if callable(contexto) else nullcontext()):
        dados = odds._get_papi("/participants", {"sportId": 10, "language": "en"})
    if not isinstance(dados, dict) or len(dados) > 300000:
        return "⚠️ Catálogo OddsPapi inválido. Zero associações, odds ou snapshots alterados."

    jogo = jogos[0]
    linhas = [
        f"🔬 NOMES DA ODDS PAPI — SHADOW | #{rank}",
        f"⚽ {_nome_curto(jogo.get('casa'))} vs {_nome_curto(jogo.get('fora'))}",
        "📚 Fonte: catálogo /participants, apenas nomes e IDs.",
    ]
    for lado, alvo in (("CASA", jogo.get("casa")), ("FORA", jogo.get("fora"))):
        exatos, parciais = [], []
        canon = AuditoriaOdds._canon_equipa(alvo)
        for bruto, nome in dados.items():
            ident = _num_id(bruto)
            if ident is None or not isinstance(nome, str) or not _nome_curto(nome):
                continue
            if AuditoriaOdds._canon_equipa(nome) == canon:
                exatos.append((ident, _nome_curto(nome)))
            elif AuditoriaOdds._nome_equipa_compativel(alvo, nome):
                parciais.append((ident, _nome_curto(nome)))
        # Ordenação estável; apresentação não decide qual equipa usar.
        exatos.sort(key=lambda p: (p[1].casefold(), p[0]))
        parciais.sort(key=lambda p: (p[1].casefold(), p[0]))
        linhas.extend([
            "",
            f"🏷️ {lado}: {_nome_curto(alvo)}",
            f"• Exatos: {len(exatos)} | Parcialmente compatíveis: {len(parciais)}",
        ])
        for categoria, entradas in (("EXATO", exatos), ("PARCIAL", parciais)):
            for ident, nome in entradas[:MAX_CANDIDATOS]:
                linhas.append(f"• [{categoria}] {nome} — ID {ident}")
            if len(entradas) > MAX_CANDIDATOS:
                linhas.append(f"… mais {len(entradas) - MAX_CANDIDATOS} nomes {categoria.lower()} não apresentados.")
    linhas.extend([
        "",
        "⚠️ Nomes semelhantes podem ser equipas diferentes (B, Sub-20, femininas, etc.).",
        "⚠️ Estes IDs são candidatos de catálogo, não fixtures nem preços Betano.",
        "🔒 1 consulta /participants. Sem /fixtures, /odds, VALUE ou alterações à V1.2/SEL1/V1.3.",
    ])
    return "\n".join(linhas)
