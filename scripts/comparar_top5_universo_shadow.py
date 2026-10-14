"""Ranking sombra das quatro competições suportadas no relatório 14/10/2026.

Consulta só endpoints ESPN públicos e históricos em memória. Não calcula VALUE:
sem odds reais não há apostas de valor confirmadas. O resultado é condicionado
à reconstituição exata do universo conhecido (9+1+4+1 jogos).
"""
from collections import Counter

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from main_enriquecido import BuscadorJogosEnriquecido
from scripts.comparar_cobertura_shadow import REF, DATA, avaliar_filtros_shadow


# Extraído do /cobertura observado a 14/10; não é uma projeção da agenda.
ESPERADOS = {
    "uefa.champions": 9,
    "por.taca.portugal": 1,
    "eng.2": 4,
    "arg.1": 1,
}


def main():
    agenda = BuscadorJogosEnriquecido(enabled=True)
    jogos = []
    validacao = {}
    falhas = []
    for codigo, esperado in ESPERADOS.items():
        try:
            eventos = agenda._get_espn(codigo, DATA)
            normalizados = [
                agenda._normalizar_evento_com_codigo(e, codigo)
                for e in eventos
            ]
            futuros = [
                e for e in normalizados
                if isinstance(e, dict) and e.get("timestamp") is not None
                and float(e["timestamp"]) > REF.timestamp()
            ]
            validacao[codigo] = len(futuros)
            jogos.extend(futuros)
        except Exception as exc:
            # A auditoria nunca imprime payloads, IDs privados ou tokens.
            falhas.append(codigo)
            validacao[codigo] = None
        print(
            f"UNIVERSO_SHADOW {codigo}: "
            f"futuros_12h={validacao[codigo]}; esperado_relatorio={esperado}"
        )

    if falhas:
        print(
            "TOP5_UNIVERSO=INCONCLUSIVO: fontes indisponíveis "
            f"({', '.join(sorted(falhas))}); sem ranking/odds/picks."
        )
        return

    stats = EstatisticasHibridasCompeticoes()
    historicos = stats.carregar_historicos(jogos, data_ref=REF)
    analises = []
    com_dados = Counter()
    for jogo in jogos:
        codigo = stats.resolver_liga(jogo)
        if codigo not in ESPERADOS:
            continue
        analise = stats.analisar_jogo(jogo, historicos.get(codigo) or [])
        if analise is not None:
            com_dados[codigo] += 1
            analises.append((codigo, analise))

    resumo = avaliar_filtros_shadow(analises)
    for codigo in ESPERADOS:
        print(
            f"TOP5_SHADOW {codigo}: futuros={validacao[codigo]}; "
            f"analisados={com_dados[codigo]}; "
            f"candidatos={resumo['elegiveis'][codigo]}; "
            f"top5_universo={resumo['top5_local'][codigo]}"
        )

    completos = all(
        validacao[codigo] == esperado
        for codigo, esperado in ESPERADOS.items()
    )
    erro_historico = bool(stats.ultimo_erros or stats.ultimo_erros_forma)
    print(
        "TOP5_UNIVERSO="
        + ("RECONSTITUIDO" if completos and not erro_historico else "PARCIAL")
        + f"; candidatos={resumo['total_elegiveis']}; "
        + f"Top5_distribuicao={dict(sorted(resumo['top5_local'].items()))}; "
        + f"falhas_historico={len(stats.ultimo_erros)}; "
        + f"falhas_forma={len(stats.ultimo_erros_forma)}"
    )
    print(
        "VALUE=NAO_VERIFICADO (sem odds reais); sem registo de previsões, "
        "sem snapshots, sem V1.3 comercial, sem Railway."
    )


if __name__ == "__main__":
    main()
