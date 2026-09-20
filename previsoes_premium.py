"""Registo auditável das previsões do motor premium.

Cada previsão é guardada antes do jogo e os campos do modelo não são alterados
por novas execuções do /analisa. Enquanto uma previsão continuar pendente e o
jogo ainda não tiver começado, uma odd real que faltava pode ser anexada com a
hora exata da captura. Depois do resultado final, a previsão pode ser liquidada
e usada para medir taxa de acerto, Brier Score e, quando aplicável, ROI.
"""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile
import requests


class RegistoPrevisoes:
    VERSAO = 1
    MODELO_VERSAO = "V1.1"
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

    def __init__(self, path=None, session=None):
        if path is None:
            data_dir = Path(os.getenv("DATA_DIR", "/data"))
            path = data_dir / "previsoes_premium.json"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.dados = self._carregar()

    def _carregar(self):
        if not self.path.exists():
            return {"versao": self.VERSAO, "previsoes": []}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Ficheiro de previsões inválido; não foi sobrescrito.") from exc
        if not isinstance(dados, dict) or not isinstance(dados.get("previsoes"), list):
            raise ValueError("Formato do ficheiro de previsões inválido.")
        dados.setdefault("versao", self.VERSAO)
        return dados

    def _guardar(self):
        conteudo = json.dumps(self.dados, ensure_ascii=False, indent=2, sort_keys=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="previsoes_", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(conteudo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _data_jogo(jogo):
        ts = jogo.get("timestamp")
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(
                ZoneInfo("Europe/Lisbon")
            ).strftime("%Y-%m-%d")
        return datetime.now(ZoneInfo("Europe/Lisbon")).strftime("%Y-%m-%d")

    @staticmethod
    def _chave(event_id, mercado):
        return f"{event_id}|{mercado}"

    @staticmethod
    def _odd_real_valida(valor):
        try:
            odd = float(valor)
        except (TypeError, ValueError):
            return None
        return odd if odd > 1.0 else None

    @staticmethod
    def _jogo_ainda_nao_comecou(registo, agora_ts):
        ts = registo.get("timestamp_jogo")
        return isinstance(ts, (int, float)) and float(ts) > float(agora_ts)

    def _anexar_odd_se_segura(self, registo, selecao, agora_iso, agora_ts):
        """Anexa apenas a primeira odd real, sem alterar qualquer campo do modelo."""
        if registo.get("estado") != "pendente":
            return False
        if self._odd_real_valida(registo.get("odd_real")) is not None:
            return False
        if not self._jogo_ainda_nao_comecou(registo, agora_ts):
            return False

        odd_real = self._odd_real_valida(selecao.get("odd_real"))
        if odd_real is None:
            return False
        try:
            prob = float(registo["probabilidade"])
        except (KeyError, TypeError, ValueError):
            return False

        registo.update(
            {
                "odd_real": round(odd_real, 4),
                "ev_real": round((prob * odd_real) - 1.0, 6),
                "odds_fonte": str(selecao.get("odds_fonte") or ""),
                "odds_event_id": str(selecao.get("odds_event_id") or ""),
                "odds_atualizada_em": str(selecao.get("odds_atualizada_em") or ""),
                "odds_capturada_em": agora_iso,
            }
        )
        return True

    def registar(self, selecoes):
        """Guarda previsões novas e completa odds ausentes apenas antes do jogo."""
        existentes = {
            self._chave(p.get("event_id"), p.get("mercado")): p
            for p in self.dados["previsoes"]
        }
        agora_dt = datetime.now(timezone.utc)
        agora_ts = agora_dt.timestamp()
        agora = agora_dt.isoformat().replace("+00:00", "Z")
        adicionadas = 0
        odds_anexadas = 0

        for s in selecoes or []:
            jogo = s.get("jogo") or {}
            event_id = jogo.get("id")
            mercado = s.get("mercado")
            if event_id is None or not mercado:
                continue
            chave = self._chave(event_id, mercado)
            if chave in existentes:
                if self._anexar_odd_se_segura(
                    existentes[chave], s, agora, agora_ts
                ):
                    odds_anexadas += 1
                continue
            try:
                prob = float(s["probabilidade"])
                prob_bruta = float(s.get("probabilidade_bruta", prob))
                qualidade = int(s["qualidade"])
                odd_justa = float(s["odd_justa"])
                odd_minima = float(s["odd_minima"])
            except (KeyError, TypeError, ValueError):
                continue

            try:
                ranking_modelo = int(s.get("ranking_modelo"))
                if ranking_modelo <= 0:
                    ranking_modelo = None
            except (TypeError, ValueError):
                ranking_modelo = None

            registo = {
                "chave": chave,
                "event_id": int(event_id),
                "data_jogo": self._data_jogo(jogo),
                "timestamp_jogo": jogo.get("timestamp"),
                "casa": str(jogo.get("casa") or ""),
                "fora": str(jogo.get("fora") or ""),
                "liga": str(jogo.get("liga") or ""),
                "mercado": str(mercado),
                "modelo_versao": self.MODELO_VERSAO,
                "ranking_modelo": ranking_modelo,
                "probabilidade": round(prob, 6),
                "probabilidade_bruta": round(prob_bruta, 6),
                "qualidade": qualidade,
                "odd_justa": round(odd_justa, 4),
                "odd_minima": round(odd_minima, 4),
                "criada_em": agora,
                "estado": "pendente",
                "resultado_binario": None,
                "golos_casa": None,
                "golos_fora": None,
                "liquidada_em": None,
            }

            odd_real = self._odd_real_valida(s.get("odd_real"))
            if odd_real is not None:
                registo.update(
                    {
                        "odd_real": round(odd_real, 4),
                        "ev_real": round((prob * odd_real) - 1.0, 6),
                        "odds_fonte": str(s.get("odds_fonte") or ""),
                        "odds_event_id": str(s.get("odds_event_id") or ""),
                        "odds_atualizada_em": str(s.get("odds_atualizada_em") or ""),
                        "odds_capturada_em": agora,
                    }
                )

            self.dados["previsoes"].append(registo)
            existentes[chave] = registo
            adicionadas += 1

        if adicionadas or odds_anexadas:
            self._guardar()
        return adicionadas

    @staticmethod
    def _resultado_mercado(mercado, gc, gf):
        if mercado == "Vitória Casa":
            return int(gc > gf)
        if mercado == "Vitória Fora":
            return int(gf > gc)
        if mercado == "Ambas Marcam":
            return int(gc > 0 and gf > 0)
        if mercado == "Over 1.5 Golos":
            return int(gc + gf >= 2)
        if mercado == "Over 2.5 Golos":
            return int(gc + gf >= 3)
        if mercado == "Under 2.5 Golos":
            return int(gc + gf <= 2)
        if mercado == "Under 3.5 Golos":
            return int(gc + gf <= 3)
        if mercado == "1X (Casa ou Empate)":
            return int(gc >= gf)
        if mercado == "X2 (Empate ou Fora)":
            return int(gf >= gc)
        return None

    @staticmethod
    def _score(valor):
        try:
            return int(str(valor).strip())
        except (TypeError, ValueError):
            return None

    def _resultados_espn(self, data_iso, liga_codigo="all"):
        """Obtém resultados finais ESPN por rota global ou competição específica."""
        compacta = str(data_iso).replace("-", "")
        liga_codigo = str(liga_codigo or "all").strip() or "all"
        r = self.session.get(
            f"{self.ESPN_BASE}/{liga_codigo}/scoreboard",
            params={"dates": compacta},
            timeout=(5, 25),
        )
        r.raise_for_status()
        dados = r.json()
        eventos = dados.get("events") if isinstance(dados, dict) else None
        if not isinstance(eventos, list):
            raise ValueError("Resultados ESPN inválidos.")

        saida = {}
        for evento in eventos:
            try:
                status = ((evento.get("status") or {}).get("type") or {})
                if str(status.get("state") or "").lower() != "post" and not status.get("completed"):
                    continue
                competicoes = evento.get("competitions") or []
                if not competicoes:
                    continue
                concorrentes = (competicoes[0] or {}).get("competitors") or []
                casa = next((c for c in concorrentes if c.get("homeAway") == "home"), None)
                fora = next((c for c in concorrentes if c.get("homeAway") == "away"), None)
                if casa is None or fora is None:
                    continue
                gc, gf = self._score(casa.get("score")), self._score(fora.get("score"))
                if gc is None or gf is None:
                    continue
                saida[int(evento["id"])] = (gc, gf)
            except (KeyError, TypeError, ValueError):
                continue
        return saida

    def atualizar_pendentes(self, buscador=None):
        """Liquida previsões pendentes. Falhas de rede não alteram o histórico."""
        pendentes = [p for p in self.dados["previsoes"] if p.get("estado") == "pendente"]
        if not pendentes:
            return 0

        por_data = {}
        for p in pendentes:
            por_data.setdefault(p.get("data_jogo"), []).append(p)

        liquidadas = 0
        agora = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for data_iso, previsoes in por_data.items():
            if not data_iso:
                continue
            try:
                resultados = self._resultados_espn(data_iso)
            except (requests.RequestException, RuntimeError, ValueError, TypeError):
                continue
            for p in previsoes:
                resultado = resultados.get(p.get("event_id"))
                if resultado is None:
                    continue
                gc, gf = resultado
                y = self._resultado_mercado(p.get("mercado"), gc, gf)
                if y is None:
                    continue
                p["estado"] = "ganhou" if y == 1 else "perdeu"
                p["resultado_binario"] = y
                p["golos_casa"] = gc
                p["golos_fora"] = gf
                p["liquidada_em"] = agora
                liquidadas += 1
        if liquidadas:
            self._guardar()
        return liquidadas

    def estatisticas(self):
        todos = self.dados["previsoes"]
        liquidados = [p for p in todos if p.get("resultado_binario") in (0, 1)]
        pendentes = sum(1 for p in todos if p.get("estado") == "pendente")
        ganhos = sum(int(p["resultado_binario"]) for p in liquidados)
        perdas = len(liquidados) - ganhos
        hit_rate = (ganhos / len(liquidados)) if liquidados else None
        if liquidados:
            brier = sum(
                (float(p["probabilidade"]) - int(p["resultado_binario"])) ** 2
                for p in liquidados
            ) / len(liquidados)
        else:
            brier = None

        com_odds = []
        for p in liquidados:
            odd = self._odd_real_valida(p.get("odd_real"))
            if odd is not None:
                com_odds.append((p, odd))
        lucro_unidades = sum(
            (odd - 1.0) if int(p["resultado_binario"]) == 1 else -1.0
            for p, odd in com_odds
        )
        roi = (lucro_unidades / len(com_odds)) if com_odds else None
        ev_medio = (
            sum((float(p["probabilidade"]) * odd) - 1.0 for p, odd in com_odds)
            / len(com_odds)
            if com_odds
            else None
        )
        return {
            "total": len(todos),
            "pendentes": pendentes,
            "liquidadas": len(liquidados),
            "ganhos": ganhos,
            "perdas": perdas,
            "hit_rate": hit_rate,
            "brier": brier,
            "odds_liquidadas": len(com_odds),
            "lucro_unidades": lucro_unidades,
            "roi": roi,
            "ev_medio": ev_medio,
        }

    def relatorio(self):
        s = self.estatisticas()
        linhas = [
            "📊 PERFORMANCE DO MODELO — AUDITORIA",
            "",
            f"Previsões registadas: {s['total']}",
            f"Liquidadas: {s['liquidadas']} | Pendentes: {s['pendentes']}",
        ]

        pendentes_detalhe = [
            p for p in self.dados["previsoes"] if p.get("estado") == "pendente"
        ]
        if pendentes_detalhe:
            linhas.extend(["", "⏳ PREVISÕES PENDENTES"])
            for p in sorted(
                pendentes_detalhe,
                key=lambda item: (
                    str(item.get("data_jogo") or ""),
                    float(item.get("timestamp_jogo") or 0),
                ),
            ):
                ts = p.get("timestamp_jogo")
                hora = "--:--"
                if isinstance(ts, (int, float)):
                    hora = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(
                        ZoneInfo("Europe/Lisbon")
                    ).strftime("%H:%M")
                odd = self._odd_real_valida(p.get("odd_real"))
                sufixo_odd = f" | Odd {odd:.2f}" if odd is not None else ""
                linhas.append(
                    f"• {p.get('data_jogo') or '--'} {hora} — "
                    f"{p.get('casa') or '?'} vs {p.get('fora') or '?'} | "
                    f"{p.get('mercado') or 'Mercado desconhecido'}{sufixo_odd}"
                )

        if not s["liquidadas"]:
            linhas.extend(
                [
                    "",
                    "Ainda não há previsões liquidadas suficientes para avaliar o modelo.",
                    "As previsões ficam guardadas antes do jogo e os campos do modelo não são reescritos pelo /analisa.",
                ]
            )
            return "\n".join(linhas)

        linhas.extend(
            [
                "",
                f"✅ Acertos: {s['ganhos']} | ❌ Falhas: {s['perdas']}",
                f"🎯 Taxa de acerto: {s['hit_rate']*100:.1f}%",
                f"📐 Brier Score: {s['brier']:.4f} (menor é melhor)",
            ]
        )
        if s["odds_liquidadas"]:
            sinal_lucro = "+" if s["lucro_unidades"] >= 0 else ""
            sinal_roi = "+" if s["roi"] >= 0 else ""
            sinal_ev = "+" if s["ev_medio"] >= 0 else ""
            linhas.extend(
                [
                    "",
                    "💶 AUDITORIA DE ODDS REAIS",
                    f"Previsões liquidadas com odd congelada: {s['odds_liquidadas']}",
                    f"Resultado a 1u por previsão: {sinal_lucro}{s['lucro_unidades']:.2f}u",
                    f"ROI observado: {sinal_roi}{s['roi']*100:.1f}%",
                    f"EV médio no snapshot: {sinal_ev}{s['ev_medio']*100:.1f}%",
                    "As odds servem apenas para auditoria e não alteram retroativamente as seleções da V1.",
                ]
            )
        else:
            linhas.extend(
                [
                    "",
                    "ROI ainda não é apresentado porque não há previsões liquidadas com odds reais capturadas antes do início do jogo.",
                    "As previsões antigas sem snapshot de odd continuam válidas para hit rate/Brier, mas não entram no ROI.",
                ]
            )
        return "\n".join(linhas)