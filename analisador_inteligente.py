"""Motor de análise premium baseado em resultados reais da ESPN.

Não usa probabilidades aleatórias nem odds fabricadas. A versão atual calcula
probabilidades de modelo e uma odd justa/mínima; odds reais de mercado entram
como camada independente de auditoria e não alteram a seleção da V1.
"""
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_espn import EstatisticasESPN
from nomes_ligas import nome_liga_pt


class AnalisadorInteligente:
    MARGEM_VALUE_ALVO = 0.05
    QUALIDADE_MINIMA = 55
    ODD_MINIMA_PERFIL = 1.50

    LIMITES = {
        "Vitória Casa": 0.56,
        "Vitória Fora": 0.56,
        "Ambas Marcam": 0.58,
        "Over 2.5 Golos": 0.57,
        "Under 2.5 Golos": 0.58,
        "Under 3.5 Golos": 0.64,
        "Over 1.5 Golos": 0.70,
        "1X (Casa ou Empate)": 0.70,
        "X2 (Empate ou Fora)": 0.70,
    }

    BANDEIRAS = {
        "english premier league": "🇬🇧",
        "premier league": "🇬🇧",
        "laliga": "🇪🇸",
        "spanish laliga": "🇪🇸",
        "italian serie a": "🇮🇹",
        "serie a": "🇮🇹",
        "german bundesliga": "🇩🇪",
        "bundesliga": "🇩🇪",
        "french ligue 1": "🇫🇷",
        "ligue 1": "🇫🇷",
        "ligue 2": "🇫🇷",
        "portuguese primeira liga": "🇵🇹",
        "primeira liga": "🇵🇹",
        "eredivisie": "🇳🇱",
        "keuken kampioen divisie": "🇳🇱",
        "belgian pro league": "🇧🇪",
        "turkish super lig": "🇹🇷",
        "super lig": "🇹🇷",
        "allsvenskan": "🇸🇪",
        "eliteserien": "🇳🇴",
        "brasileiro serie a": "🇧🇷",
        "brasileiro serie b": "🇧🇷",
        "argentine liga profesional": "🇦🇷",
        "uefa champions league": "🇪🇺",
        "champions league": "🇪🇺",
        "uefa europa league": "🇪🇺",
        "europa league": "🇪🇺",
        "uefa conference league": "🇪🇺",
        "conference league": "🇪🇺",
    }

    motivo_indisponivel = (
        "A análise premium precisa de jogos reais e histórico estatístico suficiente. "
        "Se os dados não forem suficientes, o bot não cria probabilidades de substituição."
    )

    def __init__(self, buscador_jogos=None, estatisticas=None):
        self.buscador = buscador_jogos
        self.estatisticas = estatisticas or EstatisticasESPN()
        self.ultimo_resumo = {"jogos": 0, "com_dados": 0, "selecoes": 0}
        self.ultimas_selecoes = []

    @property
    def data_hoje(self):
        return datetime.now(ZoneInfo("Europe/Lisbon")).strftime("%d/%m/%Y")

    @staticmethod
    def _confianca(qualidade, prob):
        if qualidade >= 85 and prob >= 0.62:
            return "ALTA"
        if qualidade >= 70 and prob >= 0.58:
            return "MÉDIA-ALTA"
        if qualidade >= 55:
            return "MÉDIA"
        return "BAIXA"

    @staticmethod
    def _probabilidade_conservadora(prob_bruta, qualidade):
        """Reduz excesso de confiança quando a amostra ainda é limitada."""
        prob_bruta = float(prob_bruta)
        q = max(0.0, min(1.0, float(qualidade) / 100.0))
        fiabilidade = 0.55 + (0.45 * q)
        ajustada = 0.50 + ((prob_bruta - 0.50) * fiabilidade)
        return max(0.01, min(0.99, ajustada))

    @staticmethod
    def _fmt_num(valor, casas=2):
        return f"{float(valor):.{casas}f}".replace(".", ",")

    @classmethod
    def _bandeira_liga(cls, liga):
        nome = str(liga or "").strip().lower()
        if nome in cls.BANDEIRAS:
            return cls.BANDEIRAS[nome]
        for chave, bandeira in cls.BANDEIRAS.items():
            if chave and chave in nome:
                return bandeira
        return "🌍"

    @staticmethod
    def _risco_e_estrelas(confianca):
        if confianca == "ALTA":
            return "🟢 RISCO BAIXO", "⭐⭐⭐⭐⭐"
        if confianca == "MÉDIA-ALTA":
            return "🟡 RISCO MODERADO", "⭐⭐⭐⭐"
        if confianca == "MÉDIA":
            return "🟠 RISCO MÉDIO", "⭐⭐⭐"
        return "🔴 RISCO ALTO", "⭐⭐"

    def _melhor_selecao(self, analise):
        qualidade = int(analise["qualidade"])
        if qualidade < self.QUALIDADE_MINIMA:
            return None

        candidatos = []
        for mercado, minimo in self.LIMITES.items():
            prob_bruta = float(analise["probabilidades"].get(mercado, 0.0))
            if prob_bruta <= 0 or prob_bruta >= 1:
                continue

            prob = self._probabilidade_conservadora(prob_bruta, qualidade)
            if prob < minimo:
                continue

            odd_justa = 1.0 / prob
            odd_minima = (1.0 + self.MARGEM_VALUE_ALVO) / prob
            if odd_minima < self.ODD_MINIMA_PERFIL:
                continue

            score = (prob * 0.62) + ((qualidade / 100.0) * 0.38)
            candidatos.append(
                {
                    "mercado": mercado,
                    "probabilidade": prob,
                    "probabilidade_bruta": prob_bruta,
                    "odd_justa": odd_justa,
                    "odd_minima": odd_minima,
                    "score": score,
                    "confianca": self._confianca(qualidade, prob),
                }
            )

        if not candidatos:
            return None
        melhor = max(candidatos, key=lambda x: (x["score"], x["probabilidade"]))
        return {**melhor, **analise}

    def gerar_todas_apostas(self, jogos):
        jogos = [j for j in (jogos or []) if isinstance(j, dict)]
        suportados = [j for j in jogos if self.estatisticas.resolver_liga(j)]
        self.ultimo_resumo = {"jogos": len(jogos), "com_dados": 0, "selecoes": 0}
        self.ultimas_selecoes = []
        if not suportados:
            return []

        historicos = self.estatisticas.carregar_historicos(suportados)
        selecoes = []
        com_dados = 0
        for jogo in suportados:
            codigo = self.estatisticas.resolver_liga(jogo)
            partidas = historicos.get(codigo) or []
            analise = self.estatisticas.analisar_jogo(jogo, partidas)
            if analise is None:
                continue
            com_dados += 1
            melhor = self._melhor_selecao(analise)
            if melhor is not None:
                selecoes.append(melhor)

        selecoes.sort(key=lambda x: (x["score"], x["qualidade"]), reverse=True)
        self.ultimas_selecoes = selecoes[:8]
        self.ultimo_resumo = {
            "jogos": len(jogos),
            "com_dados": com_dados,
            "selecoes": len(self.ultimas_selecoes),
        }
        return list(self.ultimas_selecoes)

    def gerar_relatorio(self, jogos, selecoes=None):
        """Relatório público/compacto com apresentação premium."""
        if selecoes is None:
            selecoes = self.gerar_todas_apostas(jogos)
        r = self.ultimo_resumo
        nome_selecoes = "SELEÇÃO" if r["selecoes"] == 1 else "SELEÇÕES"
        linhas = [
            f"🎯 ANÁLISE PREMIUM — {self.data_hoje}",
            f"📊 {r['selecoes']} {nome_selecoes} PARA HOJE",
            "🧠 Modelo V1 • Probabilidade conservadora",
        ]

        if not selecoes:
            linhas.extend(
                [
                    "",
                    "✅ Nenhuma seleção passou os filtros hoje.",
                    "O modelo não força apostas quando os dados ou a probabilidade não chegam ao mínimo.",
                ]
            )
            return "\n".join(linhas)

        grupos = OrderedDict()
        for s in sorted(selecoes, key=lambda x: str((x.get("jogo") or {}).get("horario") or "99:99")):
            hora = str((s.get("jogo") or {}).get("horario") or "--:--")
            grupos.setdefault(hora, []).append(s)

        numero = 1
        odds_reais = 0
        com_valor = 0
        abaixo_minima = 0
        sem_odd = 0
        for hora, itens in grupos.items():
            linhas.extend(["", f"⏰ {hora} — JOGOS"])
            for indice_item, s in enumerate(itens):
                if indice_item:
                    linhas.append("")
                j = s["jogo"]
                risco, estrelas = self._risco_e_estrelas(s["confianca"])
                liga_original = j.get("liga") or "Competição"
                liga = nome_liga_pt(liga_original)
                bandeira = self._bandeira_liga(liga_original)
                linhas.extend(
                    [
                        f"#{numero} {risco}",
                        f"   ⚽ {j.get('casa')} vs {j.get('fora')}",
                        f"   🏆 {bandeira} {liga}",
                        f"   💰 {s['mercado']}",
                        f"   📈 {self._fmt_num(s['probabilidade']*100, 1)}% | Odd justa {self._fmt_num(s['odd_justa'])}",
                        f"   ✅ Odd mínima: ≥ {self._fmt_num(s['odd_minima'])}",
                    ]
                )
                tem_odd_real = False
                try:
                    odd_real = float(s.get("odd_real"))
                    if odd_real > 1.0:
                        tem_odd_real = True
                        ev = float(s.get("ev_real", (float(s["probabilidade"]) * odd_real) - 1.0))
                        sinal = "+" if ev >= 0 else ""
                        linhas.append(
                            f"   💶 Odd real {self._fmt_num(odd_real)} | EV {sinal}{self._fmt_num(ev*100, 1)}%"
                        )
                        odds_reais += 1
                        if odd_real >= float(s["odd_minima"]):
                            linhas.append("   🟢 VALOR CONFIRMADO — odd real ≥ odd mínima")
                            com_valor += 1
                        else:
                            linhas.append("   🔴 SEM VALOR À ODD ATUAL — abaixo da odd mínima")
                            abaixo_minima += 1
                except (TypeError, ValueError):
                    tem_odd_real = False

                if not tem_odd_real:
                    linhas.append("   ⚪ ODD REAL INDISPONÍVEL — valor de mercado por validar")
                    sem_odd += 1

                linhas.extend(
                    [
                        f"   ⭐ {estrelas}",
                        f"   🧪 Dados {s['qualidade']}/100",
                    ]
                )
                numero += 1

        linhas.append("")
        if odds_reais:
            linhas.append(
                f"💶 Odds reais congeladas: {odds_reais}/{len(selecoes)}. Servem apenas para auditoria e não alteraram as seleções da V1."
            )
        else:
            linhas.append(
                "ℹ️ Sem odds reais de mercado não mostramos ROI/EV. Esses valores só entram quando forem medidos com odds reais."
            )
        linhas.append(
            f"🧭 Validação de mercado: {com_valor} com valor | {abaixo_minima} abaixo da mínima | {sem_odd} sem odd real."
        )
        linhas.append(
            f"📚 Jogos analisados: {r['jogos']} | Com dados suficientes: {r['com_dados']}"
        )
        return "\n".join(linhas)

    def gerar_relatorio_tecnico(self, jogos, selecoes=None):
        """Relatório técnico para validação do modelo; não altera as previsões."""
        if selecoes is None:
            selecoes = self.gerar_todas_apostas(jogos)
        r = self.ultimo_resumo
        linhas = [
            "🧠 ANÁLISE TÉCNICA — MODELO V1",
            f"📅 {self.data_hoje}",
            "",
            "Modelo: resultados ESPN reais + forma casa/fora + médias da liga + Poisson.",
            "A probabilidade exibida é conservadora e penaliza amostras menos robustas.",
            "Odds reais, quando disponíveis, são uma camada de auditoria e não mudam a seleção da V1.",
            "",
            f"Jogos do dia: {r['jogos']} | Com dados suficientes: {r['com_dados']} | Seleções: {r['selecoes']}",
        ]

        if not selecoes:
            linhas.extend(
                [
                    "",
                    "✅ Nenhuma seleção passou todos os filtros neste momento.",
                    "Isto é intencional: o bot não força apostas quando a amostra ou a probabilidade não chegam ao mínimo.",
                ]
            )
            if self.estatisticas.ultimo_erros:
                linhas.append(f"⚠️ Algumas competições ficaram sem histórico: {len(self.estatisticas.ultimo_erros)}.")
            return "\n".join(linhas)

        for i, s in enumerate(selecoes, 1):
            j = s["jogo"]
            diferenca = abs(s["probabilidade_bruta"] - s["probabilidade"])
            prob_linha = f"📊 Probabilidade conservadora: {s['probabilidade']*100:.1f}%"
            if diferenca >= 0.005:
                prob_linha += f" (bruta {s['probabilidade_bruta']*100:.1f}%)"
            linhas.extend(
                [
                    "",
                    f"{i}. ⚽ {j.get('casa')} vs {j.get('fora')}",
                    f"🏆 {nome_liga_pt(j.get('liga') or 'Competição')} — {j.get('horario') or '--:--'}",
                    f"🎯 {s['mercado']}",
                    prob_linha,
                    f"💰 Odd justa: {s['odd_justa']:.2f}",
                    f"✅ Só considerar se odd ≥ {s['odd_minima']:.2f}",
                    f"⚙️ Golos esperados pelo modelo: {s['lambda_casa']:.2f} - {s['lambda_fora']:.2f}",
                    f"📈 Forma (últimos jogos): {j.get('casa')} {s['ppg_casa']:.2f} PPG | {j.get('fora')} {s['ppg_fora']:.2f} PPG",
                    f"🧪 Qualidade dos dados: {s['qualidade']}/100 | Confiança: {s['confianca']}",
                    f"📚 Amostra: {s['amostra_casa']} + {s['amostra_fora']} jogos das equipas; {s['amostra_liga']} jogos da liga",
                ]
            )
            try:
                odd_real = float(s.get("odd_real"))
                if odd_real > 1.0:
                    ev = float(s.get("ev_real", (float(s["probabilidade"]) * odd_real) - 1.0))
                    sinal = "+" if ev >= 0 else ""
                    linhas.append(f"💶 Odd real: {odd_real:.2f} | EV snapshot: {sinal}{ev*100:.1f}%")
                    if odd_real >= float(s["odd_minima"]):
                        linhas.append("🟢 VALOR CONFIRMADO — odd real ≥ odd mínima")
                    else:
                        linhas.append("🔴 SEM VALOR À ODD ATUAL — abaixo da odd mínima")
                else:
                    linhas.append("⚪ ODD REAL INDISPONÍVEL — valor de mercado por validar")
            except (TypeError, ValueError):
                linhas.append("⚪ ODD REAL INDISPONÍVEL — valor de mercado por validar")

        linhas.extend(
            [
                "",
                "⚠️ Probabilidades são estimativas estatísticas, não garantias. Confirma sempre a odd real na casa de apostas que utilizares.",
            ]
        )
        return "\n".join(linhas)
