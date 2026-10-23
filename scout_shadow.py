"""SCOUT prospetivo de previsoes V1.2/Top5 com odds multi-casa, isolado.

- Fonte somente de snapshots congelados, NUNCA altera V1.2, V1.3 ou CLV.
- Agenda posterior ao /analisa; no maximo 2 ligas/dia e 120 creditos/mes.
- Primeiro cria marcador diario fail-closed antes de gastar credito.
- Carteira nova em /data/scout_shadow.json, nao e carteira VALUE oficial.
- Nao anuncia VALOR confirmado nem aposta real a odd mediana.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import math
import os
import statistics
import tempfile

import requests
from odds_alternativa_shadow import _get, _seguro
from odds_referencia_shadow import (
    _dt, _equipa, _mercado_modelo, _numero, _recolher, AJUSTE_KICKOFF_SEG
)
from odds_auditoria import AuditoriaOdds


TZ_PT = ZoneInfo("Europe/Lisbon")
MAX_LIGAS_DIA = 2
LIMITE_LOCAL_MES = 120  # creditos The Odds API; independente de OddsPapi
RESERVA_FORNECEDOR = 100
MIN_CASAS = 3
MIN_PROB = 0.62
MIN_QUALIDADE = 70
MIN_ODD = 1.50
MIN_EV = 0.05
MAX_DIVERGENCIA_PRECOS = 1.65
MIN_LIQUIDADAS = 50
MIN_DIAS = 20

# Correspondencias explicitas, sem decidir pela semelhança de textos.
LIGAS = {
    "portuguese primeira liga": "soccer_portugal_primeira_liga",
    "primeira liga": "soccer_portugal_primeira_liga",
    "liga portugal": "soccer_portugal_primeira_liga",
    "english premier league": "soccer_epl",
    "premier league": "soccer_epl",
    "spanish laliga": "soccer_spain_la_liga",
    "laliga": "soccer_spain_la_liga",
    "italian serie a": "soccer_italy_serie_a",
    "serie a": "soccer_italy_serie_a",
    "german bundesliga": "soccer_germany_bundesliga",
    "bundesliga": "soccer_germany_bundesliga",
    "french ligue 1": "soccer_france_ligue_one",
    "ligue 1": "soccer_france_ligue_one",
    "english league championship": "soccer_efl_champ",
    "efl championship": "soccer_efl_champ",
    "uefa champions league": "soccer_uefa_champs_league",
    "uefa europa league": "soccer_uefa_europa_league",
}


def _val_ts(valor):
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def _liga(snapshot):
    nome = AuditoriaOdds._normalizar(snapshot.get("liga"))
    return LIGAS.get(nome)


def _ident(p):
    """Identidade ligada ao snapshot original; nao altera o registo."""
    chave = str(p.get("chave") or "").strip()
    if chave:
        return chave[:200]
    return "|".join(map(str, (
        p.get("event_id", ""), p.get("mercado", ""), p.get("timestamp_jogo", ""),
    )))[:200]


def _possiveis(snapshots, agora):
    hoje = agora.astimezone(TZ_PT).date().isoformat()
    candidates = []
    reasons = Counter()
    for p in snapshots:
        if not isinstance(p, dict):
            continue
        if p.get("data_jogo") != hoje:
            continue
        if p.get("estado") != "pendente":
            reasons["nao_pendente"] += 1
            continue
        ts = _val_ts(p.get("timestamp_jogo"))
        if ts is None or ts <= agora.timestamp():
            reasons["passado_ou_sem_hora"] += 1
            continue
        try:
            ranking = int(p.get("ranking_modelo"))
            qualidade = int(p.get("qualidade"))
        except (TypeError, ValueError, OverflowError):
            reasons["ranking_qualidade_indisponivel"] += 1
            continue
        if ranking < 1 or ranking > 5:
            reasons["fora_top5"] += 1
            continue
        if _mercado_modelo(p) is None:
            reasons["mercado_nao_coberto"] += 1
            continue
        prob = _numero(p.get("probabilidade"), minimo=0, maximo=1.000001)
        minima = _numero(p.get("odd_minima"))
        if prob is None or prob > 1 or minima is None:
            reasons["parametros_modelo_invalidos"] += 1
            continue
        if prob < MIN_PROB or qualidade < MIN_QUALIDADE:
            reasons["filtro_exigente"] += 1
            continue
        sport = _liga(p)
        if not sport:
            reasons["liga_sem_mapeamento"] += 1
            continue
        if not _ident(p):
            reasons["identificacao_invalida"] += 1
            continue
        candidates.append((sport, ranking, -prob, p))
    candidates.sort(key=lambda item: (item[1], item[2], item[0], _ident(item[3])))
    return candidates, reasons


def _match(eventos, p, agora):
    """Nunca ligar apenas pelo nome da equipa ou apenas pela hora."""
    ts = _val_ts(p.get("timestamp_jogo"))
    if ts is None:
        return None
    matches = []
    for e in eventos:
        if not isinstance(e, dict):
            continue
        start = _dt(e.get("commence_time"))
        if start is None or start <= agora:
            continue
        if abs(start.timestamp() - ts) > AJUSTE_KICKOFF_SEG:
            continue
        if _equipa(e.get("home_team"), p.get("casa")) and _equipa(
            e.get("away_team"), p.get("fora")
        ):
            matches.append(e)
    return matches[0] if len(matches) == 1 else None


def _registo(p, e, sport, agora):
    mercado = _mercado_modelo(p)
    cotacoes, _, _, _ = _recolher(e, agora)
    valores = list(cotacoes.get(mercado, {}).values())
    if len(valores) < MIN_CASAS:
        return None, "casas_insuficientes"
    mediana = statistics.median(valores)
    minimo = min(valores)
    maximo = max(valores)
    if mediana < MIN_ODD or minimo <= 1.0 or maximo / minimo > MAX_DIVERGENCIA_PRECOS:
        return None, "odd_baixa_ou_divergente"
    prob = float(p["probabilidade"])
    minima_modelo = float(p["odd_minima"])
    ev = prob * mediana - 1.0
    if mediana < minima_modelo or ev < MIN_EV:
        return None, "sem_margem_teorica"
    resultado = {
        "chave": _ident(p),
        "snapshot_hash": str(p.get("snapshot_hash") or ""),
        "event_id": str(p.get("event_id") or ""),
        "timestamp_jogo": p.get("timestamp_jogo"),
        "casa": _seguro(p.get("casa"), 60),
        "fora": _seguro(p.get("fora"), 60),
        "liga": _seguro(p.get("liga"), 70),
        "sport": sport,
        "mercado": mercado,
        "ranking": int(p["ranking_modelo"]),
        "qualidade": int(p["qualidade"]),
        "probabilidade": round(prob, 6),
        "odd_minima_modelo": round(minima_modelo, 4),
        "odd_mediana": round(mediana, 4),
        "odd_minima_mercado": round(minimo, 4),
        "odd_maxima_mercado": round(maximo, 4),
        "bookmakers": len(valores),
        "ev_teorico": round(ev, 6),
        "capturado_em": agora.isoformat(),
    }
    return resultado, None


def _ranking_top5(p):
    try:
        return 1 <= int(p.get("ranking_modelo")) <= 5
    except (TypeError, ValueError, OverflowError):
        return False


def _wilson(acertos, total):
    if not total:
        return None
    z = 1.959963984540054
    p = acertos / total
    denom = 1 + z*z/total
    centro = (p + z*z/(2*total)) / denom
    margem = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / denom
    return max(0., centro-margem), min(1., centro+margem)


def _data_vazia():
    return {"versao": 1, "dias": {}}


class ScoutShadow:
    def __init__(self, path=None, session=None):
        self.path = Path(path or (Path(os.getenv("DATA_DIR", "/data")) / "scout_shadow.json"))
        self.session = session  # pode ser injetada para testes; nenhum pedido no construtor

    def _carregar(self):
        if not self.path.exists():
            return _data_vazia()
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Carteira shadow ilegivel: falha fechada.") from exc
        if (not isinstance(dados, dict) or dados.get("versao") != 1
                or not isinstance(dados.get("dias"), dict)):
            raise RuntimeError("Carteira shadow invalida: falha fechada.")
        return dados

    def _guardar(self, dados):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix=".scout_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, self.path)
        finally:
            if os.path.exists(temporario):
                os.unlink(temporario)

    @staticmethod
    def _consumo_mes(dados, mes):
        return sum(
            int(dia.get("creditos_estimados_reservados", 0))
            for data, dia in dados["dias"].items()
            if data.startswith(mes) and isinstance(dia, dict)
        )

    def executar(self, snapshots, agora=None, chave=None):
        """Executa uma unica tentativa por dia, com marcador ANTES de HTTP."""
        agora = agora or datetime.now(timezone.utc)
        if agora.tzinfo is None:
            raise ValueError("Hora sem fuso.")
        agora = agora.astimezone(timezone.utc)
        hoje = agora.astimezone(TZ_PT).date().isoformat()
        dados = self._carregar()
        if hoje in dados["dias"]:
            return False, "♻️ SCOUT de hoje ja registado. Zero chamadas novas.\n" + self.relatorio_dia(dados, hoje)
        candidatos, motivos = _possiveis(snapshots, agora)
        if not candidatos:
            return False, (
                "🎯 SCOUT SHADOW — "
                + hoje + "\n⚪ Sem snapshots Top5 elegiveis para hoje; zero pedidos API.\n"
                + ("Filtros: " + ", ".join(f"{k}={v}" for k,v in motivos.most_common(5))
                   if motivos else "Ainda nao existem snapshots de hoje.")
            )
        key = str(chave or os.getenv("THE_ODDS_API_KEY") or "").strip()
        if not key:
            return False, "⚪ The Odds API indisponivel; sem chamadas e sem alteracoes."
        if self._consumo_mes(dados, hoje[:7]) + MAX_LIGAS_DIA*2 > LIMITE_LOCAL_MES:
            return False, "⛔ Limite local mensal SCOUT atingido. Zero chamadas."
        grupos = {}
        for sport, rank, neg_prob, p in candidatos:
            grupos.setdefault(sport, []).append(p)
        ligas_ordenadas = sorted(
            grupos, key=lambda sport: (
                min(int(p["ranking_modelo"]) for p in grupos[sport]),
                -len(grupos[sport]),
                sport,
            )
        )[:MAX_LIGAS_DIA]
        dia = {
            "estado": "reservado",
            "criado_em": agora.isoformat(),
            "creditos_estimados_reservados": 2 * len(ligas_ordenadas),
            "ligas": ligas_ordenadas,
            "candidatos_modelo": len(candidatos),
            "descartes": dict(motivos),
            "selecoes": [],
        }
        # Escrever antes de qualquer chamada. Reinicio NAO repete gastos.
        dados["dias"][hoje] = dia
        self._guardar(dados)
        sessao = self.session or requests.Session()
        try:
            catalogo, erro, quota_catalogo = _get(sessao, "/sports/", {"apiKey": key})
            if erro:
                dia["estado"] = "erro_catalogo"
                dia["erro"] = erro
                return True, self.relatorio_dia(dados, hoje)
            try:
                restantes_inicio = int(quota_catalogo["x-requests-remaining"])
            except (TypeError, KeyError, ValueError):
                restantes_inicio = None
            if restantes_inicio is None:
                dia["estado"] = "quota_nao_confirmada"
                dia["descartes"]["sem_quota_verificavel"] = len(candidatos)
                return True, self.relatorio_dia(dados, hoje)
            if restantes_inicio < RESERVA_FORNECEDOR + 2:
                dia["estado"] = "reserva_protegida"
                dia["descartes"]["reserva_quota"] = len(candidatos)
                return True, self.relatorio_dia(dados, hoje)
            disponiveis = {
                s.get("key") for s in catalogo if isinstance(s, dict)
                and s.get("active", True) is not False
            }
            restantes = restantes_inicio
            for sport in ligas_ordenadas:
                if sport not in disponiveis:
                    dia["descartes"]["liga_sem_odds_api"] = (
                        dia["descartes"].get("liga_sem_odds_api", 0) + len(grupos[sport])
                    )
                    continue
                if restantes is not None and restantes < RESERVA_FORNECEDOR + 2:
                    dia["descartes"]["reserva_quota"] = (
                        dia["descartes"].get("reserva_quota", 0) + len(grupos[sport])
                    )
                    break
                odds, erro, quota = _get(sessao, f"/sports/{sport}/odds", {
                    "apiKey": key, "regions": "eu", "markets": "h2h,totals",
                    "oddsFormat": "decimal", "dateFormat": "iso",
                })
                if quota:
                    try:
                        restantes = int(quota["x-requests-remaining"])
                    except (TypeError, ValueError):
                        restantes = None
                if erro:
                    dia["descartes"]["fonte_indisponivel"] = (
                        dia["descartes"].get("fonte_indisponivel", 0) + len(grupos[sport])
                    )
                    continue
                for p in grupos[sport]:
                    e = _match(odds, p, agora)
                    if e is None:
                        dia["descartes"]["fixture_nao_unico"] = (
                            dia["descartes"].get("fixture_nao_unico", 0) + 1
                        )
                        continue
                    row, motivo = _registo(p, e, sport, agora)
                    if motivo:
                        dia["descartes"][motivo] = dia["descartes"].get(motivo, 0) + 1
                    elif not any(s["chave"] == row["chave"] for s in dia["selecoes"]):
                        dia["selecoes"].append(row)
                # Persistir apos cada liga; guardar parcial se houver falha posterior.
                self._guardar(dados)
            dia["estado"] = "concluido"
            return True, self.relatorio_dia(dados, hoje)
        finally:
            self._guardar(dados)

    @staticmethod
    def relatorio_dia(dados, dia):
        obj = dados["dias"].get(dia)
        if not obj:
            return f"🎯 SCOUT SHADOW — {dia}\n⚪ Sem carteira guardada."
        selecoes = obj.get("selecoes", [])
        linhas = [
            f"🎯 SCOUT SHADOW — {dia}",
            f"Estado: {obj.get('estado')} | Ligas alvo: {', '.join(obj.get('ligas', []))}",
            f"Modelo Top5 elegivel para pesquisa: {obj.get('candidatos_modelo', 0)}",
            f"📌 Candidatas apos filtros de odds: {len(selecoes)}",
        ]
        for s in selecoes[:8]:
            linhas += [
                f"⚽ {s['casa']} vs {s['fora']} — {s['mercado']}",
                f"   Ranking #{s['ranking']} | Modelo {s['probabilidade']*100:.1f}%"
                f" | Ref. {s['odd_mediana']:.2f} ({s['bookmakers']} casas)"
                f" | Min. modelo {s['odd_minima_modelo']:.2f}",
            ]
        if obj.get("descartes"):
            resumo = sorted(obj["descartes"].items(), key=lambda k: (-k[1], k[0]))
            linhas.append("🔎 Excluidas: " + ", ".join(f"{k}={v}" for k,v in resumo[:8]))
        linhas += [
            f"📊 Teto conservador reservado: {obj.get('creditos_estimados_reservados', 0)} creditos",
            "⚠️ Apenas candidatos a teste; referencia multi-casa nao e odd executavel.",
            "🔒 Sem alterar previsoes, carteira V1.3, CLV ou Premium.",
        ]
        return "\n".join(linhas).replace(".", ",")

    def hoje(self, agora=None):
        agora = agora or datetime.now(TZ_PT)
        hoje = agora.astimezone(TZ_PT).date().isoformat()
        return self.relatorio_dia(self._carregar(), hoje)

    def desempenho(self, snapshots):
        """Resolve apenas resultados ja presentes no registo V1.2; sem consultas."""
        dados = self._carregar()
        index = {_ident(p): p for p in snapshots if isinstance(p, dict)}
        registos = [
            (data, r) for data, obj in sorted(dados["dias"].items())
            if isinstance(obj, dict)
            for r in obj.get("selecoes", []) if isinstance(r, dict)
        ]
        if not registos:
            return "📊 SCOUT SHADOW — PERFORMANCE\nAinda nao ha candidatas prospetivas registadas."
        ganhou = perdeu = pendente = invalidas = 0
        brier = 0.0
        pnl = 0.0
        dias = set()
        for dia, item in registos:
            p = index.get(item.get("chave"))
            if not p:
                invalidas += 1
                continue
            hash_original = item.get("snapshot_hash")
            if hash_original and p.get("snapshot_hash") != hash_original:
                invalidas += 1
                continue
            if str(p.get("mercado") or "") != item.get("mercado"):
                invalidas += 1
                continue
            if _val_ts(p.get("timestamp_jogo")) != _val_ts(item.get("timestamp_jogo")):
                invalidas += 1
                continue
            outcome = p.get("resultado_binario")
            if type(outcome) is int and outcome in (0, 1):
                dias.add(dia)
                ganhou += outcome
                perdeu += 1-outcome
                brier += (item["probabilidade"] - outcome)**2
                pnl += (item["odd_mediana"] - 1.0) if outcome else -1.0
            else:
                pendente += 1
        n = ganhou + perdeu
        # Baseline da MESMA janela de dias do Scout, sem alterar o modelo.
        # Nao e amostra pareada nem prova causal de melhoria.
        dias_com_teste = {
            data for data, obj in dados["dias"].items()
            if isinstance(obj, dict) and obj.get("selecoes")
        }
        base = [
            p for p in snapshots if isinstance(p, dict)
            and p.get("data_jogo") in dias_com_teste
            and type(p.get("resultado_binario")) is int
            and p["resultado_binario"] in (0, 1)
            and _val_ts(p.get("timestamp_jogo")) is not None
            and _numero(p.get("probabilidade"), minimo=0, maximo=1.000001) is not None
            and _ranking_top5(p)
        ]
        b_n = len(base)
        b_w = sum(p["resultado_binario"] for p in base)
        b_brier = (
            sum((float(p["probabilidade"]) - p["resultado_binario"])**2 for p in base)
            / b_n if b_n else None
        )
        segmentos = Counter()
        acertos_segmento = Counter()
        for _, item in registos:
            p = index.get(item.get("chave"))
            if (p and type(p.get("resultado_binario")) is int
                    and p["resultado_binario"] in (0, 1)
                    and (not item.get("snapshot_hash")
                         or item["snapshot_hash"] == p.get("snapshot_hash"))
                    and str(p.get("mercado") or "") == item.get("mercado")
                    and _val_ts(p.get("timestamp_jogo")) == _val_ts(item.get("timestamp_jogo"))):
                segmentos[item["mercado"]] += 1
                acertos_segmento[item["mercado"]] += p["resultado_binario"]
        linhas = [
            "📊 SCOUT SHADOW — PERFORMANCE PROSPETIVA",
            f"📚 Sinais: {len(registos)} | Liquidados: {n} | Pendentes: {pendente}"
            f" | Identidade invalida: {invalidas}",
            f"✅ {ganhou} | ❌ {perdeu} | Dias com resolucao: {len(dias)}/{MIN_DIAS}",
        ]
        if n:
            ci = _wilson(ganhou, n)
            linhas += [
                f"🎯 Acerto: {100*ganhou/n:.1f}% | IC95 Wilson "
                f"{ci[0]*100:.1f}–{ci[1]*100:.1f}%",
                f"📐 Brier: {brier/n:.4f}",
                f"🧮 ROI SIMULADO a mediana: {100*pnl/n:+.1f}% "
                "(nao e ROI apostavel)",
            ]
        if b_n:
            linhas.append(
                f"📏 Baseline V1.2 Top5, nos dias de teste: {b_w}/{b_n} "
                f"({100*b_w/b_n:.1f}% acerto) | Brier {b_brier:.4f}"
            )
            linhas.append("⚠️ Baseline descritivo, nao pareado: nao prova ganho estatistico.")
        if segmentos:
            linhas.append("📊 Por mercado: " + "; ".join(
                f"{m} {acertos_segmento[m]}/{k}"
                for m,k in sorted(segmentos.items())
            ))
        if n < MIN_LIQUIDADAS or len(dias) < MIN_DIAS:
            linhas.append(
                f"⚪ Amostra insuficiente: exigimos {MIN_LIQUIDADAS} sinais liquidados "
                f"e {MIN_DIAS} dias antes de avaliar esta estrategia."
            )
        else:
            linhas.append("🔎 Amostra minima atingida; exige comparacao com baseline e CLV antes de promocao.")
        linhas.append("🔒 Nunca reclassifica o protocolo comercial V1.3 existente.")
        return "\n".join(linhas).replace(".", ",")
