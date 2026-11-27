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
    """Vitrine OWNER compacta do Top20 V1.2 guardado, sem consultar APIs.

    Agrupa por preço registado versus mínimo, não por apostas lucrativas.
    Mantém os índices/rankings originais, sem recalcular previsões ou odds.
    """
    from alertas_prejogo import AlertasPreJogo

    momento = agora or datetime.now(PT)
    if momento.tzinfo is None or momento.utcoffset() is None:
        raise ValueError("Instante sem fuso horário")
    momento = momento.astimezone(PT)
    itens = AlertasPreJogo._selecoes_do_dia(previsoes, momento)
    futuros = [p for inicio, _, _, p in itens
               if inicio > momento.timestamp() and p.get("estado") == "pendente"]
    linhas = [f"📊 ANÁLISES PREMIUM · {momento:%d/%m/%Y}"]
    if not futuros:
        return "\n".join(linhas + [
            "⚪ Sem previsões guardadas por começar para hoje.",
            "Nenhuma aposta é forçada para preencher a lista.",
            "🔒 Consulta local; sem novas odds ou alterações ao modelo.",
        ])

    def odd(valor):
        if isinstance(valor, bool):
            return None
        try:
            n = float(valor)
            return n if isfinite(n) and 1 < n < 1000 else None
        except (TypeError, ValueError, OverflowError):
            return None

    def fmt(numero, casas=2):
        return f"{numero:.{casas}f}".replace(".", ",")

    grupos = {"acima": [], "abaixo": [], "sem_odd": []}
    for p in futuros:
        minima = odd(p.get("odd_minima"))
        preco = odd(p.get("odd_valor_confirmado"))
        if preco is None:
            preco = odd(p.get("odd_real"))
        atual = odd(p.get("odd_mercado_atual"))
        estado = str(p.get("valor_estado") or "")
        if preco is None or minima is None:
            categoria = "sem_odd"
        elif (preco < minima or estado == "expirado"
              or (estado == "sem_valor" and atual is not None and atual < minima)):
            categoria = "abaixo"
        else:
            categoria = "acima"
        grupos[categoria].append((p, preco, minima, atual, estado))

    linhas.extend([
        f"⚽ {len(futuros)} jogos por começar · Rankings da análise inicial",
        f"🟠 {len(grupos['acima'])} acima da mínima (histórico)"
        f"  ·  🔴 {len(grupos['abaixo'])} sem valor/expiradas"
        f"  ·  ⚪ {len(grupos['sem_odd'])} sem cotação/mínima",
        "ℹ️ Odds guardadas, não são preços em direto.",
    ])

    secoes = (
        ("acima", "🟠 ODDS HISTÓRICAS ACIMA DA MÍNIMA"),
        ("abaixo", "🔴 ABAIXO DA MÍNIMA / VALOR EXPIRADO"),
        ("sem_odd", "⚪ AGUARDAM COTAÇÃO OU MÍNIMA"),
    )
    for categoria, titulo in secoes:
        entradas = grupos[categoria]
        if not entradas:
            continue
        linhas.extend(["", "━━━━━━━━━━━━━━━━━━━━",
                       f"{titulo} ({len(entradas)})", "━━━━━━━━━━━━━━━━━━━━"])
        for p, preco, minima, atual, estado in sorted(
            entradas, key=lambda a: (int(a[0]["ranking_modelo"]),
                                    float(a[0]["timestamp_jogo"]))
        ):
            hora = datetime.fromtimestamp(float(p["timestamp_jogo"]), PT).strftime("%H:%M")
            prob = float(p["probabilidade"])
            confianca = str(p.get("confianca_modelo") or "N/D")
            qualidade = p.get("qualidade")
            try:
                qualidade = int(qualidade) if qualidade is not None else None
            except (TypeError, ValueError, OverflowError):
                qualidade = None
            qualidade_txt = (
                f" · Dados {qualidade}/100"
                if qualidade is not None and 0 <= qualidade <= 100 else ""
            )
            linhas.extend([
                "",
                f"🏅 #{p['ranking_modelo']} · ⏰ {hora} · {p.get('liga') or 'Competição'}",
                f"⚽ {p.get('casa') or '?'} × {p.get('fora') or '?'}",
                f"🎯 {p.get('mercado') or 'Mercado'} · {fmt(prob * 100, 1)}% · {confianca}{qualidade_txt}",
            ])
            if categoria == "acima":
                linhas.append(
                    f"💶 Odd {fmt(preco)} · Mín. {fmt(minima)} · 🟠 Acima do mínimo*"
                )
                ev = prob * preco - 1
                distancia = preco / minima - 1
                if ev >= .25 or distancia >= .25:
                    linhas.append("⚠️ EV teórico invulgar — verificar jogo, mercado e preço")
            elif categoria == "abaixo":
                if estado == "expirado":
                    linhas.append(
                        f"💶 Odd {fmt(preco)} · Mín. {fmt(minima)} · 🔴 VALUE expirado"
                    )
                elif estado == "sem_valor" and atual is not None and atual < minima:
                    linhas.append(
                        f"💶 Última odd {fmt(atual)} · Mín. {fmt(minima)} · 🔴 Sem VALUE"
                    )
                else:
                    linhas.append(
                        f"💶 Odd {fmt(preco)} · Mín. {fmt(minima)} · 🔴 Sem VALUE"
                    )
            else:
                if preco is None:
                    linhas.append(
                        "💶 Sem cotação · Mín. "
                        + (fmt(minima) if minima is not None else "N/D")
                        + " · ⚪ Por verificar"
                    )
                else:
                    linhas.append(
                        f"💶 Odd {fmt(preco)} · Mín. indisponível · ⚪ Por verificar"
                    )
    linhas.append(
        "\n*Acima do mínimo histórico não significa VALUE executável. "
        "Confirma sempre a odd atual. Estimativas não garantem acertos ou lucro."
    )
    linhas.append("🔒 V1.2, V1.3, ranking e snapshots intactos · sem novas APIs.")
    return "\n".join(linhas)
