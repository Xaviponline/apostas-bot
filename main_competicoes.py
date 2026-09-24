"""Arranque de produção com cobertura V1 e histórico híbrido de competições."""
import logging

import requests
from collections import Counter
from datetime import datetime

from estatisticas_forma_web import EstatisticasFormaWeb
from main_diario import RegistoPrevisoesDiario, TZ_PORTUGAL
from main_enriquecido import (
    AnalisadorInteligenteEnriquecido,
    BotPremiumDiarioDiagnostico,
    BuscadorJogosEnriquecido,
)
from odds_auditoria import AuditoriaOdds


class BotPremiumDiarioCompeticoes(BotPremiumDiarioDiagnostico):
    def _executar_valor(self):
        """Compara previsões congeladas futuras com odds atuais sem persistir nada."""
        if not self.odds.configurada:
            return (
                "💎 VALOR AGORA\n\n"
                "Odds atuais indisponíveis: a fonte Betano não está configurada.\n"
                "As previsões congeladas não foram alteradas."
            )

        agora = datetime.now(TZ_PORTUGAL)
        agora_ts = agora.timestamp()
        data_iso = agora.strftime("%Y-%m-%d")
        selecoes = []

        for p in self.previsoes.dados.get("previsoes", []):
            if p.get("data_jogo") != data_iso or p.get("estado") != "pendente":
                continue
            ts = p.get("timestamp_jogo")
            if not isinstance(ts, (int, float)) or float(ts) <= agora_ts:
                continue
            try:
                prob = float(p["probabilidade"])
                odd_minima = float(p["odd_minima"])
                odd_justa = float(p["odd_justa"])
                qualidade = int(p["qualidade"])
            except (KeyError, TypeError, ValueError):
                continue

            selecoes.append(
                {
                    "jogo": {
                        "id": p.get("event_id"),
                        "casa": p.get("casa") or "?",
                        "fora": p.get("fora") or "?",
                        "liga": p.get("liga") or "Competição",
                        "timestamp": ts,
                    },
                    "mercado": p.get("mercado") or "Mercado desconhecido",
                    "probabilidade": prob,
                    "qualidade": qualidade,
                    "odd_justa": odd_justa,
                    "odd_minima": odd_minima,
                }
            )

        if not selecoes:
            return (
                f"💎 VALOR AGORA — {agora.strftime('%d/%m/%Y')}\n\n"
                "Não existem previsões congeladas ainda por começar hoje.\n"
                "O histórico não foi alterado."
            )

        atuais = AuditoriaOdds(self.odds).enriquecer(selecoes)
        atuais.sort(
            key=lambda s: (
                float((s.get("jogo") or {}).get("timestamp") or 0),
                str(s.get("mercado") or ""),
            )
        )

        confirmadas = abaixo = indisponiveis = 0
        linhas = [
            f"💎 VALOR AGORA — {agora.strftime('%d/%m/%Y')}",
            "📌 Odds atuais vs previsão V1 congelada",
            "",
        ]

        for s in atuais:
            jogo = s.get("jogo") or {}
            mercado = str(s.get("mercado") or "Mercado desconhecido")
            hora = self._hora_portugal(jogo.get("timestamp"))
            odd_minima = float(s.get("odd_minima") or 0)
            prob = float(s.get("probabilidade") or 0)
            odd_atual = s.get("odd_real")
            linhas.append(f"⏰ {hora} — {jogo.get('casa') or '?'} vs {jogo.get('fora') or '?'}")
            linhas.append(f"   💰 {mercado} | mínima {odd_minima:.2f}".replace(".", ","))

            try:
                odd_atual = float(odd_atual)
            except (TypeError, ValueError):
                odd_atual = None

            if odd_atual is None or odd_atual <= 1.0:
                indisponiveis += 1
                motivo = str(s.get("_odds_diag") or "odd atual indisponível")
                linhas.append(f"   ⚪ Odd atual indisponível — {motivo}")
            else:
                ev_atual = (prob * odd_atual) - 1.0
                if odd_atual >= odd_minima:
                    confirmadas += 1
                    estado = "🟢 VALOR AGORA"
                else:
                    abaixo += 1
                    estado = "🔴 ABAIXO DA MÍNIMA"
                linha = (
                    f"   {estado} — atual {odd_atual:.2f} | EV {ev_atual*100:+.1f}%"
                ).replace(".", ",")
                linhas.append(linha)
                if odd_minima > 0 and odd_atual >= odd_minima * 1.25:
                    linhas.append(
                        "   ⚠️ Diferença elevada face à odd mínima — confirmar evento/mercado."
                    )
            linhas.append("")

        linhas.extend(
            [
                f"📊 Agora: {confirmadas} com valor | {abaixo} abaixo da mínima | {indisponiveis} sem odd",
                "🔒 Esta consulta não altera a previsão nem a odd congelada para auditoria.",
            ]
        )
        return "\n".join(linhas).rstrip()

    @staticmethod
    def _formatar_instante_quota(valor):
        if not valor:
            return "não indicado pela API"
        try:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(TZ_PORTUGAL)
            return dt.strftime("%d/%m/%Y %H:%M")
        except (TypeError, ValueError):
            return str(valor)

    def _executar_odds_status(self):
        """Mostra uso da quota sem consumir a quota mensal do OddsPapi."""
        if not self.odds.configurada:
            return (
                "📡 ODDS STATUS\n\n"
                "Fonte de odds não configurada."
            )
        status_fn = getattr(self.odds, "status_conta", None)
        if not callable(status_fn):
            return (
                "📡 ODDS STATUS\n\n"
                f"Fonte: {self.odds.nome_fonte}\n"
                "Esta fonte não disponibiliza diagnóstico de quota."
            )

        dados = status_fn()
        if not isinstance(dados, dict):
            return (
                "📡 ODDS STATUS\n\n"
                "Não foi possível obter o estado da quota."
            )

        usados = int(dados.get("request_count") or 0)
        limite = int(dados.get("request_limit") or 0)
        restante = dados.get("remaining")
        restante = int(restante) if isinstance(restante, (int, float)) else None
        percentagem = ((usados / limite) * 100.0) if limite > 0 else 0.0

        if limite > 0 and restante == 0:
            estado = "🔴 QUOTA ESGOTADA"
        elif limite > 0 and percentagem >= 80:
            estado = "🟠 QUOTA BAIXA"
        else:
            estado = "🟢 QUOTA DISPONÍVEL"

        linhas = [
            "📡 ODDS STATUS",
            f"Fonte: {self.odds.nome_fonte}",
            f"Estado: {estado}",
            f"Pedidos usados: {usados}/{limite}" if limite > 0 else f"Pedidos usados: {usados}",
        ]
        if restante is not None:
            linhas.append(f"Restantes: {restante}")
        if limite > 0:
            linhas.append(f"Utilização: {percentagem:.1f}%".replace(".", ","))
        linhas.extend(
            [
                f"Último pedido: {self._formatar_instante_quota(dados.get('last_request'))}",
                f"Fim/renovação indicada: {self._formatar_instante_quota(dados.get('valid_until'))}",
                "",
                "ℹ️ Consultar este estado não desconta pedidos da quota mensal.",
            ]
        )
        return "\n".join(linhas)

    def processar_comando(self, chat_id, texto, user_id=None, update_id=None):
        comando = texto.strip().partition(" ")[0]
        if "@" in comando:
            base, alvo = comando.split("@", 1)
            if self.username is None or alvo.lower() != self.username.lower():
                return
            comando = base

        if comando in {"/valor", "/odds_status"}:
            if (
                not self.owner_id
                or not self.chat_id
                or chat_id != self.chat_id
                or user_id != self.owner_id
            ):
                return
            try:
                resposta = (
                    self._executar_valor()
                    if comando == "/valor"
                    else self._executar_odds_status()
                )
            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                ArithmeticError,
            ):
                if comando == "/valor":
                    resposta = (
                        "Não foi possível consultar as odds atuais. "
                        "As previsões e as odds congeladas não foram alteradas."
                    )
                else:
                    resposta = "Não foi possível consultar o estado da quota de odds."
            self.enviar_mensagem(chat_id, resposta)
            return

        super().processar_comando(chat_id, texto, user_id, update_id)

    def _executar_cobertura(self):
        base = super()._executar_cobertura()
        estatisticas = self.analisador.estatisticas
        diagnosticos = dict(getattr(estatisticas, "diagnostico_base", {}) or {})
        formas = dict(getattr(estatisticas, "_formas_globais", {}) or {})
        erros_forma = dict(getattr(estatisticas, "ultimo_erros_forma", {}) or {})
        diagnostico_formas = dict(
            getattr(estatisticas, "diagnostico_forma_global", {}) or {}
        )
        if not diagnosticos and not formas and not erros_forma and not diagnostico_formas:
            return base

        linhas = []
        if diagnosticos:
            linhas.extend(["", "🔬 Base histórica taças/UEFA:"])
            for codigo, diag in sorted(diagnosticos.items()):
                if not isinstance(diag, dict):
                    continue
                jogos = int(diag.get("jogos") or 0)
                fonte = str(diag.get("fonte") or "-")
                if fonte in {"cache", "cache_sofascore"}:
                    origem = "SofaScore cache" if fonte == "cache_sofascore" else "cache"
                    linhas.append(f"• {codigo}: {jogos} jogos | {origem}")
                    continue
                if fonte == "sofascore":
                    paginas = int(diag.get("paginas") or 0)
                    linhas.append(
                        f"• {codigo}: {jogos} jogos | SofaScore | páginas {paginas}"
                    )
                    continue
                if fonte == "sofascore_indisponivel":
                    motivo = str(diag.get("motivo") or "sem detalhe")
                    linhas.append(
                        f"• {codigo}: 0 jogos | SofaScore indisponível | {motivo}"
                    )
                    continue

                blocos = int(diag.get("blocos") or 0)
                ok = int(diag.get("blocos_ok") or 0)
                falhas = int(diag.get("blocos_falha") or 0)
                motivos = ", ".join(str(x) for x in (diag.get("motivos") or []))
                extra = f" | {motivos}" if motivos else ""
                linhas.append(
                    f"• {codigo}: {jogos} jogos | blocos OK {ok}/{blocos} | "
                    f"falhas {falhas}{extra}"
                )

        if formas or erros_forma or diagnostico_formas:
            suficientes = sum(1 for jogos in formas.values() if len(jogos or []) >= 4)
            insuficientes = sum(1 for jogos in formas.values() if len(jogos or []) < 4)
            linhas.extend([
                "",
                "⚙️ Forma recente multicompetição:",
                f"• Equipas com ≥4 jogos: {suficientes} | insuficientes: {insuficientes} | erros: {len(erros_forma)}",
            ])
            if erros_forma:
                contagem = Counter(str(motivo or "indisponível") for motivo in erros_forma.values())
                resumo = ", ".join(f"{motivo} ×{n}" for motivo, n in sorted(contagem.items()))
                linhas.append(f"• Falhas: {resumo}")

            melhores = []
            for diag in diagnostico_formas.values():
                if not isinstance(diag, dict):
                    continue
                tentativas = [
                    t for t in (diag.get("tentativas") or [])
                    if isinstance(t, dict) and "eventos" in t
                ]
                if not tentativas:
                    continue
                melhores.append(max(
                    tentativas,
                    key=lambda t: (
                        int(t.get("normalizados") or 0),
                        int(t.get("concluidos") or 0),
                        int(t.get("eventos") or 0),
                    ),
                ))
            if melhores:
                eventos = sum(int(t.get("eventos") or 0) for t in melhores)
                concluidos = sum(int(t.get("concluidos") or 0) for t in melhores)
                normalizados = sum(int(t.get("normalizados") or 0) for t in melhores)
                rotas = Counter(str(t.get("rota") or "-") for t in melhores)
                resumo_rotas = ", ".join(
                    f"{rota} ×{n}" for rota, n in sorted(rotas.items())
                )
                linhas.append(
                    f"• Melhor resposta/equipa: {eventos} eventos | {concluidos} concluídos | {normalizados} normalizados"
                )
                linhas.append(f"• Rotas: {resumo_rotas}")

        return base + "\n" + "\n".join(linhas)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        buscador = BuscadorJogosEnriquecido()
        estatisticas = EstatisticasFormaWeb()
        analisador = AnalisadorInteligenteEnriquecido(
            buscador_jogos=buscador,
            estatisticas=estatisticas,
        )
        BotPremiumDiarioCompeticoes(
            buscador=buscador,
            analisador=analisador,
            previsoes=RegistoPrevisoesDiario(),
        ).buscar_atualizacoes()
    except Exception:
        logging.error(
            "Arranque ou escrita interrompidos. Verifica configuração, histórico "
            "e permissões; detalhes omitidos para proteger credenciais."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
