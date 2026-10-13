"""Auditoria passiva de odds e alertas de verificacao para o administrador.

Nunca corrige ou substitui odds historicas, nao altera a coorte V1.3 e nao
consulta a casa de apostas. Uma anomalia e um pedido de verificacao, NAO uma
prova de erro nem uma nova regra de elegibilidade.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile


TZ = ZoneInfo("Europe/Lisbon")


class VerificacaoOdds:
    LIMIAR_EV = 0.25
    LIMIAR_VS_MINIMA = 0.25

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    @staticmethod
    def _odd(v):
        try:
            n = float(v)
            return n if 1 < n < 1000 else None
        except (ValueError, TypeError):
            return None

    @classmethod
    def _anomalia_snapshot(cls, p):
        odd = cls._odd(p.get("odd_valor_confirmado"))
        if odd is None:
            odd = cls._odd(p.get("odd_real"))
        minima = cls._odd(p.get("odd_minima"))
        try:
            prob = float(p.get("probabilidade"))
        except (TypeError, ValueError):
            return None
        if odd is None or minima is None or not (0 < prob <= 1):
            return None
        if odd < minima:
            return None
        ev = prob * odd - 1
        distancia = odd / minima - 1
        if ev < cls.LIMIAR_EV and distancia < cls.LIMIAR_VS_MINIMA:
            return None
        return {
            "id": str(p.get("chave") or f"{p.get('event_id')}:{p.get('mercado')}"),
            "data": str(p.get("data_jogo") or ""),
            "inicio": p.get("timestamp_jogo"),
            "jogo": f"{p.get('casa') or '?'} vs {p.get('fora') or '?'}",
            "mercado": str(p.get("mercado") or "?"),
            "odd": odd,
            "minima": minima,
            "ev": ev,
            "desvio": distancia,
            "tipo": "odd_incomum",
        }

    def _ler(self):
        if self.path is None or not self.path.exists():
            return {"observacoes": {}, "avisados": []}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(dados, dict) or not isinstance(dados.get("observacoes"), dict) or not isinstance(dados.get("avisados"), list):
                raise ValueError("Marcador invalido")
            return dados
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Auditoria Odds indisponivel; ficheiro nao sobrescrito") from exc

    def _guardar(self, dados):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".verificacao_odds_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def registar(self, selecoes):
        """So regista metadados das verificacoes vindas de consulta ja feita."""
        if self.path is None:
            return 0
        candidatos = []
        for s in selecoes or []:
            if not isinstance(s, dict):
                continue
            jogo = s.get("jogo") or {}
            alertas = s.get("_odds_alertas") or []
            for alerta in alertas:
                if alerta not in {"horario_divergente", "competicao_divergente"}:
                    continue
                event_id = str(jogo.get("id") or "")
                mercado = str(s.get("mercado") or "")
                if not event_id or not mercado:
                    continue
                chave = f"{event_id}|{mercado}|{alerta}"
                candidatos.append((chave, {
                    "tipo": alerta,
                    "jogo": f"{jogo.get('casa') or '?'} vs {jogo.get('fora') or '?'}",
                    "mercado": mercado,
                    "data": datetime.fromtimestamp(float(jogo.get("timestamp") or 0), timezone.utc).astimezone(TZ).date().isoformat(),
                    "inicio": jogo.get("timestamp"),
                }))
        if not candidatos:
            return 0
        dados = self._ler()
        total = 0
        agora = datetime.now(timezone.utc).isoformat()
        for chave, item in candidatos:
            if chave not in dados["observacoes"]:
                dados["observacoes"][chave] = {**item, "chave": chave, "detectado_em": agora}
                total += 1
        # Retencao limitada sem eliminar marcadores enviados no mesmo ciclo.
        if len(dados["observacoes"]) > 250:
            ordenar = sorted(dados["observacoes"], key=lambda k: dados["observacoes"][k].get("detectado_em", ""))
            for k in ordenar[:-250]:
                dados["observacoes"].pop(k, None)
        self._guardar(dados)
        return total

    def verificacoes(self, previsoes, agora=None):
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        inicio_limite = (dt.astimezone(TZ).date() - timedelta(days=7)).isoformat()
        previsoes_reg = previsoes.dados.get("previsoes", [])
        out = []
        for p in previsoes_reg:
            anomalia = self._anomalia_snapshot(p)
            if anomalia and anomalia["data"] >= inicio_limite:
                out.append(anomalia)
        try:
            dados = self._ler()
            for item in dados["observacoes"].values():
                if isinstance(item, dict) and item.get("data", "") >= inicio_limite:
                    out.append(item)
        except RuntimeError:
            pass
        out.sort(key=lambda x: float(x.get("inicio") or 0), reverse=True)
        return out

    def relatorio(self, previsoes, agora=None):
        alertas = self.verificacoes(previsoes, agora)
        linhas = [
            "🔎 VERIFICACAO ODDS — AUDITORIA PASSIVA",
            f"Sinais que merecem revisao: {len(alertas)} (ultimos 7 dias)",
            "",
        ]
        if not alertas:
            linhas.append("Sem alertas registados neste periodo.")
        for a in alertas[:8]:
            titulo = "Odd/EV invulgar" if a["tipo"] == "odd_incomum" else a["tipo"].replace("_", " ")
            linhas.append(f"⚠️ {a['data']} {a['jogo']} | {a['mercado']}")
            if a["tipo"] == "odd_incomum":
                linhas.append(f"   {titulo}: @{a['odd']:.2f} | minima {a['minima']:.2f} | EV modelo {a['ev']*100:+.1f}%")
            else:
                linhas.append(f"   {titulo} — conferir torneio/horario do fornecedor")
        if len(alertas) > 8:
            linhas.append(f"+{len(alertas)-8} alertas adicionais")
        linhas.extend([
            "",
            "ℹ️ Um sinal invulgar nao prova odd errada. Confirmar na fonte.",
            "🔒 Nao altera odds congeladas, selecoes ou regras V1.3.",
            "ℹ️ Nao faz pedidos OddsPapi.",
        ])
        return "\n".join(linhas)

    def avisar(self, previsoes, enviar, agora=None):
        """Alertar so para jogos futuros de hoje, uma vez por chave."""
        if self.path is None:
            return 0
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = dt.timestamp()
        dia = dt.astimezone(TZ).date().isoformat()
        candidatos = [
            p for p in self.verificacoes(previsoes, agora=dt)
            if p.get("data") == dia
            and isinstance(p.get("inicio"), (float, int))
            and ts < float(p["inicio"]) <= ts + 24 * 3600
        ]
        if not candidatos:
            return 0
        dados = self._ler()
        avisados = set(str(x) for x in dados["avisados"])
        novos = []
        for c in candidatos:
            chave = f"{c['tipo']}|{c.get('id') or c.get('chave')}"
            if chave not in avisados:
                novos.append((chave, c))
        if not novos:
            return 0
        linhas = ["⚠️ VERIFICAR ODDS — ALERTA ADMIN", f"{len(novos)} sinal(is) para rever antes do jogo:"]
        for _, a in novos[:6]:
            linhas.append(f"• {a['jogo']} | {a['mercado']}")
            if a["tipo"] == "odd_incomum":
                linhas.append(f"  Odd {a['odd']:.2f} vs minima {a['minima']:.2f}; EV modelo {a['ev']*100:+.1f}%")
            else:
                linhas.append(f"  {a['tipo'].replace('_', ' ')}")
        linhas.extend(["🔎 /odds_verificacao para detalhes", "🔒 Aviso apenas; nenhuma odd ou previsao foi modificada."])
        enviar("\n".join(linhas))
        avisados.update(k for k, _ in novos)
        dados["avisados"] = sorted(avisados)[-500:]
        self._guardar(dados)
        return len(novos)
