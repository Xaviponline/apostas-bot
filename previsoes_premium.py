"""Registo auditável das previsões do motor premium.

Cada previsão é guardada antes do jogo e não é alterada por novas execuções do
/analisa. Depois do resultado final, pode ser liquidada e usada para medir taxa
de acerto e Brier Score. ROI só deve ser calculado quando existirem odds reais.
"""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile


class RegistoPrevisoes:
    VERSAO = 1

    def __init__(self, path=None):
        if path is None:
            data_dir = Path(os.getenv("DATA_DIR", "/data"))
            path = data_dir / "previsoes_premium.json"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
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

    def registar(self, selecoes):
        """Guarda apenas previsões novas. Nunca reescreve uma previsão existente."""
        existentes = {
            self._chave(p.get("event_id"), p.get("mercado"))
            for p in self.dados["previsoes"]
        }
        agora = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        adicionadas = 0
        for s in selecoes or []:
            jogo = s.get("jogo") or {}
            event_id = jogo.get("id")
            mercado = s.get("mercado")
            if event_id is None or not mercado:
                continue
            chave = self._chave(event_id, mercado)
            if chave in existentes:
                continue
            try:
                prob = float(s["probabilidade"])
                prob_bruta = float(s.get("probabilidade_bruta", prob))
                qualidade = int(s["qualidade"])
                odd_justa = float(s["odd_justa"])
                odd_minima = float(s["odd_minima"])
            except (KeyError, TypeError, ValueError):
                continue
            self.dados["previsoes"].append(
                {
                    "chave": chave,
                    "event_id": int(event_id),
                    "data_jogo": self._data_jogo(jogo),
                    "timestamp_jogo": jogo.get("timestamp"),
                    "casa": str(jogo.get("casa") or ""),
                    "fora": str(jogo.get("fora") or ""),
                    "liga": str(jogo.get("liga") or ""),
                    "mercado": str(mercado),
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
            )
            existentes.add(chave)
            adicionadas += 1
        if adicionadas:
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

    def atualizar_pendentes(self, buscador):
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
            jogos = buscador.buscar_todos_jogos_hoje(data_iso)
            por_id = {j.get("id"): j for j in jogos if j.get("id") is not None}
            for p in previsoes:
                jogo = por_id.get(p.get("event_id"))
                if not jogo or jogo.get("status") != "finished":
                    continue
                gc, gf = jogo.get("golos_casa"), jogo.get("golos_fora")
                if not isinstance(gc, int) or not isinstance(gf, int):
                    continue
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
        return {
            "total": len(todos),
            "pendentes": pendentes,
            "liquidadas": len(liquidados),
            "ganhos": ganhos,
            "perdas": perdas,
            "hit_rate": hit_rate,
            "brier": brier,
        }

    def relatorio(self):
        s = self.estatisticas()
        linhas = [
            "📊 PERFORMANCE DO MODELO — AUDITORIA",
            "",
            f"Previsões registadas: {s['total']}",
            f"Liquidadas: {s['liquidadas']} | Pendentes: {s['pendentes']}",
        ]
        if not s["liquidadas"]:
            linhas.extend(
                [
                    "",
                    "Ainda não há previsões liquidadas suficientes para avaliar o modelo.",
                    "As previsões ficam guardadas antes do jogo e não são reescritas pelo /analisa.",
                ]
            )
            return "\n".join(linhas)
        linhas.extend(
            [
                f"✅ Acertos: {s['ganhos']} | ❌ Falhas: {s['perdas']}",
                f"🎯 Taxa de acerto: {s['hit_rate']*100:.1f}%",
                f"📐 Brier Score: {s['brier']:.4f} (menor é melhor)",
                "",
                "ROI ainda não é apresentado porque não temos odds reais guardadas no momento da previsão.",
                "Quando ligarmos odds Betano, o ROI passará a fazer parte desta auditoria.",
            ]
        )
        return "\n".join(linhas)
