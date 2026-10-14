"""Replay de cobertura histórica (SHADOW), somente leitura e sem picks.

Tenta reconstruir as duas competições de 14/10/2026 com o relógio congelado
às 12:00 Europe/Lisbon. NÃO recria snapshots nem o conjunto exato observado
no Telegram; compara apenas os dados calculáveis a partir da agenda ESPN atual.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from main_enriquecido import BuscadorJogosEnriquecido


DATA = "20261014"
REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
CODIGOS = ("uefa.champions", "por.taca.portugal")


def main():
    agenda = BuscadorJogosEnriquecido(enabled=True)
    jogos = []
    por_codigo = {}
    for codigo in CODIGOS:
        eventos = agenda._get_espn(codigo, DATA)
        normalizados = [
            agenda._normalizar_evento_com_codigo(e, codigo) for e in eventos
        ]
        validos = [e for e in normalizados if isinstance(e, dict)]
        futuros = [e for e in validos if e["timestamp"] > REF.timestamp()]
        por_codigo[codigo] = (len(validos), len(futuros))
        jogos.extend(futuros)

    stats = EstatisticasHibridasCompeticoes()
    historicos = stats.carregar_historicos(jogos, data_ref=REF)
    for codigo in CODIGOS:
        encontrados, futuros = por_codigo[codigo]
        partidas = historicos.get(codigo) or []
        candidatos = [j for j in jogos if stats.resolver_liga(j) == codigo]
        dados = sum(
            stats.analisar_jogo(j, partidas) is not None for j in candidatos
        )
        formas_casa = [
            len(stats._ultimos_time(
                stats._formas_globais.get(j.get("casa_id")) or [],
                j["casa_id"], limite=8
            )) for j in candidatos
        ]
        formas_fora = [
            len(stats._ultimos_time(
                stats._formas_globais.get(j.get("fora_id")) or [],
                j["fora_id"], limite=8
            )) for j in candidatos
        ]
        diag = stats.diagnostico_base.get(codigo) or {}
        print(
            f"REPLAY_SHADOW {codigo}: encontrados={encontrados}; "
            f"futuros_12h={futuros}; base={len(partidas)}; "
            f"analisados={dados}; fonte={diag.get('fonte', 'indisponivel')}; "
            f"erros_forma={len(stats.ultimo_erros_forma)}; "
            f"forma_casa={formas_casa}; forma_fora={formas_fora}"
        )
    print(
        "REPLAY_SHADOW não publica picks, não executa filtros VALUE/Top5 "
        "nem cria/edita snapshots; agenda pode diferir do relatório inicial."
    )


if __name__ == "__main__":
    main()
