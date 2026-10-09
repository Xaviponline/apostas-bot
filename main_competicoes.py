"""Arranque de produção com cobertura V1 e histórico híbrido de competições."""
import logging

import requests
from collections import Counter
from datetime import datetime

from acessos_premium import GestorAcessosPremium
from estatisticas_forma_web import EstatisticasFormaWeb
from main_diario import RegistoPrevisoesDiario, TZ_PORTUGAL
from main_enriquecido import (
    AnalisadorInteligenteEnriquecido,
    BotPremiumDiarioDiagnostico,
    BuscadorJogosEnriquecido,
)
from odds_auditoria import AuditoriaOdds
from research_export import ResearchLabClient


class BotPremiumDiarioCompeticoes(BotPremiumDiarioDiagnostico):
    def __init__(self, *args, acessos=None, research_lab=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acessos = acessos or GestorAcessosPremium()
        self.research_lab = research_lab or ResearchLabClient()

    def _e_owner_admin(self, chat_id, user_id):
        return bool(
            self.owner_id
            and self.chat_id
            and user_id == self.owner_id
            and chat_id == self.chat_id
        )

    def _cliente_ativo(self, chat_id, user_id):
        if user_id == self.owner_id and self.owner_id:
            return True
        if user_id is None or chat_id != user_id:
            return False
        return bool(self.acessos.estado(user_id).get("ativo"))

    @staticmethod
    def _formatar_validade_premium(validade):
        if validade is None:
            return "sem validade ativa"
        try:
            return validade.astimezone(TZ_PORTUGAL).strftime("%d/%m/%Y %H:%M")
        except (AttributeError, ValueError):
            return str(validade)

    def _executar_plano(self, user_id):
        if self.owner_id and user_id == self.owner_id:
            return (
                "👤 ACESSO PREMIUM\n\n"
                "🟣 Estado: OWNER / ADMIN\n"
                f"🆔 ID: {user_id}\n"
                "📅 Validade: permanente\n\n"
                "Comandos: /picks • /plano"
            )

        estado = self.acessos.estado(user_id)
        if not estado.get("ativo"):
            return (
                "👤 ACESSO PREMIUM\n\n"
                "🔴 Estado: inativo ou expirado\n"
                f"🆔 ID: {user_id}\n\n"
                "Para ativar o acesso, envia este ID ao responsável do serviço."
            )

        validade = self._formatar_validade_premium(estado.get("validade_ate"))
        dias = float(estado.get("segundos_restantes") or 0) / 86400.0
        return (
            "👤 ACESSO PREMIUM\n\n"
            "🟢 Estado: ATIVO\n"
            f"🆔 ID: {user_id}\n"
            f"📅 Válido até: {validade}\n"
            f"⏳ Tempo restante: {dias:.1f} dias\n\n"
            "Comandos: /picks • /plano"
        ).replace(".", ",")

    def _executar_picks_cliente(self):
        agora = datetime.now(TZ_PORTUGAL)
        data_iso = agora.strftime("%Y-%m-%d")
        agora_ts = agora.timestamp()
        previsoes = []
        for p in self.previsoes.dados.get("previsoes", []):
            if p.get("data_jogo") != data_iso or p.get("estado") != "pendente":
                continue
            ts = p.get("timestamp_jogo")
            if not isinstance(ts, (int, float)) or float(ts) <= agora_ts:
                continue
            try:
                prob = float(p["probabilidade"])
                odd_minima = float(p["odd_minima"])
            except (KeyError, TypeError, ValueError):
                continue
            previsoes.append((float(ts), int(p.get("ranking_modelo") or 999), p, prob, odd_minima))

        previsoes.sort(key=lambda item: (item[0], item[1]))
        if not previsoes:
            return (
                f"🎯 PREMIUM PICKS — {agora.strftime('%d/%m/%Y')}\n\n"
                "Ainda não existem picks Premium congeladas e por começar para hoje.\n"
                "Quando forem publicadas, aparecerão aqui sem alterar o modelo."
            )

        estrelas = {
            "ALTA": "⭐⭐⭐⭐⭐",
            "MÉDIA-ALTA": "⭐⭐⭐⭐",
            "MÉDIA": "⭐⭐⭐",
            "BAIXA": "⭐⭐",
        }
        linhas = [
            f"🎯 PREMIUM PICKS — {agora.strftime('%d/%m/%Y')}",
            f"📊 {len(previsoes)} seleções ainda por começar",
            "🔒 Previsões já congeladas pelo modelo",
            "",
        ]
        hora_anterior = None
        for _, ranking, p, prob, odd_minima in previsoes:
            hora = self._hora_portugal(p.get("timestamp_jogo"))
            if hora != hora_anterior:
                if hora_anterior is not None:
                    linhas.append("")
                linhas.append(f"⏰ {hora}")
                hora_anterior = hora
            confianca = str(p.get("confianca_modelo") or "").strip()
            estrela = estrelas.get(confianca, "⭐")
            linhas.extend(
                [
                    f"• ⚽ {p.get('casa') or '?'} vs {p.get('fora') or '?'}",
                    f"  💰 {p.get('mercado') or 'Mercado'}",
                    f"  📈 {prob*100:.1f}% | Odd mínima ≥ {odd_minima:.2f}".replace(".", ","),
                    f"  {estrela} {confianca or 'MODELO'} | Ranking #{ranking if ranking < 999 else '—'}",
                ]
            )
            estado_valor = str(p.get("valor_estado") or "")
            try:
                odd_atual = float(p.get("odd_mercado_atual"))
            except (TypeError, ValueError):
                odd_atual = None
            try:
                odd_confirmada = float(
                    p.get("odd_valor_confirmado", p.get("odd_real"))
                )
            except (TypeError, ValueError):
                odd_confirmada = None
            if estado_valor == "confirmado" and odd_confirmada and odd_confirmada > 1.0:
                linhas.append(
                    f"  🟢 Valor confirmado @ {odd_confirmada:.2f}".replace(".", ",")
                )
            elif estado_valor == "expirado":
                sufixo = (
                    f" — odd atual {odd_atual:.2f} < {odd_minima:.2f}"
                    if odd_atual and odd_atual > 1.0
                    else ""
                )
                linhas.append(("  ⛔ PICK EXPIRADO" + sufixo).replace(".", ","))
            elif estado_valor == "sem_valor" and odd_atual and odd_atual > 1.0:
                linhas.append(
                    f"  🔴 Sem valor à odd {odd_atual:.2f}".replace(".", ",")
                )

        linhas.extend(
            [
                "",
                "ℹ️ A odd mínima é o preço mínimo de referência do modelo.",
                "⚠️ Probabilidades são estimativas estatísticas, não garantias de resultado.",
            ]
        )
        return "\n".join(linhas)

    def _executar_clientes_admin(self):
        estados = self.acessos.listar()
        ativos = [e for e in estados if e.get("ativo")]
        inativos = [e for e in estados if not e.get("ativo")]
        linhas = [
            "👥 CLIENTES PREMIUM",
            f"🟢 Ativos: {len(ativos)} | ⚪ Inativos/expirados: {len(inativos)}",
        ]
        if not estados:
            linhas.extend(["", "Ainda não existem clientes registados."])
            return "\n".join(linhas)

        for estado in ativos + inativos:
            icone = "🟢" if estado.get("ativo") else "⚪"
            validade = self._formatar_validade_premium(estado.get("validade_ate"))
            linhas.append(f"• {icone} {estado.get('user_id')} — até {validade}")
        return "\n".join(linhas)

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
                    "ranking_modelo": p.get("ranking_modelo"),
                }
            )

        selecoes.sort(
            key=lambda s: (
                int(s.get("ranking_modelo") or 999),
                float((s.get("jogo") or {}).get("timestamp") or 0),
            )
        )

        if not selecoes:
            return (
                f"💎 VALOR AGORA — {agora.strftime('%d/%m/%Y')}\n\n"
                "Não existem previsões congeladas ainda por começar hoje.\n"
                "O histórico não foi alterado."
            )

        atuais = AuditoriaOdds(self.odds).enriquecer(
            selecoes,
            fallback_individual_ausentes=True,
            max_fallback_individual=5,
        )
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

    def _selecoes_futuras_para_mercado(self):
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
        return selecoes

    def _executar_sync_valor(self):
        """Atualiza estado comercial/CLV sem tocar na odd inicial nem no modelo."""
        if not self.odds.configurada:
            return (
                "🔄 SYNC VALOR\n\n"
                "Fonte de odds não configurada. Nenhum snapshot foi alterado."
            )
        selecoes = self._selecoes_futuras_para_mercado()
        if not selecoes:
            return (
                "🔄 SYNC VALOR\n\n"
                "Não existem previsões futuras para sincronizar hoje."
            )
        atuais = AuditoriaOdds(self.odds).enriquecer(
            selecoes,
            fallback_individual_ausentes=True,
            max_fallback_individual=8,
        )
        resumo = self.previsoes.atualizar_estado_mercado(atuais)
        diagnosticos = Counter()
        detalhes_diag = []
        for s in atuais:
            if s.get("odd_real") is not None:
                continue
            motivo = str(s.get("_odds_diag") or "odd_nao_associada")
            diagnosticos[motivo] += 1
            jogo = s.get("jogo") or {}
            detalhes_diag.append(
                (
                    f"{jogo.get('casa') or '?'} vs {jogo.get('fora') or '?'}",
                    str(s.get("mercado") or "Mercado"),
                    motivo,
                )
            )

        estados = Counter(
            str(p.get("valor_estado") or "sem_estado")
            for p in self.previsoes.dados.get("previsoes", [])
            if p.get("data_jogo") == datetime.now(TZ_PORTUGAL).strftime("%Y-%m-%d")
            and p.get("estado") == "pendente"
            and isinstance(p.get("timestamp_jogo"), (int, float))
            and float(p.get("timestamp_jogo")) > datetime.now(TZ_PORTUGAL).timestamp()
        )
        linhas = [
            "🔄 SYNC VALOR — CAMADA COMERCIAL",
            f"• Odds atuais associadas: {resumo['alterados']}",
            f"• Novos valores confirmados: {resumo['confirmados_novos']}",
            f"• Picks que expiraram agora: {resumo['expirados_novos']}",
            f"• Closing lines capturadas: {resumo['fechos_capturados']}",
            "",
            f"🟢 Confirmados: {estados.get('confirmado', 0)}",
            f"⛔ Expirados: {estados.get('expirado', 0)}",
            f"🔴 Sem valor: {estados.get('sem_valor', 0)}",
            f"⚪ Sem odd: {estados.get('sem_odd', 0) + estados.get('sem_estado', 0)}",
        ]
        if diagnosticos:
            linhas.extend(["", "🔎 DIAGNÓSTICO DAS ODDS"])
            nomes = {
                "evento_nao_encontrado": "evento não encontrado na fonte",
                "evento_ambiguo": "evento ambíguo",
                "betano_sem_odds_no_evento": "Betano sem odds nesse fixture",
                "odds_evento_sem_resposta": "fixture sem resposta de odds",
                "linha_ou_selecao_nao_disponivel": "mercado/linha não disponível",
                "odds_payload_evento_divergente": "payload do evento divergente",
                "odd_nao_extraida": "odd não extraída",
                "odds_quota_esgotada": "quota esgotada",
            }
            for motivo, total in diagnosticos.most_common():
                linhas.append(f"• {total}× {nomes.get(motivo, motivo)}")
            for jogo_nome, mercado, motivo in detalhes_diag[:8]:
                linhas.append(
                    f"  - {jogo_nome} | {mercado} → {nomes.get(motivo, motivo)}"
                )
        linhas.extend(
            [
                "",
                "🔒 Probabilidade, ranking, seleção e odd inicial congelada não foram alterados.",
                "ℹ️ Este comando consulta a fonte de odds e pode consumir quota.",
            ]
        )
        return "\n".join(linhas)

    def _executar_v13_comercial(self):
        m = self.previsoes.metricas_v13_comercial()
        linhas = [
            "💼 V1.3 COMERCIAL — TOP5 + VALUE",
            "🔒 Teste prospetivo pré-registado • V1.2 e SEL1 inalteradas",
            "",
            "🧪 REGRA FIXA",
            f"• Início: snapshot #{m['inicio_snapshot']} (09/10/2026)",
            "• Apenas ranking #1–5",
            "• Entrada só quando a primeira odd confirmada ≥ odd mínima",
            "• Stake fixa: 1u",
            f"• Coorte fixa: primeiras {m['alvo']} entradas elegíveis",
            f"• Dias mínimos: {m['min_dias']}",
            f"• CLV mínimo para avaliação: {m['min_clv_amostras']}/{m['alvo']} fechos",
            "• Gate: ROI > 0% E CLV médio > 0%",
            "• Sem substituição, extensão oportunista ou promoção automática",
            "",
            "📊 PROGRESSO",
            f"• Top5 monitorizadas desde o início: {m['top5_monitorizadas']}",
            f"• Entradas VALUE confirmadas: {m['coorte_tamanho']}/{m['alvo']}",
            f"• Liquidadas: {m['liquidadas']} | Pendentes: {m['pendentes']}",
            f"• Dias representados na coorte: {m['dias']}/{m['min_dias']}",
        ]
        if m["liquidadas"]:
            sinal = "+" if m["lucro_unidades"] >= 0 else ""
            sinal_roi = "+" if m["roi"] is not None and m["roi"] >= 0 else ""
            linhas.extend(
                [
                    f"• ✅ {m['ganhos']} | ❌ {m['perdas']}",
                    f"• P/L: {sinal}{m['lucro_unidades']:.2f}u".replace(".", ","),
                    f"• ROI: {sinal_roi}{m['roi']*100:.1f}%".replace(".", ","),
                    f"• Drawdown máximo: {m['max_drawdown']:.2f}u".replace(".", ","),
                    f"• Maior sequência de perdas: {m['max_streak_perdas']}",
                ]
            )
        if m["clv_amostras"]:
            sinal_clv = "+" if m["clv_media"] is not None and m["clv_media"] >= 0 else ""
            linhas.extend(
                [
                    f"• CLV: {m['clv_amostras']}/{m['coorte_tamanho']} amostras",
                    f"• CLV médio: {sinal_clv}{m['clv_media']*100:.1f}%".replace(".", ","),
                    f"• CLV positivo: {m['clv_positivos']}/{m['clv_amostras']}",
                ]
            )
        else:
            linhas.append("• CLV: ainda sem fechos capturados")

        if m["estado"] == "RECOLHA":
            linhas.extend(
                [
                    "",
                    f"⏳ EM RECOLHA — faltam {m['alvo']-m['coorte_tamanho']} entradas VALUE Top5 para fechar a coorte.",
                    "🛡️ Métricas intermédias são apenas acompanhamento e não permitem decisão.",
                ]
            )
        elif m["estado"] == "AGUARDA_LIQUIDACAO":
            linhas.extend(
                [
                    "",
                    "⏳ COORTE FECHADA — aguardar liquidação das 50 entradas antes da decisão.",
                ]
            )
        else:
            regras = m["regras"]
            linhas.extend(
                [
                    "",
                    "🧭 GATE FINAL",
                    f"• 50 entradas fixas: {'✅' if regras['coorte_50'] else '❌'}",
                    f"• ≥20 dias: {'✅' if regras['dias_20'] else '❌'}",
                    f"• 50 liquidadas: {'✅' if regras['liquidacao_completa'] else '❌'}",
                    f"• ROI > 0%: {'✅' if regras['roi_positivo'] else '❌'}",
                    f"• CLV ≥40/50: {'✅' if regras['clv_cobertura'] else '❌'}",
                    f"• CLV médio > 0%: {'✅' if regras['clv_positivo'] else '❌'}",
                    (
                        "✅ PASSOU — pode ir a auditoria final; nunca é promovida automaticamente."
                        if m["estado"] == "PASSOU"
                        else "❌ NÃO PASSOU — não alterar nem prolongar esta coorte para procurar outro resultado."
                    ),
                ]
            )
        return "\n".join(linhas)

    def _executar_carteira_shadow(self):
        m = self.previsoes.metricas_carteira_valor()
        linhas = [
            "💼 CARTEIRA SHADOW — VALUE",
            "🧪 Pré-oficial: não altera a V1.2 nem a SEL1.",
            "Regra: 1u apenas quando a odd capturada atingiu a odd mínima.",
            "",
            f"Entradas elegíveis: {m['elegiveis']}",
            f"Liquidadas: {m['liquidadas']} | Pendentes: {m['pendentes']}",
        ]
        if not m["liquidadas"]:
            linhas.append("Ainda não há entradas liquidadas suficientes para ROI.")
            return "\n".join(linhas)
        sinal = "+" if m["lucro_unidades"] >= 0 else ""
        sinal_roi = "+" if m["roi"] is not None and m["roi"] >= 0 else ""
        linhas.extend(
            [
                f"✅ {m['ganhos']} | ❌ {m['perdas']}",
                f"Resultado: {sinal}{m['lucro_unidades']:.2f}u".replace(".", ","),
                f"ROI: {sinal_roi}{m['roi']*100:.1f}%".replace(".", ","),
                f"Drawdown máximo: {m['max_drawdown']:.2f}u".replace(".", ","),
                f"Maior sequência de perdas: {m['max_streak_perdas']}",
                "",
                "⚠️ É uma auditoria shadow; só passa a carteira oficial após validação pré-definida.",
                "📋 Usa /carteira_detalhe para auditar cada entrada (sem gastar quota).",
            ]
        )
        return "\n".join(linhas)

    def _executar_carteira_detalhe(self, argumentos=""):
        """Livro de entradas VALUE, paginado, sem consultas externas nem mutações."""
        argumentos = str(argumentos or "").strip()
        if argumentos:
            partes = argumentos.split()
            if len(partes) != 1:
                return "Formato: /carteira_detalhe [PÁGINA]. Exemplo: /carteira_detalhe 2"
            try:
                pagina = int(partes[0])
            except ValueError:
                return "Formato: /carteira_detalhe [PÁGINA]. Exemplo: /carteira_detalhe 2"
        else:
            pagina = 1
        if pagina < 1:
            return "A página tem de ser 1 ou superior. Exemplo: /carteira_detalhe 1"

        entradas = self.previsoes.entradas_carteira_valor()
        if not entradas:
            return "📋 CARTEIRA VALUE — DETALHE\n\nAinda não existem entradas elegíveis."
        tamanho = 8
        paginas = (len(entradas) + tamanho - 1) // tamanho
        if pagina > paginas:
            return f"Só existem {paginas} página(s). Usa /carteira_detalhe {paginas}."

        linhas = [
            "📋 CARTEIRA VALUE — DETALHE",
            f"Entradas: {len(entradas)} | Página {pagina}/{paginas}",
            "🔒 Apenas leitura • odds congeladas preservadas",
            "",
        ]
        for item in entradas[(pagina - 1) * tamanho:pagina * tamanho]:
            data = item["data_jogo"]
            data_legivel = f"{data[8:10]}/{data[5:7]}" if len(data) == 10 else (data or "?")
            rank = item["ranking_modelo"]
            rank_txt = f"#{rank}" if rank not in (None, "") else "—"
            fecho = item["odd_fecho"]
            minima = item["odd_minima"]
            linhas.append(
                f"⚽ {data_legivel} — {item['casa']} vs {item['fora']}"
            )
            linhas.append(f"  {item['mercado']} | Ranking {rank_txt}")
            texto_odds = f"  Entrada {item['odd_entrada']:.2f}"
            if minima is not None:
                texto_odds += f" | Mín {minima:.2f}"
            texto_odds += f" | Fecho {fecho:.2f}" if fecho is not None else " | Fecho —"
            linhas.append(texto_odds.replace(".", ","))
            resultado = item["resultado_binario"]
            if resultado == 1:
                estado = "✅ GANHOU"
            elif resultado == 0:
                estado = "❌ PERDEU"
            else:
                estado = "⏳ PENDENTE"
            pnl = item["lucro_unidades"]
            texto_final = f"  {estado}"
            if pnl is not None:
                texto_final += f" | P/L {pnl:+.2f}u"
            clv = item["clv"]
            texto_final += f" | CLV {clv*100:+.1f}%" if clv is not None else " | CLV sem fecho"
            linhas.extend([texto_final.replace(".", ","), ""])

        linhas.append("ℹ️ CLV usa a odd efetivamente capturada perto do início; sem fecho não há CLV.")
        if pagina < paginas:
            linhas.append(f"➡️ Página seguinte: /carteira_detalhe {pagina+1}")
        return "\n".join(linhas)

    def _executar_clv(self):
        m = self.previsoes.metricas_clv()
        linhas = [
            "📉 CLV — CLOSING LINE VALUE",
            "Entrada = primeira odd com valor confirmado; fecho = odd capturada nos 30 min anteriores ao jogo.",
            "",
            f"Amostras com entrada + fecho: {m['total']}",
        ]
        if not m["total"]:
            linhas.extend(
                [
                    "Ainda não existem closing lines suficientes.",
                    "A captura automática tenta recolher a odd de fecho nos últimos 30 minutos antes do jogo.",
                    "O /sync_valor fica apenas como opção manual de auditoria.",
                ]
            )
            return "\n".join(linhas)
        sinal = "+" if m["media"] >= 0 else ""
        linhas.extend(
            [
                f"CLV médio: {sinal}{m['media']*100:.1f}%".replace(".", ","),
                f"CLV positivo: {m['positivos']}/{m['total']} ({m['positivos']/m['total']*100:.1f}%)".replace(".", ","),
                "",
                "ℹ️ CLV positivo significa que a odd de entrada foi melhor que a odd capturada perto do fecho.",
            ]
        )
        amostras = [
            p for p in self.previsoes.entradas_carteira_valor()
            if p["clv"] is not None
        ]
        if amostras:
            linhas.extend(["", "📋 FECHOS INDIVIDUAIS (mais recentes)"])
            for p in amostras[:6]:
                data = p["data_jogo"]
                data_legivel = f"{data[8:10]}/{data[5:7]}" if len(data) == 10 else (data or "?")
                linhas.append(
                    f"• {data_legivel} {p['casa']} vs {p['fora']} | {p['mercado']}"
                )
                linhas.append(
                    (f"  {p['odd_entrada']:.2f} → {p['odd_fecho']:.2f}"
                     f" | CLV {p['clv']*100:+.1f}%").replace(".", ",")
                )
            if len(amostras) > 6:
                linhas.append(f"• Mais {len(amostras)-6} amostra(s): ver /carteira_detalhe.")
        linhas.append("📋 Todas as entradas VALUE: /carteira_detalhe")
        return "\n".join(linhas)

    def _executar_integridade(self):
        m = self.previsoes.verificar_integridade()
        estado = "✅ SEM DIVERGÊNCIAS" if m["divergentes"] == 0 else "🚨 DIVERGÊNCIA DETETADA"
        return "\n".join(
            [
                "🛡️ INTEGRIDADE DOS SNAPSHOTS",
                f"Estado: {estado}",
                f"Total histórico: {m['total']}",
                f"Selados por hash: {m['protegidos']}",
                f"Hashes válidos: {m['validos']}",
                f"Divergentes: {m['divergentes']}",
                f"Legados sem hash: {m['legados_sem_hash']}",
                "",
                "ℹ️ Apenas snapshots criados após esta função são selados; históricos anteriores não são retro-selados.",
            ]
        )

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

    def _executar_lab_export(self):
        if not self.research_lab.configurado:
            return (
                "🧪 RESEARCH LAB\n\n"
                "⚪ Ainda não está configurado no Railway. "
                "A produção não foi alterada."
            )
        resposta = self.research_lab.exportar(
            self.previsoes.dados.get("previsoes", [])
        )
        total = int(resposta.get("records") or 0)
        digest = str(resposta.get("sha256") or "")
        estado = "✅ ACEITE" if resposta.get("accepted") else "⚠️ NÃO CONFIRMADO"
        return "\n".join(
            [
                "🧪 RESEARCH LAB — EXPORT",
                f"Estado: {estado}",
                f"Snapshots enviados: {total}",
                f"Dataset: {digest[:16] or '—'}",
                "Análise: agendada em shadow",
                "",
                "🔒 Só foram enviados campos desportivos/modelo.",
                "🛡️ V1.2, SEL1, V1.3 comercial e snapshots de produção não foram alterados.",
            ]
        )

    def _executar_lab_status(self):
        if not self.research_lab.configurado:
            return (
                "🧪 RESEARCH LAB\n\n"
                "⚪ Ainda não está configurado no Railway."
            )
        dados = self.research_lab.status()
        dataset = dados.get("dataset") if isinstance(dados.get("dataset"), dict) else {}
        report = dados.get("report") if isinstance(dados.get("report"), dict) else None
        linhas = [
            "🧠 RESEARCH LAB — CHAMPION vs CHALLENGERS",
            "🔒 Totalmente shadow • sem promoção automática",
            "",
            f"Dataset: {int(dataset.get('records') or 0)} snapshots",
            f"Execução em curso: {'sim' if dados.get('analysis_running') else 'não'}",
        ]
        if not report:
            linhas.extend(["", "⏳ Ainda não existe relatório concluído."])
            return "\n".join(linhas)

        champion = report.get("champion") or {}
        total = champion.get("total") or {}
        top5 = champion.get("top5") or {}
        linhas.extend(
            [
                "",
                "🏆 CHAMPION — V1.2",
                (
                    f"• Total: n={int(total.get('n') or 0)} | "
                    f"Brier {float(total['brier']):.4f} | "
                    f"Gap {float(total['gap_pp']):+.1f}pp"
                ).replace(".", ",")
                if total.get("brier") is not None
                else "• Sem amostra suficiente",
                (
                    f"• Top5: n={int(top5.get('n') or 0)} | "
                    f"Brier {float(top5['brier']):.4f} | "
                    f"Gap {float(top5['gap_pp']):+.1f}pp"
                ).replace(".", ",")
                if top5.get("brier") is not None
                else "• Top5 sem amostra suficiente",
                "",
                "🧪 CHALLENGERS WALK-FORWARD",
            ]
        )
        challengers = report.get("challengers") or {}
        for nome, item in challengers.items():
            if not isinstance(item, dict):
                continue
            estado = str(item.get("estado") or "?")
            n = int(item.get("oos_n") or 0)
            ch = item.get("challenger") or {}
            delta = item.get("delta_brier")
            if ch.get("brier") is None:
                linhas.append(f"• {nome}: {estado} | OOS n={n}")
                continue
            delta_txt = f"{float(delta):+.4f}" if delta is not None else "—"
            linhas.append(
                (
                    f"• {nome}: {estado} | OOS n={n} | "
                    f"Brier {float(ch['brier']):.4f} | Δ {delta_txt} | "
                    f"Gap {float(ch['gap_pp']):+.1f}pp"
                ).replace(".", ",")
            )

        drift = report.get("drift") or {}
        linhas.extend(
            [
                "",
                f"📡 Drift: {str(drift.get('estado') or '—')}",
            ]
        )
        mlflow = report.get("mlflow") or {}
        if mlflow.get("logged"):
            linhas.append(f"🧬 MLflow run: {str(mlflow.get('run_id') or '')[:12]}")
        elif mlflow.get("error"):
            linhas.append("⚠️ MLflow não registou esta execução; relatório local preservado.")
        linhas.extend(
            [
                "",
                "🛡️ Um challenger nunca entra em produção automaticamente.",
                "Qualquer vencedor terá de passar um teste prospetivo pré-registado.",
            ]
        )
        return "\n".join(linhas)

    @staticmethod
    def _lab_drift_icone(estado):
        return {
            "ALTO": "🔴",
            "MODERADO": "🟠",
            "ESTAVEL": "🟢",
            "AMOSTRA_INSUFICIENTE": "⚪",
        }.get(str(estado or ""), "⚪")

    def _executar_lab_drift(self):
        if not self.research_lab.configurado:
            return "🧪 RESEARCH LAB\n\n⚪ Ainda não está configurado no Railway."
        dados = self.research_lab.status()
        report = dados.get("report") if isinstance(dados.get("report"), dict) else None
        if not report:
            return "📡 RESEARCH LAB — DRIFT\n\n⏳ Ainda não existe relatório concluído."

        drift = report.get("drift") if isinstance(report.get("drift"), dict) else {}
        estado = str(drift.get("estado") or "AMOSTRA_INSUFICIENTE")
        base = drift.get("base") if isinstance(drift.get("base"), dict) else {}
        recente = drift.get("recente") if isinstance(drift.get("recente"), dict) else {}
        linhas = [
            "📡 RESEARCH LAB — DRIFT DETALHADO",
            "🔒 Diagnóstico shadow • não altera o modelo",
            "",
            f"Estado: {self._lab_drift_icone(estado)} {estado}",
            f"Amostra com telemetria: {int(drift.get('n') or 0)}",
        ]
        if base or recente:
            linhas.extend(
                [
                    (
                        f"Base: n={int(base.get('n') or 0)} | "
                        f"snapshots #{base.get('snapshot_min') or '—'}–#{base.get('snapshot_max') or '—'}"
                    ),
                    (
                        f"Recente: n={int(recente.get('n') or 0)} | "
                        f"snapshots #{recente.get('snapshot_min') or '—'}–#{recente.get('snapshot_max') or '—'}"
                    ),
                ]
            )

        labels = {
            "probabilidade": "Probabilidade calibrada",
            "probabilidade_bruta": "Probabilidade bruta",
            "lambda_total": "Lambda total",
            "lambda_diff": "Diferença de lambda",
            "ppg_diff": "Diferença PPG",
            "margem_limite": "Margem sobre threshold",
            "amostra_local_min": "Amostra local mínima",
            "media_liga_total": "Média de golos da liga",
        }
        detalhes = drift.get("numeric_details") if isinstance(drift.get("numeric_details"), dict) else {}
        if detalhes:
            linhas.extend(["", "🔬 VARIÁVEIS NUMÉRICAS — PSI"])
            ordenados = sorted(
                detalhes.items(),
                key=lambda kv: float((kv[1] or {}).get("psi") or 0.0),
                reverse=True,
            )
            for nome, item in ordenados:
                if not isinstance(item, dict) or item.get("psi") is None:
                    continue
                psi = float(item["psi"])
                est = str(item.get("estado") or "")
                b = item.get("base_media")
                r = item.get("recente_media")
                if b is None or r is None:
                    media = ""
                else:
                    media = f" | média {float(b):.3f}→{float(r):.3f}"
                linhas.append(
                    (
                        f"• {self._lab_drift_icone(est)} {labels.get(nome, nome)}: "
                        f"PSI {psi:.3f}{media}"
                    ).replace(".", ",")
                )

        categorico = drift.get("categorical") if isinstance(drift.get("categorical"), dict) else {}
        if categorico:
            linhas.extend(["", "🧩 COMPOSIÇÃO — DISTÂNCIA TOTAL"])
            cat_labels = {"mercado": "Mercados", "liga": "Ligas"}
            for nome, item in categorico.items():
                if not isinstance(item, dict) or item.get("tv_distance") is None:
                    continue
                tv = float(item["tv_distance"])
                est = str(item.get("estado") or "")
                linhas.append(
                    (
                        f"• {self._lab_drift_icone(est)} {cat_labels.get(nome, nome)}: "
                        f"{tv:.3f}"
                    ).replace(".", ",")
                )
                for mudanca in (item.get("top_mudancas") or [])[:3]:
                    if not isinstance(mudanca, dict):
                        continue
                    linhas.append(
                        (
                            f"   ↳ {str(mudanca.get('categoria') or '?')}: "
                            f"{float(mudanca.get('base_pct') or 0):.1f}%→"
                            f"{float(mudanca.get('recente_pct') or 0):.1f}% "
                            f"({float(mudanca.get('delta_pp') or 0):+.1f}pp)"
                        ).replace(".", ",")
                    )

        linhas.extend(
            [
                "",
                "ℹ️ PSI/distância <0,10 = estável; 0,10–0,25 = moderado; ≥0,25 = alto.",
                "⚠️ Drift não significa automaticamente que o modelo piorou; indica mudança na distribuição dos dados.",
            ]
        )
        return "\n".join(linhas)

    def _executar_lab_top5(self):
        if not self.research_lab.configurado:
            return "🧪 RESEARCH LAB\n\n⚪ Ainda não está configurado no Railway."
        dados = self.research_lab.status()
        report = dados.get("report") if isinstance(dados.get("report"), dict) else None
        if not report:
            return "🏅 RESEARCH LAB — TOP5\n\n⏳ Ainda não existe relatório concluído."

        champion = report.get("champion") if isinstance(report.get("champion"), dict) else {}
        champ_hist = champion.get("top5") if isinstance(champion.get("top5"), dict) else {}
        linhas = [
            "🏅 RESEARCH LAB — TOP5 OOS",
            "🔒 Comparação apenas fora da amostra",
            "",
        ]
        if champ_hist.get("brier") is not None:
            linhas.append(
                (
                    f"🏆 Champion V1.2 histórico Top5: n={int(champ_hist.get('n') or 0)} | "
                    f"Brier {float(champ_hist['brier']):.4f} | "
                    f"Gap {float(champ_hist.get('gap_pp') or 0):+.1f}pp"
                ).replace(".", ",")
            )

        challengers = report.get("challengers") if isinstance(report.get("challengers"), dict) else {}
        linhas.extend(["", "🧪 CHALLENGERS — MESMA COORTE TOP5"])
        for nome, item in challengers.items():
            if not isinstance(item, dict):
                continue
            cc = item.get("top5_champion") if isinstance(item.get("top5_champion"), dict) else {}
            ch = item.get("top5_challenger") if isinstance(item.get("top5_challenger"), dict) else {}
            n = int(item.get("top5_oos_n") or ch.get("n") or 0)
            if ch.get("brier") is None or cc.get("brier") is None:
                linhas.append(f"• {nome}: Top5 OOS n={n} | amostra insuficiente")
                continue

            delta = item.get("top5_delta_brier")
            if delta is None:
                delta = float(ch["brier"]) - float(cc["brier"])
            delta = float(delta)
            boot = item.get("top5_bootstrap_delta_brier") if isinstance(
                item.get("top5_bootstrap_delta_brier"), dict
            ) else {}
            ci_low = boot.get("ci95_low")
            ci_high = boot.get("ci95_high")

            if delta <= -0.005 and ci_high is not None and float(ci_high) < 0:
                sinal = "🟢 melhoria consistente"
            elif delta < 0:
                sinal = "🟡 melhoria pequena/inconclusiva"
            else:
                sinal = "🔴 não melhora o Champion"

            linhas.extend(
                [
                    f"• {nome} — Top5 OOS n={n}",
                    (
                        f"   Champion {float(cc['brier']):.4f} → "
                        f"Challenger {float(ch['brier']):.4f} | Δ {delta:+.4f}"
                    ).replace(".", ","),
                    (
                        f"   Gap challenger {float(ch.get('gap_pp') or 0):+.1f}pp | {sinal}"
                    ).replace(".", ","),
                ]
            )
            if ci_low is not None and ci_high is not None:
                linhas.append(
                    (
                        f"   Bootstrap 95% Δ Brier: "
                        f"[{float(ci_low):+.4f}, {float(ci_high):+.4f}]"
                    ).replace(".", ",")
                )

        linhas.extend(
            [
                "",
                "ℹ️ Δ Brier negativo é melhor; positivo é pior.",
                "🛡️ Estes resultados são exploratórios. Não promovem nem alteram V1.2/SEL1.",
            ]
        )
        return "\n".join(linhas)

    def processar_comando(self, chat_id, texto, user_id=None, update_id=None):
        comando_original, _, argumentos = texto.strip().partition(" ")
        comando = comando_original
        if "@" in comando:
            base, alvo = comando.split("@", 1)
            if self.username is None or alvo.lower() != self.username.lower():
                return
            comando = base

        owner_admin = self._e_owner_admin(chat_id, user_id)

        if comando in {"/start", "/ajuda"} and not owner_admin:
            if chat_id != user_id:
                self.enviar_mensagem(
                    chat_id,
                    "🔒 Por privacidade, abre uma conversa privada com o bot e usa /start.",
                )
                return
            if self.owner_id and user_id == self.owner_id:
                resposta = (
                    "🎯 PREMIUM PICKS\n\n"
                    "🟣 Acesso OWNER / ADMIN.\n"
                    "/picks — Ver picks congeladas ainda por começar\n"
                    "/plano — Ver estado do acesso\n"
                    "/id — Ver o teu ID"
                )
                self.enviar_mensagem(chat_id, resposta)
                return
            estado = self.acessos.estado(user_id)
            if estado.get("ativo"):
                resposta = (
                    "🎯 PREMIUM PICKS\n\n"
                    "🟢 Acesso ativo.\n"
                    "/picks — Ver picks congeladas ainda por começar\n"
                    "/plano — Ver validade do acesso\n"
                    "/id — Ver o teu ID"
                )
            else:
                resposta = (
                    "🎯 PREMIUM PICKS\n\n"
                    "🔴 Acesso Premium não ativo.\n"
                    f"🆔 O teu ID é: {user_id}\n\n"
                    "Envia este ID ao responsável do serviço para ativação."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando in {"/picks", "/plano"}:
            if not self._cliente_ativo(chat_id, user_id):
                self.enviar_mensagem(
                    chat_id,
                    "🔒 Acesso Premium inativo. Usa /start para veres o teu ID.",
                )
                return
            try:
                resposta = (
                    self._executar_picks_cliente()
                    if comando == "/picks"
                    else self._executar_plano(user_id)
                )
            except (ValueError, TypeError, KeyError, ArithmeticError):
                resposta = (
                    "Não foi possível gerar esta área Premium neste momento. "
                    "O histórico e o modelo não foram alterados."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando == "/modelo_lab":
            if not owner_admin:
                return
            try:
                resposta = self.previsoes.relatorio_modelo_lab()
            except (ValueError, TypeError, KeyError, ArithmeticError):
                resposta = (
                    "Não foi possível executar o laboratório do modelo. "
                    "O histórico e a V1.2 não foram alterados."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando == "/v13_audit":
            if not owner_admin:
                return
            try:
                resposta = self.previsoes.relatorio_auditoria_v13()
            except (ValueError, TypeError, KeyError, ArithmeticError):
                resposta = (
                    "Não foi possível executar a auditoria V1.3. "
                    "O histórico e a V1.2 não foram alterados."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando == "/v13_shadow":
            if not owner_admin:
                return
            try:
                resposta = self.previsoes.relatorio_v13_shadow()
            except (ValueError, TypeError, KeyError, ArithmeticError):
                resposta = (
                    "Não foi possível executar a V1.3 Shadow. "
                    "O histórico e a V1.2 não foram alterados."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando == "/v13_top5":
            if not owner_admin:
                return
            try:
                resposta = self.previsoes.relatorio_v13_shadow_top5()
            except (ValueError, TypeError, KeyError, ArithmeticError):
                resposta = (
                    "Não foi possível executar a Shadow Top 5. "
                    "O histórico e a V1.2 não foram alterados."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando == "/v13_comercial":
            if not owner_admin:
                return
            try:
                resposta = self._executar_v13_comercial()
            except (ValueError, TypeError, KeyError, ArithmeticError):
                resposta = (
                    "Não foi possível gerar o gate comercial agora. "
                    "A V1.2, a SEL1 e os snapshots não foram alterados."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando in {"/lab_export", "/lab_status", "/lab_drift", "/lab_top5"}:
            if not owner_admin:
                return
            try:
                if comando == "/lab_export":
                    resposta = self._executar_lab_export()
                elif comando == "/lab_status":
                    resposta = self._executar_lab_status()
                elif comando == "/lab_drift":
                    resposta = self._executar_lab_drift()
                else:
                    resposta = self._executar_lab_top5()
            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                ArithmeticError,
                OSError,
            ):
                resposta = (
                    "Não foi possível contactar o Research Lab agora. "
                    "A produção e os snapshots não foram alterados."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando in {"/cliente_add", "/cliente_del", "/clientes"}:
            if not owner_admin:
                return
            try:
                if comando == "/clientes":
                    resposta = self._executar_clientes_admin()
                elif comando == "/cliente_add":
                    partes = argumentos.split()
                    if len(partes) != 2:
                        raise ValueError("Usa /cliente_add USER_ID DIAS")
                    registo = self.acessos.adicionar(int(partes[0]), int(partes[1]))
                    validade = self.acessos.estado(registo["user_id"]).get("validade_ate")
                    resposta = (
                        "✅ CLIENTE PREMIUM ATIVADO\n"
                        f"🆔 {registo['user_id']}\n"
                        f"📅 Válido até: {self._formatar_validade_premium(validade)}"
                    )
                else:
                    partes = argumentos.split()
                    if len(partes) != 1:
                        raise ValueError("Usa /cliente_del USER_ID")
                    removido = self.acessos.remover(int(partes[0]))
                    resposta = (
                        f"✅ Acesso {partes[0]} desativado."
                        if removido
                        else f"ℹ️ Cliente {partes[0]} não estava registado."
                    )
            except (ValueError, TypeError, OSError):
                resposta = (
                    "Formato inválido. Usa /cliente_add USER_ID DIAS, "
                    "/cliente_del USER_ID ou /clientes."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando in {"/carteira", "/carteira_detalhe", "/clv", "/integridade", "/sync_valor"}:
            if not owner_admin:
                return
            try:
                if comando == "/carteira":
                    resposta = self._executar_carteira_shadow()
                elif comando == "/carteira_detalhe":
                    resposta = self._executar_carteira_detalhe(argumentos)
                elif comando == "/clv":
                    resposta = self._executar_clv()
                elif comando == "/integridade":
                    resposta = self._executar_integridade()
                else:
                    resposta = self._executar_sync_valor()
            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                ArithmeticError,
                OSError,
            ):
                resposta = (
                    "Não foi possível gerar a auditoria comercial agora. "
                    "A V1.2, a SEL1 e a odd inicial congelada não foram alteradas."
                )
            self.enviar_mensagem(chat_id, resposta)
            return

        if comando in {"/valor", "/odds_status"}:
            if not owner_admin:
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
                if fonte in {"espn_team_schedules", "cache_espn_equipas"}:
                    equipas = int(diag.get("equipas") or 0)
                    temporada = str(diag.get("temporada") or "-")
                    origem = (
                        "ESPN calendários de equipa"
                        if fonte == "espn_team_schedules"
                        else "ESPN calendários de equipa (cache)"
                    )
                    linhas.append(
                        f"• {codigo}: {jogos} jogos | {origem} | "
                        f"{equipas} equipas | temporada {temporada}"
                    )
                    continue
                if fonte == "sofa_e_espn_equipas_indisponiveis":
                    motivo = str(diag.get("motivo") or "sem detalhe")
                    linhas.append(
                        f"• {codigo}: 0 jogos | fontes históricas indisponíveis | {motivo}"
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
