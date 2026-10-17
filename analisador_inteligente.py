"""Motor de análise premium baseado em resultados reais da ESPN.

Não usa probabilidades aleatórias nem odds fabricadas. A versão atual calcula
probabilidades de modelo e uma odd justa/mínima; odds reais de mercado entram
como camada independente de auditoria e não alteram a seleção da V1.
"""
from math import isfinite
from collections import Counter
from datetime import timezone
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_espn import EstatisticasESPN
from nomes_ligas import nome_liga_pt


class AnalisadorInteligente:
    MODELO_VERSAO = "V1.2"
    MARGEM_VALUE_ALVO = 0.05
    QUALIDADE_MINIMA = 55
    ODD_MINIMA_PERFIL = 1.50
    MAX_SELECOES = 20

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
        "english league championship": "🇬🇧",
        "efl championship": "🇬🇧",
        "english league one": "🇬🇧",
        "efl league one": "🇬🇧",
        "english league two": "🇬🇧",
        "efl league two": "🇬🇧",
        "spanish laliga 2": "🇪🇸",
        "spanish segunda division": "🇪🇸",
        "laliga 2": "🇪🇸",
        "laliga": "🇪🇸",
        "spanish laliga": "🇪🇸",
        "italian serie b": "🇮🇹",
        "italian serie a": "🇮🇹",
        "serie a": "🇮🇹",
        "german 2. bundesliga": "🇩🇪",
        "2. bundesliga": "🇩🇪",
        "german bundesliga": "🇩🇪",
        "bundesliga": "🇩🇪",
        "french ligue 1": "🇫🇷",
        "ligue 1": "🇫🇷",
        "french ligue 2": "🇫🇷",
        "ligue 2": "🇫🇷",
        "portuguese primeira liga": "🇵🇹",
        "primeira liga": "🇵🇹",
        "eredivisie": "🇳🇱",
        "dutch eredivisie": "🇳🇱",
        "keuken kampioen divisie": "🇳🇱",
        "dutch keuken kampioen divisie": "🇳🇱",
        "belgian pro league": "🇧🇪",
        "turkish super lig": "🇹🇷",
        "super lig": "🇹🇷",
        "scottish premiership": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "scottish championship": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "austrian bundesliga": "🇦🇹",
        "danish superliga": "🇩🇰",
        "greek super league": "🇬🇷",
        "swiss super league": "🇨🇭",
        "allsvenskan": "🇸🇪",
        "swedish allsvenskan": "🇸🇪",
        "eliteserien": "🇳🇴",
        "norwegian eliteserien": "🇳🇴",
        "major league soccer": "🇺🇸",
        "mls": "🇺🇸",
        "brasileiro serie a": "🇧🇷",
        "brasileiro serie b": "🇧🇷",
        "brazilian serie a": "🇧🇷",
        "brazilian serie b": "🇧🇷",
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
        """Confiança V1.2 baseada na probabilidade, não na quantidade de dados."""
        prob = float(prob)
        if prob >= 0.68:
            return "ALTA"
        if prob >= 0.64:
            return "MÉDIA-ALTA"
        if prob >= 0.60:
            return "MÉDIA"
        return "BAIXA"

    @staticmethod
    def _probabilidade_conservadora(prob_bruta, qualidade):
        """Shrink fixo: qualidade valida dados, mas não amplifica a probabilidade."""
        prob_bruta = float(prob_bruta)
        # 0.80 aproxima o fator que a V1.1 já aplicava no limiar mínimo
        # de qualidade (55/100), evitando premiar duplamente amostras maiores.
        fiabilidade = 0.80
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

            # V1.2: qualidade é requisito de dados, não componente do ranking.
            score = prob
            candidatos.append(
                {
                    "mercado": mercado,
                    "probabilidade": prob,
                    "probabilidade_bruta": prob_bruta,
                    "odd_justa": odd_justa,
                    "odd_minima": odd_minima,
                    "score": score,
                    "confianca": self._confianca(qualidade, prob),
                    # Diagnóstico apenas: congela o limiar que esta seleção
                    # ultrapassou e a margem sobre esse limiar.
                    "limite_mercado": minimo,
                    "margem_limite": prob - minimo,
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

        selecoes.sort(
            key=lambda x: (x["score"], x["probabilidade_bruta"]),
            reverse=True,
        )
        for posicao, selecao in enumerate(selecoes, 1):
            selecao["ranking_modelo"] = posicao
        self.ultimas_selecoes = selecoes[: self.MAX_SELECOES]
        self.ultimo_resumo = {
            "jogos": len(jogos),
            "com_dados": com_dados,
            "selecoes": len(self.ultimas_selecoes),
        }
        return list(self.ultimas_selecoes)

    def gerar_relatorio(self, jogos, selecoes=None):
        """Vitrine de sugestões /analisa, sem alterar o modelo ou selecionar apostas.

        O preço real é apenas o que foi observado na execução, não uma odd
        em direto. Grupos são exclusivamente uma apresentação das seleções
        originais e não entram em SEL1, Top5, coortes ou gate.
        """
        if selecoes is None:
            selecoes = self.gerar_todas_apostas(jogos)
        r = self.ultimo_resumo
        total = len(selecoes)
        linhas = [
            f"🎯 ANÁLISE PREMIUM — {self.data_hoje}",
            "━━━━━━━━━━━━━━━━━━━━",
            f"⚽ {total} " + ("SUGESTÃO" if total == 1 else "SUGESTÕES") + " DO MODELO",
            f"🧠 V{self.MODELO_VERSAO.lstrip('V')} · Prognósticos estatísticos",
            "🔒 Ranking e mercados definidos antes de consultar as odds",
        ]

        if not selecoes:
            linhas.extend([
                "",
                "🛡️ NENHUMA SUGESTÃO HOJE",
                "Nenhuma seleção passou os filtros. O modelo não força apostas.",
                f"📚 Jogos analisados: {r['jogos']} | Com dados: {r['com_dados']}",
            ])
            return "\n".join(linhas)

        def odd_segura(valor):
            try:
                odd = float(valor)
            except (ValueError, TypeError, OverflowError):
                return None
            return odd if isfinite(odd) and 1.0 < odd < 1000 else None

        # /analisa acumula snapshots de várias execuções ao longo do dia.
        # Uma ronda tem no máximo MAX_SELECOES; o dia pode ter mais e
        # repetir rankings locais. Identificar sem modificar as entradas.
        rankings = Counter(
            int(s["ranking_modelo"])
            for s in selecoes
            if isinstance(s.get("ranking_modelo"), int)
            and not isinstance(s["ranking_modelo"], bool)
            and s["ranking_modelo"] > 0
        )
        repetidos = {rank: n for rank, n in rankings.items() if n > 1}
        agora_ts = datetime.now(timezone.utc).timestamp()
        iniciados = []
        grupos = {"valor": [], "sem_odd": [], "abaixo": []}
        for item in selecoes:
            real = odd_segura(item.get("odd_real"))
            minima = odd_segura(item.get("odd_minima"))
            ts = (item.get("jogo") or {}).get("timestamp")
            # Sem timestamp não se infere que o jogo começou. Os snapshots
            # reais têm timestamp, mas os históricos legados podem não ter.
            if isinstance(ts, (int, float)) and isfinite(float(ts)) and float(ts) <= agora_ts:
                iniciados.append((item, real, minima))
                continue
            if real is None or minima is None:
                grupo = "sem_odd"
            elif real >= minima:
                grupo = "valor"
            else:
                grupo = "abaixo"
            grupos[grupo].append((item, real, minima))

        def ordem(entrada):
            selecao = entrada[0]
            try:
                rank = int(selecao.get("ranking_modelo") or 999)
            except (TypeError, ValueError, OverflowError):
                rank = 999
            jogo = selecao.get("jogo") or {}
            return (rank, str(jogo.get("horario") or "99:99"), str(jogo.get("id") or ""))

        for entradas in grupos.values():
            entradas.sort(key=ordem)
        iniciados.sort(key=ordem)
        futuros = total - len(iniciados)

        linhas.extend([
            "📚 Lista acumulada do dia; máximo de 20 por execução.",
            f"🕒 {futuros} por começar  ·  ⛔ {len(iniciados)} já iniciados",
            "",
            f"💎 {len(grupos['valor'])} odds ≥ mínimo  ·  🟡 {len(grupos['sem_odd'])} sem odd",
            f"🔴 {len(grupos['abaixo'])} abaixo do mínimo",
        ])
        if repetidos:
            duplicados = ", ".join(f"#{rank} ({quantidade}x)" for rank, quantidade in sorted(repetidos.items()))
            linhas.append(f"⚠️ Rankings repetidos entre execuções: {duplicados}. Não representam um Top {total} único.")

        def bloco(cabecalho, grupo):
            entradas = grupos[grupo]
            if not entradas:
                return
            linhas.extend(["", "━━━━━━━━━━━━━━━━━━━━", f"{cabecalho} ({len(entradas)})", "━━━━━━━━━━━━━━━━━━━━"])
            for selecao, real, minima in entradas:
                jogo = selecao.get("jogo") or {}
                liga_original = jogo.get("liga") or "Competição"
                liga = nome_liga_pt(liga_original)
                bandeira = self._bandeira_liga(liga_original)
                rank = selecao.get("ranking_modelo")
                rotulo_rank = f"#{rank}" if rank else "histórico"
                marcador_rank = " ⚠️ repetido" if rank in repetidos else ""
                hora = str(jogo.get("horario") or "--:--")
                probabilidade = self._fmt_num(selecao["probabilidade"] * 100, 1)
                odd_justa = self._fmt_num(selecao["odd_justa"])
                minima_fmt = self._fmt_num(minima if minima is not None else selecao["odd_minima"])
                confianca = str(selecao.get("confianca") or "não indicada")
                mercado = str(selecao.get("mercado") or "Mercado por identificar")
                linhas.extend([
                    "",
                    f"🏅 RANKING {rotulo_rank}{marcador_rank}  ·  ⏰ {hora}",
                    f"⚽ {jogo.get('casa') or '?'} vs {jogo.get('fora') or '?'}",
                    f"🏆 {bandeira} {liga}",
                    f"🎯 {mercado}",
                ])
                if grupo == "valor":
                    linhas.extend([
                        f"📈 Modelo {probabilidade}% · Confiança {confianca}",
                        f"💶 Odd registada {self._fmt_num(real)}  |  Mín. {minima_fmt}",
                        f"⚖️ Odd justa {odd_justa}  |  Dados {selecao['qualidade']}/100",
                    ])
                    ev = (float(selecao["probabilidade"]) * real - 1.0) if real is not None else 0.0
                    alertas = selecao.get("_odds_alertas") or []
                    distancia = real / minima - 1 if minima else 0.0
                    if (alertas or ev >= 0.25 or distancia >= 0.25):
                        linhas.append(
                            f"⚠️ PREÇO/EV INVULGAR — verificar o evento e a odd "
                            f"(EV do modelo {ev*100:+.1f}%)".replace(".", ",")
                        )
                    else:
                        linhas.append("🟢 VALOR CONFIRMADO — pelo critério da odd mínima do modelo")
                elif grupo == "sem_odd":
                    linhas.extend([
                        f"📈 Modelo {probabilidade}% · Confiança {confianca}",
                        f"🟡 Odd por confirmar  |  Mínima ≥ {minima_fmt}",
                        f"⚪ ODD REAL INDISPONÍVEL — Odd justa {odd_justa}",
                    ])
                else:
                    linhas.extend([
                        f"📈 Modelo {probabilidade}% · Confiança {confianca}",
                        f"🔴 SEM VALOR À ODD ATUAL — registada {self._fmt_num(real)} < mínima {minima_fmt}",
                    ])

        bloco("💎 PREÇO ACIMA DO MÍNIMO", "valor")
        bloco("🟡 SUGESTÕES SEM ODD CONFIRMADA", "sem_odd")
        bloco("🔴 PREÇO ABAIXO DO MÍNIMO", "abaixo")

        if iniciados:
            linhas.extend([
                "", "━━━━━━━━━━━━━━━━━━━━",
                f"⛔ JOGOS JÁ INICIADOS — HISTÓRICO ({len(iniciados)})",
                "━━━━━━━━━━━━━━━━━━━━",
                "Não são sugestões disponíveis para apostar.",
            ])
            for item, real, _ in iniciados:
                jogo = item.get("jogo") or {}
                rank = item.get("ranking_modelo")
                rank_txt = f"#{rank}" if rank else "—"
                repetido = " ⚠️ repetido" if rank in repetidos else ""
                linhas.append(
                    f"• {jogo.get('horario') or '--:--'} · Ranking {rank_txt}{repetido} · "
                    f"{jogo.get('casa') or '?'} vs {jogo.get('fora') or '?'}"
                )
                linhas.append(f"  🎯 {item.get('mercado') or 'Mercado'} · ⛔ JÁ INICIADO")

        linhas.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📚 Jogos analisados: {r['jogos']} | Com dados suficientes: {r['com_dados']}",
            f"💶 Odds observadas em jogos futuros: {len(grupos['valor']) + len(grupos['abaixo'])}/{futuros}",
            f"🧭 Validação de mercado: {len(grupos['valor'])} com valor | "
            f"{len(grupos['abaixo'])} abaixo da mínima | {len(grupos['sem_odd'])} sem odd real.",
            "ℹ️ Odds são registos da consulta, não cotações em direto.",
            "⚠️ Probabilidade e VALUE são estimativas do modelo, não lucro garantido.",
            "🛡️ Um preço acima do mínimo não comprova vantagem estatística.",
        ])
        return "\n".join(linhas)

    def gerar_relatorio_tecnico(self, jogos, selecoes=None):
        """Relatório técnico para validação do modelo; não altera as previsões."""
        if selecoes is None:
            selecoes = self.gerar_todas_apostas(jogos)
        r = self.ultimo_resumo
        linhas = [
            f"🧠 ANÁLISE TÉCNICA — MODELO {self.MODELO_VERSAO}",
            f"📅 {self.data_hoje}",
            "",
            "Modelo: resultados ESPN reais + forma casa/fora + médias da liga + Poisson.",
            "A probabilidade exibida aplica shrink conservador fixo; a qualidade funciona como requisito mínimo de dados.",
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
                    f"🏅 Ranking modelo: #{s['ranking_modelo']}" if s.get("ranking_modelo") else "🏅 Ranking modelo: histórico",
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
