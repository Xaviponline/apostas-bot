"""Smoke test READ-ONLY das rotas reais SofaScore para os históricos de 14/10/2026.

Executar APENAS num runner isolado, nunca no Railway de produção.
Não acede ao Telegram, odds, modelos, backups ou snapshots.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
CODIGOS = ("uefa.champions", "por.taca.portugal")


def main():
    stats = EstatisticasHibridasCompeticoes()
    falhas = 0
    for codigo in CODIGOS:
        try:
            historico = stats._fetch_liga(codigo, REF)
            diag = stats.diagnostico_base.get(codigo, {})
            total = len(historico)
            fonte = diag.get("fonte", "desconhecida")
            if fonte != "sofascore" or total < stats.MIN_JOGOS_BASE:
                raise ValueError("fonte ou amostra insuficiente")
            if any(
                item.get("liga_codigo") != codigo or
                item.get("timestamp", float("inf")) >= REF.timestamp()
                for item in historico
            ):
                raise ValueError("dados fora da competição ou do corte temporal")
            print(
                f"OK {codigo}: fonte={fonte}; jogos={total}; "
                f"torneio_id={diag.get('torneio_id')}; "
                f"temporada_id={diag.get('temporada_id')}"
            )
        except Exception:
            # Logs deliberadamente sem payload, URL, tokens ou traceback.
            diag = stats.diagnostico_base.get(codigo, {})
            print(
                f"FALHA {codigo}: fonte={diag.get('fonte', 'indisponivel')}; "
                "histórico não validado; não promover a produção"
            )
            falhas += 1
    if falhas:
        raise SystemExit(1)
    print("SMOKE READ-ONLY: duas provas com histórico real válido; "
          "isto NÃO prova que jogos específicos serão analisados.")


if __name__ == "__main__":
    main()
