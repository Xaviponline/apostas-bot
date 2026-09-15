"""Arranque do bot com relatório diário completo no /analisa.

A geração de novas previsões continua a acontecer apenas antes do início dos
jogos. O relatório compacto junta essas novas previsões às previsões já
congeladas na auditoria para o mesmo dia local em Portugal (00:00–23:59).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging

from main_sofascore import BotPremiumReal


TZ_PORTUGAL = ZoneInfo("Europe/Lisbon")


class BotPremiumDiario(BotPremiumReal):
    @staticmethod
    def _hora_portugal(timestamp):
        if not isinstance(timestamp, (int, float)):
            return "--:--"
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
            TZ_PORTUGAL
        ).strftime("%H:%M")

    def _selecoes_registadas_da_data(self, data_iso):
        """Reconstrói cartões compactos a partir dos snapshots auditados."""
        selecoes = []
        for p in self.previsoes.dados.get("previsoes", []):
            if p.get("data_jogo") != data_iso:
                continue
            try:
                prob = float(p["probabilidade"])
                prob_bruta = float(p.get("probabilidade_bruta", prob))
                qualidade = int(p["qualidade"])
                odd_justa = float(p["odd_justa"])
                odd_minima = float(p["odd_minima"])
            except (KeyError, TypeError, ValueError):
                continue

            timestamp = p.get("timestamp_jogo")
            selecoes.append(
                {
                    "jogo": {
                        "id": p.get("event_id"),
                        "casa": p.get("casa") or "?",
                        "fora": p.get("fora") or "?",
                        "liga": p.get("liga") or "Competição",
                        "timestamp": timestamp,
                        "horario": self._hora_portugal(timestamp),
                    },
                    "mercado": p.get("mercado") or "Mercado desconhecido",
                    "probabilidade": prob,
                    "probabilidade_bruta": prob_bruta,
                    "qualidade": qualidade,
                    "odd_justa": odd_justa,
                    "odd_minima": odd_minima,
                    "confianca": self.analisador._confianca(qualidade, prob),
                    "score": (prob * 0.62) + ((qualidade / 100.0) * 0.38),
                }
            )

        selecoes.sort(
            key=lambda s: (
                float((s.get("jogo") or {}).get("timestamp") or 0),
                str(s.get("mercado") or ""),
            )
        )
        return selecoes

    def _executar_analise(self, tecnica=False):
        # O relatório técnico mantém o comportamento original: os snapshots
        # antigos não guardam todos os campos técnicos (PPG, lambdas, amostras).
        if tecnica:
            return super()._executar_analise(tecnica=True)

        agora = datetime.now(TZ_PORTUGAL)
        data_iso = agora.strftime("%Y-%m-%d")
        agora_ts = agora.timestamp()
        jogos = self._jogos_hoje_portugal()

        # Nunca criar uma previsão nova depois de o jogo ter começado.
        jogos_futuros = [
            j
            for j in jogos
            if isinstance(j, dict)
            and isinstance(j.get("timestamp"), (int, float))
            and float(j["timestamp"]) > agora_ts
        ]

        selecoes_novas = []
        resumo_novo = {"jogos": len(jogos), "com_dados": 0, "selecoes": 0}
        if jogos_futuros:
            selecoes_novas = self.analisador.gerar_todas_apostas(jogos_futuros)
            resumo_novo = dict(self.analisador.ultimo_resumo)

        novas = self.previsoes.registar(selecoes_novas)
        selecoes_dia = self._selecoes_registadas_da_data(data_iso)

        if not jogos and not selecoes_dia:
            return self.buscador.formatar_jogos(jogos)

        ids_futuros = {
            j.get("id") for j in jogos_futuros if isinstance(j, dict) and j.get("id") is not None
        }
        ids_guardados_fora_da_consulta = {
            (s.get("jogo") or {}).get("id")
            for s in selecoes_dia
            if (s.get("jogo") or {}).get("id") not in ids_futuros
        }
        ids_guardados_fora_da_consulta.discard(None)

        self.analisador.ultimo_resumo = {
            "jogos": len(jogos),
            "com_dados": int(resumo_novo.get("com_dados", 0))
            + len(ids_guardados_fora_da_consulta),
            "selecoes": len(selecoes_dia),
        }
        resposta = self.analisador.gerar_relatorio(jogos, selecoes=selecoes_dia)
        resposta += "\n🕛 Janela diária: 00:00–23:59 (hora de Portugal)."
        if novas:
            resposta += (
                f"\n\n🧾 Auditoria: {novas} nova(s) previsão(ões) guardada(s) "
                "antes dos jogos."
            )
        return resposta


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        BotPremiumDiario().buscar_atualizacoes()
    except Exception:
        logging.error(
            "Arranque ou escrita interrompidos. Verifica configuração, histórico "
            "e permissões; detalhes omitidos para proteger credenciais."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
