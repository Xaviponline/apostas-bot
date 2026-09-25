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
from estatisticas_espn import EstatisticasESPN
from main_sofascore import BotPremiumReal
from odds_auditoria import AuditoriaOdds
from previsoes_premium import RegistoPrevisoes
from nomes_ligas import nome_liga_pt


TZ_PORTUGAL = ZoneInfo("Europe/Lisbon")


class RegistoPrevisoesDiario(RegistoPrevisoes):
    """Liquidação robusta e auditoria segmentada das previsões diárias."""

    ALVO_V12_LIQUIDADAS = 40

    RESULTADO_LIGAS_EXTRA = {
        "english fa cup": "eng.fa",
        "english carabao cup": "eng.league_cup",
        "english league cup": "eng.league_cup",
        "spanish copa del rey": "esp.copa_del_rey",
        "german dfb-pokal": "ger.dfb_pokal",
        "italian coppa italia": "ita.coppa_italia",
        "french coupe de france": "fra.coupe_de_france",
        "portuguese taca de portugal": "por.taca.portugal",
        "dutch knvb beker": "ned.cup",
        "scottish cup": "sco.tennents",
        "scottish league cup": "sco.cis",
        "brazilian copa do brasil": "bra.copa_do_brazil",
        "argentine copa argentina": "arg.copa",
    }

    @classmethod
    def _codigo_liga_snapshot(cls, previsao):
        nome = " ".join(str((previsao or {}).get("liga") or "").lower().split())
        return cls.RESULTADO_LIGAS_EXTRA.get(nome) or EstatisticasESPN.LIGAS.get(nome)

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

        # A rota global /all pode omitir eventos que a descoberta encontrou
        # nos endpoints específicos. Para event_id ainda em falta, consulta
        # apenas as competições necessárias e nunca altera snapshots.
        pendentes_data = [
            p
            for p in self.dados.get("previsoes", [])
            if p.get("estado") == "pendente"
            and str(p.get("data_jogo") or "") == str(data_iso)
            and p.get("event_id") is not None
        ]
        faltam = {
            int(p["event_id"])
            for p in pendentes_data
            if int(p["event_id"]) not in resultados
        }

        por_codigo = {}
        for p in pendentes_data:
            try:
                event_id = int(p["event_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if event_id not in faltam:
                continue
            codigo = self._codigo_liga_snapshot(p)
            if codigo:
                por_codigo.setdefault(codigo, set()).add(event_id)

        for codigo, ids_codigo in sorted(por_codigo.items()):
            restantes = set(ids_codigo) - set(resultados)
            if not restantes:
                continue

            # Primeiro a data local gravada; só procura datas adjacentes se
            # ainda houver event_id em falta (proteção para jogos perto da meia-noite).
            for deslocamento in (0, -1, 1):
                if not restantes:
                    break
                alvo = (data_base + timedelta(days=deslocamento)).isoformat()
                try:
                    encontrados = super()._resultados_espn(alvo, codigo)
                except (requests.RequestException, RuntimeError, ValueError, TypeError):
                    continue
                resultados.update(encontrados)
                restantes -= set(encontrados)

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
        prob_media = sum(float(p["probabilidade"]) for p in liquidados) / total
        hit_rate = ganhos / total
        return {
            "total": total,
            "ganhos": ganhos,
            "perdas": total - ganhos,
            "hit_rate": hit_rate,
            "brier": brier,
            "prob_media": prob_media,
            "gap_calibracao": hit_rate - prob_media,
        }

    @staticmethod
    def _calibracao_texto(metricas):
        gap = float(metricas["gap_calibracao"]) * 100.0
        sinal = "+" if gap >= 0 else ""
        return (
            f"Prev {metricas['prob_media']*100:.1f}% | "
            f"Real {metricas['hit_rate']*100:.1f}% | "
            f"Gap {sinal}{gap:.1f}pp"
        )

    @staticmethod
    def _confianca_snapshot(previsao):
        persistida = str((previsao or {}).get("confianca_modelo") or "").strip()
        if persistida:
            return persistida

        try:
            qualidade = int(previsao["qualidade"])
            prob = float(previsao["probabilidade"])
        except (KeyError, TypeError, ValueError):
            return "DESCONHECIDA"

        # V1.0/V1.1 não guardavam a confiança. Reproduz exatamente a regra
        # histórica para não reclassificar snapshots antigos ao introduzir V1.2.
        versao = str(previsao.get("modelo_versao") or "").strip()
        if not versao or versao == "V1.1":
            if qualidade >= 85 and prob >= 0.62:
                return "ALTA"
            if qualidade >= 70 and prob >= 0.58:
                return "MÉDIA-ALTA"
            if qualidade >= 55:
                return "MÉDIA"
            return "BAIXA"

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
    def _faixa_ranking(previsao):
        try:
            ranking = int(previsao["ranking_modelo"])
        except (KeyError, TypeError, ValueError):
            return "Sem ranking (histórico)"
        if ranking <= 5:
            return "#1–5"
        if ranking <= 10:
            return "#6–10"
        if ranking <= 15:
            return "#11–15"
        if ranking <= 20:
            return "#16–20"
        return "#21+"

    @staticmethod
    def _versao_snapshot(previsao):
        versao = str(previsao.get("modelo_versao") or "").strip()
        return versao or "V1.0 (histórico)"

    def resumo_v12(self):
        """Estado operacional da V1.2 sem alterar snapshots nem resultados."""
        previsoes = [
            p
            for p in self.dados.get("previsoes", [])
            if self._versao_snapshot(p) == "V1.2"
        ]
        liquidadas = [
            p for p in previsoes if p.get("resultado_binario") in (0, 1)
        ]
        pendentes = [
            p
            for p in previsoes
            if p.get("estado") == "pendente"
            and p.get("resultado_binario") not in (0, 1)
        ]
        alvo = int(self.ALVO_V12_LIQUIDADAS)
        total_liquidadas = len(liquidadas)
        total_pendentes = len(pendentes)
        return {
            "alvo": alvo,
            "registadas": len(previsoes),
            "liquidadas": total_liquidadas,
            "pendentes": total_pendentes,
            "faltam": max(alvo - total_liquidadas, 0),
            "potencial": total_liquidadas + total_pendentes,
            "faltam_apos_pendentes": max(
                alvo - (total_liquidadas + total_pendentes), 0
            ),
            "progresso": min(total_liquidadas / alvo, 1.0) if alvo else 1.0,
            "metricas": self._metricas_grupo(liquidadas),
            "liquidadas_lista": liquidadas,
        }

    @staticmethod
    def _competicao_snapshot(previsao):
        liga = str(previsao.get("liga") or "Competição").strip() or "Competição"
        return nome_liga_pt(liga)

    @staticmethod
    def _float_seguro(valor):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return None
        if numero != numero or numero in (float("inf"), float("-inf")):
            return None
        return numero

    def _auditar_integridade_v12(self):
        """Verifica invariantes técnicos da V1.2 sem alterar qualquer snapshot."""
        previsoes = [
            p
            for p in self.dados.get("previsoes", [])
            if self._versao_snapshot(p) == "V1.2"
        ]
        chaves = []
        campos_criticos = (
            "event_id",
            "data_jogo",
            "timestamp_jogo",
            "mercado",
            "ranking_modelo",
            "confianca_modelo",
            "probabilidade",
            "probabilidade_bruta",
            "qualidade",
            "odd_justa",
            "odd_minima",
            "criada_em",
            "estado",
        )
        faltas = formula = odds = confianca = timing = ranking = 0
        telemetria_anomala = 0

        for p in previsoes:
            chave = p.get("chave")
            if not chave:
                chave = self._chave(p.get("event_id"), p.get("mercado"))
            chaves.append(str(chave))

            if any(p.get(campo) is None for campo in campos_criticos):
                faltas += 1

            prob = self._float_seguro(p.get("probabilidade"))
            bruta = self._float_seguro(p.get("probabilidade_bruta"))
            qualidade = p.get("qualidade")
            justa = self._float_seguro(p.get("odd_justa"))
            minima = self._float_seguro(p.get("odd_minima"))

            if prob is None or bruta is None or not (0.0 < prob < 1.0) or not (0.0 < bruta < 1.0):
                formula += 1
            else:
                esperada = 0.50 + ((bruta - 0.50) * 0.80)
                esperada = max(0.01, min(0.99, esperada))
                if abs(prob - esperada) > 0.00001:
                    formula += 1

                if (
                    justa is None
                    or minima is None
                    or abs(justa - (1.0 / prob)) > 0.015
                    or abs(minima - (1.05 / prob)) > 0.015
                ):
                    odds += 1

                try:
                    qualidade_int = int(qualidade)
                except (TypeError, ValueError):
                    qualidade_int = None
                if qualidade_int is not None:
                    esperada_conf = AnalisadorInteligente._confianca(
                        qualidade_int, prob
                    )
                    if str(p.get("confianca_modelo") or "") != esperada_conf:
                        confianca += 1

            try:
                rank = int(p.get("ranking_modelo"))
            except (TypeError, ValueError):
                rank = 0
            if rank < 1 or rank > AnalisadorInteligente.MAX_SELECOES:
                ranking += 1

            ts_jogo = self._float_seguro(p.get("timestamp_jogo"))
            criada_em = p.get("criada_em")
            try:
                criada = datetime.fromisoformat(
                    str(criada_em).replace("Z", "+00:00")
                )
                if criada.tzinfo is None:
                    criada = criada.replace(tzinfo=timezone.utc)
                criada_ts = criada.timestamp()
            except (TypeError, ValueError):
                criada_ts = None
            if (
                ts_jogo is None
                or criada_ts is None
                or criada_ts >= ts_jogo
            ):
                timing += 1

            diag = p.get("diagnostico_modelo")
            if isinstance(diag, dict):
                lc = self._float_seguro(diag.get("lambda_casa"))
                lf = self._float_seguro(diag.get("lambda_fora"))
                try:
                    ac = int(diag.get("amostra_casa"))
                    af = int(diag.get("amostra_fora"))
                    al = int(diag.get("amostra_liga"))
                except (TypeError, ValueError):
                    ac = af = al = -1
                if (
                    lc is None
                    or lf is None
                    or not (0.20 <= lc <= 3.80)
                    or not (0.20 <= lf <= 3.80)
                    or ac < 4
                    or af < 4
                    or al < 10
                ):
                    telemetria_anomala += 1

        duplicadas = max(len(chaves) - len(set(chaves)), 0)
        com_telemetria = sum(
            1 for p in previsoes if isinstance(p.get("diagnostico_modelo"), dict)
        )
        return {
            "total": len(previsoes),
            "duplicadas": duplicadas,
            "campos_criticos": faltas,
            "formula": formula,
            "odds": odds,
            "confianca": confianca,
            "ranking": ranking,
            "timing": timing,
            "telemetria": com_telemetria,
            "telemetria_anomala": telemetria_anomala,
        }

    def relatorio_modelo_lab(self):
        """Laboratório read-only: mede qualidade do sistema antes da V1.3."""
        resumo = self.resumo_v12()
        integridade = self._auditar_integridade_v12()
        metricas = resumo.get("metricas")
        erros = sum(
            integridade[chave]
            for chave in (
                "duplicadas",
                "campos_criticos",
                "formula",
                "odds",
                "confianca",
                "ranking",
                "timing",
                "telemetria_anomala",
            )
        )

        linhas = [
            "🧪 MODELO LAB — V1.2",
            "🔒 Motor de seleção: CONGELADO",
            "",
            "📦 AMOSTRA",
            f"• Registadas: {resumo['registadas']}",
            f"• Liquidadas: {resumo['liquidadas']}/{resumo['alvo']}",
            f"• Pendentes: {resumo['pendentes']}",
        ]
        if metricas:
            linhas.extend(
                [
                    f"• Acerto: {metricas['ganhos']}/{metricas['total']} "
                    f"({metricas['hit_rate']*100:.1f}%)",
                    f"• Brier: {metricas['brier']:.4f}",
                    f"• {self._calibracao_texto(metricas)}",
                ]
            )

        linhas.extend(
            [
                "",
                "🛡️ INTEGRIDADE TÉCNICA DOS SNAPSHOTS",
                f"• Chaves duplicadas: {integridade['duplicadas']}",
                f"• Campos críticos em falta: {integridade['campos_criticos']}",
                f"• Divergências fórmula V1.2: {integridade['formula']}",
                f"• Divergências odd justa/mínima: {integridade['odds']}",
                f"• Divergências de confiança: {integridade['confianca']}",
                f"• Ranking inválido: {integridade['ranking']}",
                f"• Snapshot criado após início: {integridade['timing']}",
            ]
        )
        if erros == 0:
            linhas.append("✅ Nenhuma anomalia técnica detetada.")

        linhas.extend(
            [
                "",
                "🔬 TELEMETRIA PARA A FUTURA V1.3",
                f"• Snapshots com diagnóstico detalhado: "
                f"{integridade['telemetria']}/{integridade['total']}",
                f"• Telemetria anómala: {integridade['telemetria_anomala']}",
                "• Novas previsões congelam: lambdas, PPG, amostras, "
                "médias da liga, inputs do Poisson, threshold e probabilidades "
                "brutas dos restantes mercados.",
                "• O histórico antigo não é enriquecido retroativamente.",
                "",
                "🧭 DECISÃO",
            ]
        )
        if resumo["liquidadas"] >= resumo["alvo"]:
            linhas.append(
                "✅ Meta V1.2 atingida. Podemos iniciar a auditoria para desenhar "
                "uma V1.3 controlada."
            )
        else:
            linhas.append(
                f"⏳ Faltam {resumo['faltam']} liquidadas V1.2 para a meta. "
                "Continuar a recolher evidência sem alterar o motor."
            )
        linhas.append("🛡️ Este laboratório é apenas leitura.")
        return "\n".join(linhas)

    def _relatorio_ciclo_v12(self):
        resumo = self.resumo_v12()
        if not resumo["registadas"]:
            return ""

        alvo = resumo["alvo"]
        liquidadas = resumo["liquidadas"]
        pendentes = resumo["pendentes"]
        linhas = [
            "🧭 CICLO DE VALIDAÇÃO V1.2",
            "• Estado do modelo: 🔒 CONGELADO",
            f"• Liquidadas: {liquidadas}/{alvo} | Pendentes: {pendentes} | "
            f"Registadas: {resumo['registadas']}",
            f"• Progresso para decisão V1.3: {resumo['progresso']*100:.1f}%",
        ]
        if liquidadas >= alvo:
            linhas.append(
                "✅ AMOSTRA-ALVO ATINGIDA — próxima etapa: auditoria da V1.2 "
                "antes de qualquer alteração de modelo."
            )
        elif resumo["potencial"] >= alvo:
            linhas.append(
                f"⏳ As pendentes atuais podem levar a {resumo['potencial']}/{alvo}; "
                f"faltam {resumo['faltam']} liquidadas neste momento."
            )
        else:
            if pendentes:
                linhas.append(
                    f"📌 Se as pendentes atuais liquidarem: "
                    f"{resumo['potencial']}/{alvo}; depois faltará "
                    f"{resumo['faltam_apos_pendentes']} nova liquidada."
                )
            else:
                linhas.append(
                    f"📌 Faltam {resumo['faltam']} previsões V1.2 liquidadas para a meta."
                )
        return "\n".join(linhas)

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
        por_ranking = {}
        por_versao = {}
        por_confianca = {}
        por_qualidade = {}
        alta_por_mercado = {}
        qualidade_alta_por_mercado = {}
        for p in liquidados:
            por_dia.setdefault(str(p.get("data_jogo") or "Sem data"), []).append(p)
            por_mercado.setdefault(
                str(p.get("mercado") or "Mercado desconhecido"), []
            ).append(p)
            por_competicao.setdefault(self._competicao_snapshot(p), []).append(p)
            por_probabilidade.setdefault(self._faixa_probabilidade(p), []).append(p)
            por_ranking.setdefault(self._faixa_ranking(p), []).append(p)
            por_versao.setdefault(self._versao_snapshot(p), []).append(p)
            confianca = self._confianca_snapshot(p)
            faixa_qualidade = self._faixa_qualidade(p)
            mercado = str(p.get("mercado") or "Mercado desconhecido")
            por_confianca.setdefault(confianca, []).append(p)
            por_qualidade.setdefault(faixa_qualidade, []).append(p)
            if confianca == "ALTA":
                alta_por_mercado.setdefault(mercado, []).append(p)
            if faixa_qualidade == "85–100":
                qualidade_alta_por_mercado.setdefault(mercado, []).append(p)

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
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f} | "
                f"{self._calibracao_texto(m)}"
            )

        ordem_ranking = ["#1–5", "#6–10", "#11–15", "#16–20", "#21+", "Sem ranking (histórico)"]
        linhas.extend(["", "🏅 DESEMPENHO POR RANKING DO MODELO"])
        for faixa in ordem_ranking:
            if faixa not in por_ranking:
                continue
            m = self._metricas_grupo(por_ranking[faixa])
            if m is None:
                continue
            linhas.append(
                f"• {faixa}: {m['ganhos']}/{m['total']} "
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f} | "
                f"{self._calibracao_texto(m)}"
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

        # Acompanhamento isolado da versão atual. Evita misturar V1.0/V1.1
        # quando se decide se a V1.2 precisa ou não de nova calibração.
        v12 = [p for p in liquidados if self._versao_snapshot(p) == "V1.2"]
        if v12:
            m_v12 = self._metricas_grupo(v12)
            linhas.extend(["", "🧬 V1.2 APENAS"])
            linhas.append(
                f"• Global: {m_v12['ganhos']}/{m_v12['total']} "
                f"({m_v12['hit_rate']*100:.1f}%) | Brier {m_v12['brier']:.4f} | "
                f"{self._calibracao_texto(m_v12)}"
            )

            grupos_v12 = {
                "Mercado": {},
                "Probabilidade": {},
                "Ranking": {},
                "Confiança": {},
                "Qualidade": {},
            }
            for p in v12:
                grupos_v12["Mercado"].setdefault(
                    str(p.get("mercado") or "Mercado desconhecido"), []
                ).append(p)
                grupos_v12["Probabilidade"].setdefault(
                    self._faixa_probabilidade(p), []
                ).append(p)
                grupos_v12["Ranking"].setdefault(
                    self._faixa_ranking(p), []
                ).append(p)
                grupos_v12["Confiança"].setdefault(
                    self._confianca_snapshot(p), []
                ).append(p)
                grupos_v12["Qualidade"].setdefault(
                    self._faixa_qualidade(p), []
                ).append(p)

            ordens_v12 = {
                "Mercado": sorted(grupos_v12["Mercado"]),
                "Probabilidade": ["55–59%", "60–64%", "65–69%", "70%+", "<55%", "Desconhecida"],
                "Ranking": ["#1–5", "#6–10", "#11–15", "#16–20", "#21+", "Sem ranking (histórico)"],
                "Confiança": ["ALTA", "MÉDIA-ALTA", "MÉDIA", "BAIXA", "DESCONHECIDA"],
                "Qualidade": ["85–100", "70–84", "55–69", "<55", "Desconhecida"],
            }

            for titulo in ("Mercado", "Probabilidade", "Ranking", "Confiança", "Qualidade"):
                linhas.append(f"• {titulo}:")
                for chave in ordens_v12[titulo]:
                    grupo = grupos_v12[titulo].get(chave)
                    if not grupo:
                        continue
                    m = self._metricas_grupo(grupo)
                    if m is None:
                        continue
                    etiqueta = f"Dados {chave}" if titulo == "Qualidade" else chave
                    linhas.append(
                        f"  ↳ {etiqueta}: {m['ganhos']}/{m['total']} "
                        f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f} | "
                        f"{self._calibracao_texto(m)}"
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
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f} | "
                f"{self._calibracao_texto(m)}"
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
                f"({m['hit_rate']*100:.1f}%) | Brier {m['brier']:.4f} | "
                f"{self._calibracao_texto(m)}"
            )

        linhas.extend(["", "🔎 CRUZAMENTO DOS GRUPOS DE ALERTA"])
        linhas.append("• Dados 85–100 por mercado:")
        if qualidade_alta_por_mercado:
            for mercado in sorted(qualidade_alta_por_mercado):
                m = self._metricas_grupo(qualidade_alta_por_mercado[mercado])
                if m is None:
                    continue
                linhas.append(
                    f"  ↳ {mercado}: {m['ganhos']}/{m['total']} "
                    f"({m['hit_rate']*100:.1f}%) | "
                    f"{self._calibracao_texto(m)}"
                )
        else:
            linhas.append("  ↳ Sem amostra.")

        linhas.append("• Confiança ALTA por mercado:")
        if alta_por_mercado:
            for mercado in sorted(alta_por_mercado):
                m = self._metricas_grupo(alta_por_mercado[mercado])
                if m is None:
                    continue
                linhas.append(
                    f"  ↳ {mercado}: {m['ganhos']}/{m['total']} "
                    f"({m['hit_rate']*100:.1f}%) | "
                    f"{self._calibracao_texto(m)}"
                )
        else:
            linhas.append("  ↳ Sem amostra.")

        return "\n".join(linhas)

    def relatorio(self):
        base = super().relatorio()
        blocos = [
            bloco
            for bloco in (
                self._relatorio_segmentado(),
                self._relatorio_ciclo_v12(),
            )
            if bloco
        ]
        if not blocos:
            return base

        extra = "\n\n".join(blocos)
        marcadores = (
            "\n\n💶 AUDITORIA DE ODDS REAIS",
            "\n\nROI ainda não é apresentado",
        )
        for marcador in marcadores:
            if marcador in base:
                return base.replace(marcador, f"\n\n{extra}{marcador}", 1)
        return f"{base}\n\n{extra}"


