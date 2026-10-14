"""Diagnóstico somente leitura da forma ESPN por equipa (sem picks).

Pede, para uma equipa por prova, as rotas all vs liga e filtros opcionais;
imprime APENAS HTTP, nº de eventos e nº de finalizados/normalizáveis.
"""
import requests
from main_enriquecido import BuscadorJogosEnriquecido
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


def main():
    buscador = BuscadorJogosEnriquecido(enabled=True)
    stats = EstatisticasHibridasCompeticoes()
    sessao = requests.Session()
    for liga in ("uefa.champions", "por.taca.portugal"):
        eventos = buscador._get_espn(liga, "20261014")
        jogos = [buscador._normalizar_evento_com_codigo(e, liga) for e in eventos]
        jogos = [j for j in jogos if isinstance(j, dict)]
        if not jogos:
            print(f"FORMA_PROBE {liga}: sem jogos normalizados")
            continue
        team_id = jogos[0]["casa_id"]
        for rota in ("all", liga):
            for rotulo, params in (
                ("sem_filtro", None),
                ("season2026", {"season": "2026"}),
                ("dates2026", {"dates": "2026"}),
                ("dates202610", {"dates": "202610"}),
                ("season2025", {"season": "2025"}),
                ("season2024", {"season": "2024"}),
                ("limit500", {"limit": "500"}),
                ("season2025limit500", {"season": "2025", "limit": "500"}),
            ):
                try:
                    url = f"{stats.BASE}/{rota}/teams/{team_id}/schedule"
                    r = sessao.get(url, params=params, timeout=(5, 12))
                    dados = r.json() if r.status_code == 200 else {}
                    resultado = dados.get("events") if isinstance(dados, dict) else None
                    total = len(resultado) if isinstance(resultado, list) else -1
                    concluidos = sum(
                        bool(((e.get("status") or {}).get("type") or {}).get("completed"))
                        for e in (resultado or []) if isinstance(e, dict)
                    )
                    validos = sum(
                        stats._normalizar_resultado(e, rota) is not None
                        for e in (resultado or []) if isinstance(e, dict)
                    )
                    print(
                        f"FORMA_PROBE {liga} rota={rota} param={rotulo}: "
                        f"HTTP={r.status_code} eventos={total} "
                        f"concluidos={concluidos} normalizados={validos}"
                    )
                except (requests.RequestException, ValueError, TypeError):
                    print(f"FORMA_PROBE {liga} rota={rota} param={rotulo}: indisponível")


if __name__ == "__main__":
    main()
