"""Replay isolado da cobertura + filtros V1.2 de 14/10/2026.

READ-ONLY. Usa os critérios originais de _melhor_selecao, sem consultar odds,
registar previsões, gerar picks comerciais ou alterar snapshots.
Top5 local é apenas o ranking das provas auditadas (UCL/Taça), NÃO o Top5
global do dia nem uma entrada VALUE confirmada.
"""
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from analisador_inteligente import AnalisadorInteligente
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from main_enriquecido import BuscadorJogosEnriquecido


DATA = "20261014"
REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
CODIGOS = ("uefa.champions", "por.taca.portugal")


def avaliar_filtros_shadow(analises, analisador=None):
    """Reproduz _melhor_selecao sem registos, odds ou alterações de critérios.

    As posições locais só servem para comparar as provas fornecidas. Não
    atribui ranking_modelo, não calcula VALUE e não promove seleções.
    """
    motor = analisador or AnalisadorInteligente()
    elegiveis = []
    sem_qualidade = Counter()
    sem_mercado = Counter()
    por_liga = Counter()
    total_dados = Counter()

    for codigo, analise in analises:
        total_dados[codigo] += 1
        if int(analise["qualidade"]) < motor.QUALIDADE_MINIMA:
            sem_qualidade[codigo] += 1
            continue
        melhor = motor._melhor_selecao(analise)
        if melhor is None:
            sem_mercado[codigo] += 1
            continue
        elegiveis.append((codigo, melhor))
        por_liga[codigo] += 1

    # A mesma ordenação usada em /cobertura, mas SEM universo completo do dia.
    elegiveis.sort(
        key=lambda item: (item[1]["score"], item[1]["qualidade"]),
        reverse=True,
    )
    top5 = Counter(codigo for codigo, _ in elegiveis[:5])
    limite = int(getattr(motor, "MAX_SELECOES", 20) or 20)
    selecionaveis = Counter(codigo for codigo, _ in elegiveis[:limite])
    mercados = Counter(sel["mercado"] for _, sel in elegiveis[:limite])
    return {
        "analisados": total_dados,
        "sem_qualidade": sem_qualidade,
        "sem_mercado": sem_mercado,
        "elegiveis": por_liga,
        "top5_local": top5,
        "dentro_limite_local": selecionaveis,
        "mercados": mercados,
        "total_elegiveis": len(elegiveis),
        "total_dentro_limite": sum(selecionaveis.values()),
        "value_confirmado": False,  # sem odds de mercado, nunca confirmar VALUE
        "ranking_global_confirmado": False,
    }


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
    analises = []
    for codigo in CODIGOS:
        encontrados, futuros = por_codigo[codigo]
        partidas = historicos.get(codigo) or []
        candidatos = [j for j in jogos if stats.resolver_liga(j) == codigo]
        analisadas = []
        for jogo in candidatos:
            analise = stats.analisar_jogo(jogo, partidas)
            if analise is not None:
                analisadas.append(analise)
                analises.append((codigo, analise))

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
            f"analisados={len(analisadas)}; fonte={diag.get('fonte', 'indisponivel')}; "
            f"erros_forma={len(stats.ultimo_erros_forma)}; "
            f"forma_casa={formas_casa}; forma_fora={formas_fora}"
        )

    resumo = avaliar_filtros_shadow(analises)
    for codigo in CODIGOS:
        print(
            f"FILTROS_SHADOW {codigo}: dados={resumo['analisados'][codigo]}; "
            f"qualidade_rejeitada={resumo['sem_qualidade'][codigo]}; "
            f"mercados_rejeitados={resumo['sem_mercado'][codigo]}; "
            f"candidatos={resumo['elegiveis'][codigo]}; "
            f"top5_apenas_duas_provas={resumo['top5_local'][codigo]}; "
            f"limite_local={resumo['dentro_limite_local'][codigo]}"
        )
    print(
        "FILTROS_SHADOW totais: candidatos="
        f"{resumo['total_elegiveis']}; dentro_limite_local="
        f"{resumo['total_dentro_limite']}; "
        f"mercados_agregados={dict(sorted(resumo['mercados'].items()))}"
    )
    print(
        "GATE_SHADOW: ranking_global=NAO_VERIFICADO (restantes ligas ausentes); "
        "VALUE=NAO_VERIFICADO (sem odds reais); sem picks, sem snapshots, "
        "sem escrita, sem alteração de V1.2/SEL1/V1.3."
    )


if __name__ == "__main__":
    main()