class BotPremiumDiario(BotPremiumReal):
    @staticmethod
    def _hora_portugal(timestamp):
        if not isinstance(timestamp, (int, float)):
            return "--:--"
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
            TZ_PORTUGAL
        ).strftime("%H:%M")

    @staticmethod
    def _barra_progresso(fracao, blocos=10):
        valor = max(0.0, min(float(fracao or 0.0), 1.0))
        cheios = min(int(round(valor * blocos)), blocos)
        return "█" * cheios + "░" * (blocos - cheios)

    def _executar_v12_status(self):
        """Centro de controlo read-only da versão atualmente em validação."""
        resumo = self.previsoes.resumo_v12()
        alvo = resumo["alvo"]
        liquidadas = resumo["liquidadas"]
        pendentes = resumo["pendentes"]
        linhas = [
            "🧬 V1.2 — CENTRO DE CONTROLO",
            "🔒 Estado: MODELO CONGELADO",
            f"🎯 Meta de validação: {alvo} liquidadas",
            "",
            f"📦 Registadas: {resumo['registadas']}",
            f"✅ Liquidadas: {liquidadas}/{alvo}",
            f"⏳ Pendentes: {pendentes}",
            f"📈 {self._barra_progresso(resumo['progresso'])} "
            f"{resumo['progresso']*100:.1f}%",
        ]

        metricas = resumo.get("metricas")
        if metricas:
            linhas.extend(
                [
                    "",
                    "📐 CALIBRAÇÃO ATUAL",
                    f"• Acerto: {metricas['ganhos']}/{metricas['total']} "
                    f"({metricas['hit_rate']*100:.1f}%)",
                    f"• Brier: {metricas['brier']:.4f}",
                    f"• {self.previsoes._calibracao_texto(metricas)}",
                ]
            )

        # Mostra apenas sinais de sobreconfiança com pelo menos cinco casos.
        # É diagnóstico: não muda filtros, thresholds, ranking ou snapshots.
        candidatos = []
        liquidadas_v12 = resumo.get("liquidadas_lista") or []
        definicoes = (
            ("Mercado", lambda p: str(p.get("mercado") or "Mercado desconhecido")),
            ("Ranking", self.previsoes._faixa_ranking),
            ("Confiança", self.previsoes._confianca_snapshot),
            ("Dados", self.previsoes._faixa_qualidade),
        )
        for tipo, chave_fn in definicoes:
            grupos = {}
            for previsao in liquidadas_v12:
                chave = chave_fn(previsao)
                grupos.setdefault(chave, []).append(previsao)
            for chave, grupo in grupos.items():
                m = self.previsoes._metricas_grupo(grupo)
                if (
                    m
                    and m["total"] >= 5
                    and float(m["gap_calibracao"]) <= -0.10
                ):
                    candidatos.append((float(m["gap_calibracao"]), tipo, chave, m))

        if candidatos:
            candidatos.sort(key=lambda item: (item[0], -item[3]["total"]))
            linhas.extend(["", "⚠️ SINAIS A ACOMPANHAR — amostra ainda curta"])
            for _, tipo, chave, m in candidatos[:3]:
                linhas.append(
                    f"• {tipo} {chave}: n={m['total']} | "
                    f"{self.previsoes._calibracao_texto(m)}"
                )

        linhas.extend(["", "🧭 PRÓXIMO PASSO"])
        if liquidadas >= alvo:
            linhas.append(
                "✅ Amostra-alvo atingida. Fazer auditoria completa antes de "
                "decidir qualquer V1.3."
            )
        elif resumo["potencial"] >= alvo:
            linhas.append(
                f"⏳ Se as {pendentes} pendentes liquidarem, ficamos em "
                f"{resumo['potencial']}/{alvo}. A V1.2 continua congelada."
            )
        else:
            if pendentes:
                linhas.append(
                    f"📌 Se as {pendentes} pendentes liquidarem: "
                    f"{resumo['potencial']}/{alvo}. Depois faltará "
                    f"{resumo['faltam_apos_pendentes']} nova liquidada."
                )
            else:
                linhas.append(
                    f"📌 Recolher mais {resumo['faltam']} liquidadas V1.2."
                )
            linhas.append("🔒 Sem alterações ao modelo até à meta de validação.")
        linhas.append("🛡️ Este comando é apenas leitura; não altera o histórico.")
        return "\n".join(linhas)

    def processar_comando(self, chat_id, texto, user_id=None, update_id=None):
        comando = texto.strip().partition(" ")[0]
        if "@" in comando:
            base, alvo = comando.split("@", 1)
            if self.username is None or alvo.lower() != self.username.lower():
                return
            comando = base

        if comando != "/v12_status":
            return super().processar_comando(chat_id, texto, user_id, update_id)

        if (
            not self.owner_id
            or not self.chat_id
            or chat_id != self.chat_id
            or user_id != self.owner_id
        ):
            return
        try:
            resposta = self._executar_v12_status()
        except (ValueError, KeyError, TypeError, ArithmeticError):
            resposta = (
                "Não foi possível gerar o estado V1.2. "
                "O histórico e o modelo não foram alterados."
            )
        self.enviar_mensagem(chat_id, resposta)

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
                "ranking_modelo": p.get("ranking_modelo"),
                "confianca": RegistoPrevisoesDiario._confianca_snapshot(p),
                "score": (
                    float(p["score_modelo"])
                    if isinstance(p.get("score_modelo"), (int, float))
                    else (
                        prob
                        if str(p.get("modelo_versao") or "") == "V1.2"
                        else (prob * 0.62) + ((qualidade / 100.0) * 0.38)
                    )
                ),
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
