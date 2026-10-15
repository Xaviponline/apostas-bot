"""Sondagem read-only do histórico Europa + Conferência de 15/10/2026.

Roda apenas em GitHub Actions (isolado), sem Telegram, odds, modelo comercial,
snapshots ou Railway. Não regista previsões; não altera nenhuma fonte.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_forma_web import EstatisticasFormaWeb
from main_enriquecido import BuscadorJogosEnriquecido

CODIGOS = ("uefa.europa", "uefa.europa.conf")
DATA = "20261015"
REF = datetime(2026, 10, 15, 10, tzinfo=ZoneInfo("Europe/Lisbon"))


def main():
    agenda = BuscadorJogosEnriquecido(enabled=True)
    jogos = []
    for codigo in CODIGOS:
        eventos = agenda._get_espn(codigo, DATA)
        validados = [
            agenda._normalizar_evento_com_codigo(evento, codigo)
            for evento in eventos
        ]
        futuros = [
            j for j in validados
            if isinstance(j, dict) and j.get("timestamp", 0) > REF.timestamp()
        ]
        print(f"AGENDA_SHADOW {codigo}: futuros={len(futuros)}")
        if not futuros:
            print(f"FALHA {codigo}: sem fixtures futuros validados")
            raise SystemExit(1)
        jogos.extend(futuros)

    stats = EstatisticasFormaWeb()
    bases = stats.carregar_historicos(jogos, data_ref=REF)
    falhas = 0
    for codigo in CODIGOS:
        base = bases.get(codigo) or []
        diagnostico = stats.diagnostico_base.get(codigo) or {}
        competicao = [j for j in jogos if stats.resolver_liga(j) == codigo]
        analisados = 0
        if diagnostico.get("fonte") != "espn_anual" or len(base) < stats.MIN_JOGOS_BASE:
            falhas += 1
        elif any(
            jogo.get("liga_codigo") != codigo or
            jogo.get("timestamp", float("inf")) >= REF.timestamp()
            for jogo in base
        ):
            falhas += 1
        for jogo in competicao:
            if base and stats.analisar_jogo(jogo, base) is not None:
                analisados += 1
        print(
            f"BASE_PRODUCAO_SHADOW {codigo}: fonte={diagnostico.get('fonte','indisponivel')}; "
            f"historico={len(base)}; jogos={len(competicao)}; "
            f"com_dados={analisados}; forma_erros={len(stats.ultimo_erros_forma)}; "
            f"historico_erro={stats.ultimo_erros.get(codigo, '-')}"
        )
        if not analisados:
            falhas += 1
    if falhas:
        print("SHADOW FALHOU: não promover para produção; sem previsões inventadas")
        raise SystemExit(1)
    print("SHADOW PRODUCAO OK: mesma classe do Railway, histórico e forma com dados reais; sem VALUE nem picks")


if __name__ == "__main__":
    main()
