"""Diagnóstico manual de nomes OddsPapi — só catálogo, nunca odds ou associação.

Reutiliza normalização atual apenas para APRESENTAR hipóteses, não para
identificar fixtures. OWNER-only é imposto pelo handler do Telegram.
"""
from contextlib import nullcontext
import re
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


def _escalao_ou_variante(nome):
    """Sinalizador visual; não decide a identidade de uma equipa."""
    return bool(re.search(
        r"(?<![a-z0-9])(?:u[- ]?\d{2}|sub[- ]?\d{2}|under[- ]?\d{2}|women|feminina|feminino)(?![a-z0-9])",
        _nome_curto(nome), re.IGNORECASE,
    ))


def diagnosticar_nomes(previsoes, odds, argumento, permite_quota, agora=None):
    agora = (agora or datetime.now(TZ)).astimezone(TZ)
    arg = str(argumento or "").strip()
    partes = arg.split()
    formato = "Formato: /odds_nomes 3 ou /odds_nomes 2026-10-16 3 (OWNER)."
    if not arg.isascii() or len(partes) not in (1, 2):
        return formato
    dia = agora.date().isoformat()
    if len(partes) == 2:
        try:
            dia = datetime.strptime(partes[0], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return formato
        if dia != partes[0]:
            return formato
    ranking_txt = partes[-1]
    if not ranking_txt.isdecimal() or len(ranking_txt) > 3 or int(ranking_txt) < 1:
        return formato
    rank = int(ranking_txt)
    jogos = [
        p for p in previsoes or []
        if isinstance(p, dict)
        and p.get("data_jogo") == dia
        and p.get("modelo_versao") == "V1.2"
        and p.get("ranking_modelo") == rank
    ]
    if len(jogos) != 1:
        return ("⚪ Ranking inexistente ou repetido em " + dia
                + ". Usa /odds_nomes AAAA-MM-DD 3 para jogos anteriores. Zero OddsPapi.")
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
        f"🔬 NOMES DA ODDS PAPI — SHADOW | {dia} | #{rank}",
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

        # Avisos estritamente visuais sobre os nomes já mostrados.
        # Nenhum ID é escolhido, persistido ou enviado a /fixtures.
        if not exatos:
            linhas.append("⚠️ Nenhum nome canónico exato: identidade não confirmada.")
        apresentados = exatos[:MAX_CANDIDATOS] + parciais[:MAX_CANDIDATOS]
        por_nome = {}
        for ident, nome in apresentados:
            por_nome.setdefault(nome.casefold(), []).append(ident)
        avisos_repetidos = 0
        for ids_nome in por_nome.values():
            if len(ids_nome) > 1:
                nome = next(nome for ident, nome in apresentados if ident == ids_nome[0])
                linhas.append(
                    f"⚠️ Nome repetido com IDs distintos: {nome} — "
                    + ", ".join(str(ident) for ident in ids_nome)
                )
                avisos_repetidos += 1
                if avisos_repetidos >= 3:
                    break
        if any(_escalao_ou_variante(nome) for ident, nome in apresentados):
            linhas.append("⚠️ Há candidato(s) Sub-20/U20 ou feminino(s): não assumir equipa sénior.")
    linhas.extend([
        "",
        "⚠️ Nomes semelhantes podem ser equipas diferentes (B, Sub-20, femininas, etc.).",
        "⚠️ Estes IDs são candidatos de catálogo, não fixtures nem preços Betano.",
        "🔒 1 consulta /participants. Sem /fixtures, /odds, VALUE ou alterações à V1.2/SEL1/V1.3.",
    ])
    return "\n".join(linhas)
