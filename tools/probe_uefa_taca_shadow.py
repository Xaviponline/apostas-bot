"""Sonda SHADOW so de leitura para base historica Champions e Taca.

Uso: python tools/probe_uefa_taca_shadow.py
Nao cria previsoes, nao consulta OddsPapi, nao grava qualquer ficheiro.
Executar apenas no CI de PR de testes; nunca no arranque de producao.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import re
import requests

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_forma_web import EstatisticasFormaWeb
from analisador_inteligente import AnalisadorInteligente


def sondar_espn():
    """Verifica apenas as rotas diarias: sem snapshots nem pedidos por intervalo."""
    saida = []
    for codigo in ("uefa.champions", "por.taca.portugal"):
        registo = {"competicao": codigo, "fonte": "ESPN"}
        try:
            r = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{codigo}/scoreboard",
                params={"dates": "20261014"},
                timeout=(4, 9),
            )
            registo["http_status"] = int(r.status_code)
            if r.status_code == 200:
                eventos = r.json().get("events", [])
                registo["jogos_agendados"] = len(eventos) if isinstance(eventos, list) else 0
                # Testar uma rota de equipa como possivel via historica, em read-only.
                team_id = None
                for e in eventos[:5] if isinstance(eventos, list) else []:
                    for c in (e.get("competitions") or [{}])[0].get("competitors", []):
                        try:
                            team_id = int((c.get("team") or {}).get("id"))
                        except (ValueError, TypeError):
                            continue
                        if team_id:
                            break
                    if team_id:
                        break
                if team_id:
                    rr = requests.get(
                        f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/teams/{team_id}/schedule",
                        params={"season": 2026},
                        timeout=(4, 9),
                    )
                    registo["equipa_schedule_http"] = int(rr.status_code)
                    if rr.status_code == 200:
                        ee = rr.json().get("events", [])
                        registo["calendario_equipa_eventos"] = len(ee) if isinstance(ee, list) else 0
                        estat = EstatisticasFormaWeb()
                        registo["base_mesma_prova"] = sum(
                            1 for x in ee
                            if estat._codigo_competicao_evento(x) == codigo
                            and estat._normalizar_resultado_forma(x) is not None
                        ) if isinstance(ee, list) else 0
        except (requests.RequestException, ValueError, TypeError, KeyError):
            registo["erro_categoria"] = "inacessivel"
        # Comparar formatos da mesma API: sem valor de aposta, so metadados.
        variantes = (
            ("daily_limit500", {"dates": "20261014", "limit": 500}),
            ("range_sem_limit", {"dates": "20261001-20261014"}),
            ("month", {"dates": "202610"}),
            ("year", {"dates": "2026"}),
        )
        registo["formatos"] = {}
        for rotulo, params in variantes:
            try:
                rr = requests.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/soccer/{codigo}/scoreboard",
                    params=params,
                    timeout=(4, 9),
                )
                detalhe = {"http": int(rr.status_code)}
                if rr.status_code == 200:
                    eventos = rr.json().get("events", [])
                    detalhe["eventos"] = len(eventos) if isinstance(eventos, list) else 0
                registo["formatos"][rotulo] = detalhe
            except (requests.RequestException, ValueError, TypeError):
                registo["formatos"][rotulo] = {"erro": "ligacao_ou_formato"}
        saida.append(registo)
    print("SHADOW_ESPN_ALTERNATIVA=" + json.dumps(saida, ensure_ascii=False, sort_keys=True))


def comparar_analise_em_memoria():
    """Executa analise somente em objetos efemeros: NAO chama .registar()."""
    data_ref = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    codigos = ("uefa.champions", "por.taca.portugal")
    jogos = []
    diagnostico = {}
    for codigo in codigos:
        try:
            resposta = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{codigo}/scoreboard",
                params={"dates": "20261014"}, timeout=(4, 9),
            )
            resposta.raise_for_status()
            eventos = resposta.json().get("events") or []
            for evento in eventos:
                jogo = BuscadorJogosReais._normalizar_evento_espn(evento)
                if jogo is None:
                    continue
                jogo["league_code"] = codigo  # origem: endpoint especifico ESPN
                if jogo.get("timestamp") and jogo["timestamp"] > data_ref.timestamp():
                    jogos.append(jogo)
        except (requests.RequestException, ValueError, TypeError, KeyError):
            diagnostico[codigo] = {"erro": "consulta_fixture"}
    estatisticas = EstatisticasFormaWeb(sofa_client=BuscadorJogosReais(enabled=True))
    historicos = estatisticas.carregar_historicos(jogos, data_ref=data_ref)
    analisador = AnalisadorInteligente(estatisticas=estatisticas)
    for codigo in codigos:
        alvo = [j for j in jogos if j.get("league_code") == codigo]
        com_dados = 0
        selecoes = 0
        for jogo in alvo:
            analise = estatisticas.analisar_jogo(jogo, historicos.get(codigo) or [])
            if analise is not None:
                com_dados += 1
                if analisador._melhor_selecao(analise) is not None:
                    selecoes += 1
        diagnostico[codigo] = {
            "jogos_futuros": len(alvo),
            "base_historica": len(historicos.get(codigo) or []),
            "analisaveis": com_dados,
            "passam_filtros_v12": selecoes,
            "modo": "apenas_em_memoria",
        }
    print("SHADOW_COBERTURA_COMPARADA=" + json.dumps(diagnostico, ensure_ascii=False, sort_keys=True))


def executar():
    data_ref = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    stats = EstatisticasFormaWeb(sofa_client=BuscadorJogosReais(enabled=True))
    resultados = []
    tudo_ok = True
    for codigo in ("uefa.champions", "por.taca.portugal"):
        registo = {"competicao": codigo, "minimo_requerido": stats.MIN_JOGOS_BASE}
        try:
            base = stats._fetch_liga(codigo, data_ref=data_ref)
            diagnostico = stats.diagnostico_base.get(codigo) or {}
            registo["fonte"] = diagnostico.get("fonte", "desconhecida")
            registo["jogos_finalizados"] = len(base)
            registo["valido"] = (
                len(base) >= stats.MIN_JOGOS_BASE
                and all(float(p["timestamp"]) < data_ref.timestamp() for p in base)
                and all(str(p["liga_codigo"]) == codigo for p in base)
            )
        except Exception as exc:
            # Nao incluir texto do erro: pode conter URLs ou payloads.
            registo["valido"] = False
            registo["erro_tipo"] = type(exc).__name__
            registo["fonte"] = (stats.diagnostico_base.get(codigo) or {}).get("fonte")
            motivo = str((stats.diagnostico_base.get(codigo) or {}).get("motivo") or "")
            # Categorias estritas: nenhum URL, resposta bruta ou identificador privado.
            registo["http_status"] = re.findall(r"(?:API|WWW) HTTP [0-9]{3}", motivo)
            if "base insuficiente" in motivo:
                registo["motivo_categoria"] = "amostra_insuficiente"
            elif "ambígua" in motivo:
                registo["motivo_categoria"] = "epoca_ambigua"
            elif "não encontrada" in motivo:
                registo["motivo_categoria"] = "epoca_nao_encontrada"
            elif "HTTP" in motivo:
                registo["motivo_categoria"] = "http_indisponivel"
            else:
                registo["motivo_categoria"] = "desconhecido"
        resultados.append(registo)
        tudo_ok &= registo["valido"]
    print("SHADOW_FONTE_HISTORICA=" + json.dumps(resultados, ensure_ascii=False, sort_keys=True))
    sondar_espn()
    comparar_analise_em_memoria()
    return 0 if tudo_ok else 1


if __name__ == "__main__":
    raise SystemExit(executar())
