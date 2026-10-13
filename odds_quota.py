"""Contagem local aproximada de pedidos OddsPapi e orcamento por dia.

A quota devolvida por /account e a fonte autoritativa. O contador local
regista apenas chamadas feitas por este processo depois da instalacao.
Nao armazena API keys, parametros de pedidos nem respostas da OddsPapi.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile

TZ = ZoneInfo("Europe/Lisbon")
OPERACOES = frozenset({"ODDS_AUTO", "CLV_AUTO", "CLV_TARDIO", "MANUAL"})


class GestorQuotaOdds:
    RETENCAO_DIAS = 45
    RESERVA_CLV = 25

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    @staticmethod
    def _hoje(agora=None):
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ).date()

    def _ler(self):
        if self.path is None or not self.path.exists():
            return {"dias": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("dias"), dict):
                raise ValueError("Formato invalido.")
            return data
        except (OSError, ValueError, TypeError) as exc:
            # Nunca reescrever silenciosamente um ficheiro danificado.
            raise RuntimeError("Contador de quota indisponivel") from exc

    def _guardar(self, data):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".odds_quota_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def registar(self, endpoint, operacao="MANUAL", agora=None):
        """Um registo por tentativa HTTP efetivamente devolvida pelo cliente."""
        if self.path is None or endpoint == "/account":
            return 0
        dia = self._hoje(agora)
        data = self._ler()
        chave = dia.isoformat()
        reg = data["dias"].setdefault(chave, {"total": 0, "operacoes": {}, "endpoints": {}})
        categoria = operacao if operacao in OPERACOES else "MANUAL"
        api = str(endpoint).split("?")[0][:50]
        reg["total"] = int(reg.get("total", 0)) + 1
        reg["operacoes"][categoria] = int(reg["operacoes"].get(categoria, 0)) + 1
        reg["endpoints"][api] = int(reg["endpoints"].get(api, 0)) + 1
        from datetime import timedelta
        minimo = (dia - timedelta(days=self.RETENCAO_DIAS)).isoformat()
        data["dias"] = {
            k: v for k, v in data["dias"].items()
            if isinstance(k, str) and k >= minimo and isinstance(v, dict)
        }
        self._guardar(data)
        return reg["total"]

    def resumo(self, agora=None):
        hoje = self._hoje(agora).isoformat()
        data = self._ler()
        reg = data["dias"].get(hoje) or {}
        return {
            "dia": hoje,
            "total": int(reg.get("total", 0)),
            "operacoes": dict(reg.get("operacoes") or {}),
            "endpoints": dict(reg.get("endpoints") or {}),
            "dias_contados": len(data["dias"]),
        }

    @classmethod
    def plano(cls, status, agora=None):
        """Limite orientador so para chamadas automaticas nao-CLV."""
        if not isinstance(status, dict):
            return None
        restante = status.get("remaining")
        if not isinstance(restante, (int, float)) or restante < 0:
            return None
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ate = status.get("valid_until")
        dias = 30
        try:
            fim = datetime.fromisoformat(str(ate).replace("Z", "+00:00"))
            if fim.tzinfo is None:
                fim = fim.replace(tzinfo=timezone.utc)
            dias = max(1, (fim.astimezone(TZ).date() - dt.astimezone(TZ).date()).days + 1)
        except (ValueError, TypeError, OverflowError):
            pass
        reserva = min(cls.RESERVA_CLV, int(restante))
        utilizavel = max(0, int(restante) - reserva)
        objetivo = max(0, int(utilizavel * 0.9 / dias))
        return {
            "dias_restantes": dias,
            "restante": int(restante),
            "reserva_clv": reserva,
            "objetivo_dia": objetivo,
        }

    def permite_extra(self, status, operacao="ODDS_AUTO", agora=None):
        """CLV oficial so respeita a quota real, nunca a meta diaria."""
        if operacao == "CLV_AUTO":
            return True
        plano = self.plano(status, agora)
        if plano is None:
            return True
        if plano["restante"] <= plano["reserva_clv"]:
            return False
        if self.path is None:
            return True  # o controlo de reserva continua a funcionar
        resumo = self.resumo(agora)
        return resumo["total"] < plano["objetivo_dia"]

    def relatorio(self, status=None, agora=None):
        r = self.resumo(agora)
        plano = self.plano(status, agora)
        linhas = [
            "📊 GESTAO QUOTA — ODDSPAPI",
            f"Hoje ({r['dia']}): {r['total']} pedido(s) registado(s) por este bot",
            "Por operacao (contador local):",
        ]
        for op in ("ODDS_AUTO", "CLV_AUTO", "CLV_TARDIO", "MANUAL"):
            linhas.append(f"• {op}: {r['operacoes'].get(op, 0)}")
        if plano:
            linhas.extend([
                "",
                f"Quota real: {status.get('request_count', '?')}/{status.get('request_limit', '?')}",
                f"Restam: {plano['restante']} | Dias no ciclo: {plano['dias_restantes']}",
                f"Reserva de seguranca CLV: {plano['reserva_clv']}",
                f"Meta diaria dinamica (pedidos nao prioritarios): {plano['objetivo_dia']}",
            ])
        else:
            linhas.append("⚠️ Quota real indisponivel: consultar /odds_status")
        linhas.extend([
            "",
            "ℹ️ Contador local iniciado com esta atualizacao; nao reconstrói o passado.",
            "ℹ️ Os pedidos reais da conta podem incluir outras apps/chaves.",
            "🔒 O CLV oficial tem prioridade sobre a meta diaria.",
            "ℹ️ Este comando usa /account, sem descontar pedidos mensais.",
        ])
        return "\n".join(linhas)
