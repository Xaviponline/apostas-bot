"""Entrega OWNER do relatório diário, sem reexecutar análises nem odds.

Guarda as partes antes do envio e o progresso confirmado após cada resposta
Telegram. Se houver erro, retoma apenas as partes não confirmadas. Nunca
altera snapshots nem critérios do modelo V1.2/V1.3.
"""
import json
import os
import tempfile
from datetime import datetime
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("Europe/Lisbon")


class EntregaAnaliseOwner:
    def __init__(self, path=None):
        self.path = Path(path) if path else None

    def _ler(self):
        if self.path is None or not self.path.exists():
            return None
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(dados, dict)
                    or not isinstance(dados.get("dia"), str)
                    or not isinstance(dados.get("partes"), list)
                    or not dados["partes"]
                    or not all(isinstance(p, str) and p for p in dados["partes"])
                    or type(dados.get("enviadas")) is not int
                    or not 0 <= dados["enviadas"] <= len(dados["partes"])):
                raise ValueError("Estado de entrega inválido")
            return dados
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Estado de entrega OWNER indisponível") from exc

    def _guardar(self, dados):
        if self.path is None:
            raise RuntimeError("Sem caminho persistente para entrega OWNER")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".entrega_analise_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(dados, file, ensure_ascii=False, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def preparar(self, dia, relatorio, dividir):
        """Fila idempotente por dia. Não substituir nem repetir uma entrega."""
        if self.path is None:
            return False
        anterior = self._ler()
        if anterior is not None and anterior["dia"] == dia:
            return False
        if not isinstance(relatorio, str) or not relatorio.strip():
            return False
        partes = dividir("📩 ANÁLISES DOS JOGOS — ENVIO AUTOMÁTICO OWNER\n"
                        "🔒 Previsões estatísticas; odds observadas não são preços em direto.\n\n"
                        + relatorio)
        if not partes or not all(isinstance(p, str) and p for p in partes):
            return False
        self._guardar({"dia": dia, "partes": partes, "enviadas": 0})
        return True

    def enviar_pendentes(self, dia, enviar, max_partes=4):
        """Envia partes pendentes; grava o progresso só após sucesso do callback."""
        estado = self._ler()
        if estado is None or estado["dia"] != dia:
            return 0
        enviados = 0
        while estado["enviadas"] < len(estado["partes"]) and enviados < max_partes:
            parte = estado["partes"][estado["enviadas"]]
            enviar(parte)
            estado["enviadas"] += 1
            self._guardar(estado)
            enviados += 1
        return enviados

    def relatorio_guardado(self, dia):
        estado = self._ler()
        if estado is None or estado["dia"] != dia:
            return None
        return "\n\n".join(estado["partes"])


def resumo_analises_hoje(previsoes, agora=None):
    """Leitura local das previsões V1.2 por começar, sem novos pedidos externos."""
    from alertas_prejogo import AlertasPreJogo
    momento = agora or datetime.now(PT)
    if momento.tzinfo is None:
        raise ValueError("Instante sem fuso horário")
    momento = momento.astimezone(PT)
    itens = AlertasPreJogo._selecoes_do_dia(previsoes, momento)
    linhas = [
        f"📊 ANÁLISES GUARDADAS — {momento:%d/%m/%Y}",
        "🔒 Histórico pré-jogo V1.2; consulta local, zero odds/API.",
    ]
    futuros = [p for inicio, _, _, p in itens
               if inicio > momento.timestamp() and p.get("estado") == "pendente"]
    if not futuros:
        return "\n".join(linhas + [
            "⚪ Sem previsões guardadas por começar para hoje.",
            "O sistema não cria sugestões para preencher a lista.",
        ])
    linhas.append(f"⚽ {len(futuros)} previsões ainda por começar (máx. 20 da análise inicial)")
    for p in sorted(futuros, key=lambda x: (int(x["ranking_modelo"]),
                                             float(x["timestamp_jogo"]))):
        ts = float(p["timestamp_jogo"])
        prob = float(p["probabilidade"])
        qualidade = p.get("qualidade")
        try:
            qualidade = int(qualidade)
        except (TypeError, ValueError, OverflowError):
            qualidade = None
        def odd(v):
            try:
                n = float(v)
                return n if isfinite(n) and 1 < n < 1000 else None
            except (TypeError, ValueError, OverflowError):
                return None
        minima = odd(p.get("odd_minima"))
        justa = odd(p.get("odd_justa"))
        capturada = odd(p.get("odd_valor_confirmado"))
        if capturada is None:
            capturada = odd(p.get("odd_real"))
        if capturada is None:
            preco = "Sem odd real confirmada; VALUE por verificar"
        elif minima is not None and capturada >= minima:
            preco = f"Odd histórica {capturada:.2f} ≥ mínima {minima:.2f}; confirmar preço atual"
        else:
            preco = f"Odd histórica {capturada:.2f}; VALUE não confirmado"
        linhas.extend([
            "",
            f"🏅 #{p['ranking_modelo']} · {datetime.fromtimestamp(ts, PT):%H:%M}",
            f"⚽ {p.get('casa') or '?'} vs {p.get('fora') or '?'}",
            f"🏆 {p.get('liga') or 'Competição'}",
            f"🎯 {p.get('mercado') or 'Mercado'}",
            f"📈 Prob. {prob*100:.1f}% · Confiança {p.get('confianca_modelo') or 'N/D'}"
            + (f" · Dados {qualidade}/100" if qualidade is not None else ""),
            "⚖️ Odd justa " + (f"{justa:.2f}" if justa else "N/D")
            + " · Mínima " + (f"{minima:.2f}" if minima else "N/D"),
            "💶 " + preco,
        ])
    linhas.append("\n⚠️ Estimativas não garantem acertos ou lucro; snapshots e V1.3 intactos.")
    return "\n".join(linhas)
