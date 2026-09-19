"""Arranque do bot com relatório diário completo no /analisa.

A geração de novas previsões continua a acontecer apenas antes do início dos
jogos. O relatório compacto junta essas novas previsões às previsões já
congeladas na auditoria para o mesmo dia local em Portugal (00:00–23:59).
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import logging
import requests

from analisador_inteligente import AnalisadorInteligente
from main_sofascore import BotPremiumReal
from odds_auditoria import AuditoriaOdds
from previsoes_premium import RegistoPrevisoes
from nomes_ligas import nome_liga_pt


TZ_PORTUGAL = ZoneInfo("Europe/Lisbon")


class RegistoPrevisoesDiario(RegistoPrevisoes):
    """Liquidação robusta e auditoria segmentada das previsões diárias."""

    def _resultados_espn(self, data_iso):
        """Procura o mesmo event_id numa janela de três datas ESPN."""
        try:
            data_base = datetime.strptime(str(data_iso), "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise ValueError("Data de jogo inválida para consulta ESPN.") from exc

        resultados = {}
        consultas_validas = 0
        ultimo_erro = None

        for deslocamento in (-1, 0, 1):
            alvo = (data_base + timedelta(days=deslocamento)).isoformat()
            try:
                encontrados = super()._resultados_espn(alvo)
            except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                ultimo_erro = exc
                continue
            consultas_validas += 1
            resultados.update(encontrados)

        if not consultas_validas:
            raise ValueError("Não foi possível consultar resultados ESPN.") from ultimo_erro
        return resultados

    @staticmethod
    def _metricas_grupo(previsoes):
        liquidados = [
            p for p in (previsoes or []) if p.get("resultado_binario") in (0, 1)
        ]
        if not liquidados:
            return None
        ganhos = sum(int(p["resultado_binario"]) for p in liquidados)
        total = len(liquidados)
        brier = sum(
            (float(p["probabilidade"]) - int(p["resultado_binario"])) ** 2
            for p in liquidados
        ) / total
        return {
            "total": total,
            "ganhos": ganhos,
            "perdas": total - ganhos,
            "hit_rate": ganhos / total,
            "brier": brier,
        }

    @staticmethod
    def _confianca_snapshot(previsao):
        try:
            qualidade = int(previsao["qualidade"])
            prob = float(previsao["probabilidade"])
        except (KeyError, TypeError, ValueError):
            return "DESCONHECIDA"
        return AnalisadorInteligente._confianca(qualidade, prob)

    @staticmethod
    def _faixa_qualidade(previsao):
        try:
            qualidade = int(previsao["qualidade"])
        except (KeyError, TypeError, ValueError):
            return "Desconhecida"
        if qualidade >= 85:
            return "85–100"
        if qualidade >= 70:
            return "70–84"
        if qualidade >= 55:
            return "55–69"
        return "<55"

    @staticmethod
    def _faixa_probabilidade(previsao):
        try:
            prob = float(previsao["probabilidade"]) * 100.0
        except (KeyError, TypeError, ValueError):
            return "Desconhecida"
        if prob >= 70.0:
            return "70%+"
        if prob >= 65.0:
            return "65–69%"
        if prob >= 60.0:
            return "60–64%"
        if prob >= 55.0:
            return "55–59%"
        return "<55%"

    @staticmethod
    def _versao_snapshot(previsao):
        versao = str(previsao.get("modelo_versao") or "").strip()
        return versao or "V1.0 (histórico)"

    @staticmethod
    def _competicao_snapshot(previsao):
        liga = str(previsao.get("liga") or "Competição").strip() or "Competição"
        return nome_liga_pt(liga)

    def _relatorio_segmentado(self):
        """Mostra apenas estatísticas; não altera previsões nem o modelo V1."""
        liquidados = [
            p
            for p in self.dados.get("previsoes", [])
            if p.get("resultado_binario") in (0, 1)
        ]
        if not liquidados:
            return ""

        por_dia = {}
        por_mercado = {}
        por_competicao = {}
        por_probabilidade = {}
        por_versao = {}
        por_confianca = {}
        por_qualidade = {}
        for p in liquidados:
            por_dia.setdefault(str(p.get("data_jogo") or "Sem data"), []).append(p)
            por_mercado.setdefault(
                str(p.get("mercado") or "Mercado desconhecido"), []
            ).append(p)
            por_competicao.setdefault(self._competicao_snapshot(p), []).append(p)
            por_probabilidade.setdefault(self._faixa_probabilidade(p), []).append(p)
            por_versao.setdefault(self._versao_snapshot(p), []).append(p)
            por_confianca.setdefault(self._confianca_snapshot(p), []).append(p)
            por_qualidade.setdefault(self._faixa_qualidade(p), []).append(p)

        linhas = ["📅 DESEMPENHO POR DIA"]
        for data_iso in sorted(por_dia):
            m = self._metricas_grupo(por_dia[data_iso])
            if m is None:
                continue
            try:
                etiqueta = datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m")
            except ValueError:
                etiqueta = data_iso
            linhas.append(
                f"• {etiqueta}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f}"
            )

        linhas.extend(["", "🎯 DESEMPENHO POR MERCADO"])
        for mercado in sorted(por_mercado):
            m = self._metricas_grupo(por_mercado[mercado])
            if m is None:
                continue
            linhas.append(
                f"• {mercado}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f}"
            )

        linhas.extend(["", "🏆 DESEMPENHO POR COMPETIÇÃO"])
        for competicao in sorted(por_competicao):
            m = self._metricas_grupo(por_competicao[competicao])
            if m is None:
                continue
            linhas.append(
                f"• {competicao}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f}"
            )

        ordem_probabilidade = ["55–59%", "60–64%", "65–69%", "70%+", "<55%", "Desconhecida"]
        linhas.extend(["", "📈 DESEMPENHO POR PROBABILIDADE"])
        for faixa in ordem_probabilidade:
            if faixa not in por_probabilidade:
                continue
            m = self._metricas_grupo(por_probabilidade[faixa])
            if m is None:
                continue
            linhas.append(
                f"• {faixa}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f}"
            )

        linhas.extend(["", "🧩 DESEMPENHO POR VERSÃO"])
        for versao in sorted(por_versao):
            m = self._metricas_grupo(por_versao[versao])
            if m is None:
                continue
            linhas.append(
                f"• {versao}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f}"
            )

        ordem_confianca = ["ALTA", "MÉDIA-ALTA", "MÉDIA", "BAIXA", "DESCONHECIDA"]
        estrelas = {
            "ALTA": "⭐⭐⭐⭐⭐",
            "MÉDIA-ALTA": "⭐⭐⭐⭐",
            "MÉDIA": "⭐⭐⭐",
            "BAIXA": "⭐⭐",
            "DESCONHECIDA": "—",
        }
        linhas.extend(["", "⭐ DESEMPENHO POR CONFIANÇA"])
        for confianca in ordem_confianca:
            if confianca not in por_confianca:
                continue
            m = self._metricas_grupo(por_confianca[confianca])
            if m is None:
                continue
            linhas.append(
                f"• {estrelas[confianca]} {confianca}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f}"
            )

        ordem_qualidade = ["85–100", "70–84", "55–69", "<55", "Desconhecida"]
        linhas.extend(["", "🧪 DESEMPENHO POR QUALIDADE DOS DADOS"])
        for faixa in ordem_qualidade:
            if faixa not in por_qualidade:
                continue
            m = self._metricas_grupo(por_qualidade[faixa])
            if m is None:
                continue
            linhas.append(
                f"• Dados {faixa}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f}"
            )
        return "\n".join(linhas)

    def relatorio(self):
        base = super().relatorio()
        segmentado = self._relatorio_segmentado()
        if not segmentado:
            return base

        marcadores = (
            "\n\n💶 AUDITORIA DE ODDS REAIS",
            "\n\nROI ainda não é apresentado",
        )
        for marcador in marcadores:
            if marcador in base:
                return base.replace(marcador, f"\n\n{segmentado}{marcador}", 1)
        return f"{base}\n\n{segmentado}"


class BotPremiumDiario(BotPremiumReal):
    @staticmethod
    def _hora_portugal(timestamp):
        if not isinstance(timestamp, (int, float)):
            return "--:--"
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
            TZ_PORTUGAL
        ).strftime("%H:%M")

    @staticmethod
    def _contar_competicoes(jogos):
        contador = Counter(
            str((j or {}).get("liga") or "Competição").strip() or "Competição"
            for j in (jogos or [])
            if isinstance(j, dict)
        )
        return sorted(contador.items(), key=lambda item: (-item[1], item[0].lower()))

    @staticmethod
    def _formatar_competicoes(contagens):
        return ", ".join(f"{nome} ({total})" for nome, total in (contagens or []))

    @staticmethod
    def _diagnostico_zero(
        total_jogos,
        total_futuros,
        total_suportados,
        resumo_novo,
        selecoes_novas,
        fora_cobertura=None,
        historico_indisponivel=None,
        jogos_historico_indisponivel=0,
    ):
        """Explica um dia sem seleções sem alterar qualquer filtro do V1."""
        com_dados = int((resumo_novo or {}).get("com_dados", 0) or 0)
        selecionadas = len(selecoes_novas or [])
        futuros = int(total_futuros)
        suportados = int(total_suportados)
        fora_total = max(futuros - suportados, 0)
        indisponiveis = max(int(jogos_historico_indisponivel or 0), 0)
        sem_amostra = max(suportados - com_dados - indisponiveis, 0)
        sem_selecao = max(com_dados - selecionadas, 0)
        linhas = [
            f"📚 Jogos encontrados hoje: {int(total_jogos)} | Futuros avaliados: {futuros}",
            f"🧭 Dentro da cobertura V1: {suportados} | Fora da cobertura: {fora_total}",
            f"🧪 Com dados suficientes: {com_dados} | Sem amostra suficiente: {sem_amostra}",
            f"🎯 Sem seleção após filtros: {sem_selecao}",
        ]
        if fora_cobertura:
            linhas.append(
                "🌍 Competições fora da cobertura: "
                + BotPremiumDiario._formatar_competicoes(fora_cobertura)
            )
        if historico_indisponivel:
            linhas.append(
                "⚠️ Histórico indisponível: " + ", ".join(historico_indisponivel)
            )
        return "\n".join(linhas)

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
            item = {
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
            try:
                odd_real = float(p.get("odd_real"))
                if odd_real > 1.0:
                    item["odd_real"] = odd_real
                    item["ev_real"] = float(p.get("ev_real", (prob * odd_real) - 1.0))
                    item["odds_fonte"] = p.get("odds_fonte") or ""
            except (TypeError, ValueError):
                pass
            selecoes.append(item)

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
        resolver = self.analisador.estatisticas.resolver_liga
        jogos_suportados = [j for j in jogos_futuros if resolver(j) is not None]
        jogos_fora_cobertura = [j for j in jogos_futuros if resolver(j) is None]

        selecoes_novas = []
        resumo_novo = {"jogos": len(jogos), "com_dados": 0, "selecoes": 0}
        if jogos_futuros:
            selecoes_novas = self.analisador.gerar_todas_apostas(jogos_futuros)
            resumo_novo = dict(self.analisador.ultimo_resumo)
            try:
                selecoes_novas = AuditoriaOdds(self.odds).enriquecer(selecoes_novas)
            except (RuntimeError, ValueError, TypeError):
                # A camada de odds é opcional e nunca pode impedir a análise V1.
                pass

        erros_historico = dict(self.analisador.estatisticas.ultimo_erros or {})
        codigos_erro = set(erros_historico)
        jogos_hist_indisponivel = [
            j for j in jogos_suportados if resolver(j) in codigos_erro
        ]

        nomes_por_codigo = {}
        for jogo in jogos_suportados:
            codigo = resolver(jogo)
            if not codigo:
                continue
            nome = str(jogo.get("liga") or "Competição").strip() or "Competição"
            nomes_por_codigo.setdefault(codigo, Counter())[nome] += 1

        historico_indisponivel = []
        for codigo in sorted(codigos_erro):
            nomes = nomes_por_codigo.get(codigo)
            if nomes:
                nome = nomes.most_common(1)[0][0]
                historico_indisponivel.append(f"{nome} [{codigo}]")
            else:
                historico_indisponivel.append(codigo)

        novas = self.previsoes.registar(selecoes_novas)
        selecoes_dia = self._selecoes_registadas_da_data(data_iso)

        if not jogos and not selecoes_dia:
            return self.buscador.formatar_jogos(jogos)

        ids_futuros = {
            j.get("id")
            for j in jogos_futuros
            if isinstance(j, dict) and j.get("id") is not None
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
        if not selecoes_dia:
            resposta += "\n" + self._diagnostico_zero(
                len(jogos),
                len(jogos_futuros),
                len(jogos_suportados),
                resumo_novo,
                selecoes_novas,
                self._contar_competicoes(jogos_fora_cobertura),
                historico_indisponivel,
                len(jogos_hist_indisponivel),
            )
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
        BotPremiumDiario(previsoes=RegistoPrevisoesDiario()).buscar_atualizacoes()
    except Exception:
        logging.error(
            "Arranque ou escrita interrompidos. Verifica configuração, histórico "
            "e permissões; detalhes omitidos para proteger credenciais."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
