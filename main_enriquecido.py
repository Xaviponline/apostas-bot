"""Arranque de produção com enriquecimento de competições ESPN.

Mantém o modelo V1 e os seus filtros intactos. A única função desta camada é
combinar a listagem global da ESPN com endpoints específicos de competições
conhecidas para guardar um código de liga fiável (ex.: uefa.europa, esp.1).
O histórico usa ainda uma recolha resiliente por blocos quando a ESPN rejeita
uma janela longa de datas.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging
import requests

from analisador_inteligente import AnalisadorInteligente
from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_espn import EstatisticasESPN
from estatisticas_espn_resiliente import EstatisticasESPNResiliente
from main_diario import BotPremiumDiario, RegistoPrevisoesDiario, TZ_PORTUGAL
from main_sofascore import AJUDA
from nomes_ligas import nome_liga_pt


class BuscadorJogosEnriquecido(BuscadorJogosReais):
    """Preserva todos os jogos globais e enriquece os que têm código conhecido."""

    EXTRA_ESPN_LEAGUES = (
        "eng.fa",
        "eng.league_cup",
        "esp.copa_del_rey",
        "ger.dfb_pokal",
        "ita.coppa_italia",
        "fra.coupe_de_france",
        "por.taca.portugal",
        "ned.cup",
        "sco.tennents",
        "sco.cis",
        "bra.copa_do_brazil",
        "arg.copa",
    )
    ESPN_LEAGUES = BuscadorJogosReais.ESPN_LEAGUES + EXTRA_ESPN_LEAGUES

    ESPN_CODIGO_NOME = {
        "eng.1": "English Premier League",
        "eng.2": "English League Championship",
        "eng.3": "English League One",
        "eng.4": "English League Two",
        "eng.fa": "English FA Cup",
        "eng.league_cup": "English Carabao Cup",
        "esp.1": "Spanish LaLiga",
        "esp.2": "Spanish LaLiga 2",
        "esp.copa_del_rey": "Spanish Copa del Rey",
        "ita.1": "Italian Serie A",
        "ita.2": "Italian Serie B",
        "ita.coppa_italia": "Italian Coppa Italia",
        "ger.1": "German Bundesliga",
        "ger.2": "German 2. Bundesliga",
        "ger.dfb_pokal": "German DFB-Pokal",
        "fra.1": "French Ligue 1",
        "fra.2": "French Ligue 2",
        "fra.coupe_de_france": "French Coupe de France",
        "por.1": "Portuguese Primeira Liga",
        "por.taca.portugal": "Portuguese Taca de Portugal",
        "ned.1": "Eredivisie",
        "ned.2": "Keuken Kampioen Divisie",
        "ned.cup": "Dutch KNVB Beker",
        "bel.1": "Belgian Pro League",
        "tur.1": "Turkish Super Lig",
        "sco.1": "Scottish Premiership",
        "sco.2": "Scottish Championship",
        "sco.tennents": "Scottish Cup",
        "sco.cis": "Scottish League Cup",
        "aut.1": "Austrian Bundesliga",
        "den.1": "Danish Superliga",
        "gre.1": "Greek Super League",
        "sui.1": "Swiss Super League",
        "swe.1": "Allsvenskan",
        "nor.1": "Eliteserien",
        "uefa.champions": "UEFA Champions League",
        "uefa.europa": "UEFA Europa League",
        "uefa.europa.conf": "UEFA Conference League",
        "uefa.nations": "UEFA Nations League",
        "fifa.world": "FIFA World Cup",
        "usa.1": "Major League Soccer",
        "bra.1": "Brasileiro Serie A",
        "bra.2": "Brasileiro Serie B",
        "bra.copa_do_brazil": "Brazilian Copa do Brasil",
        "arg.1": "Argentine Liga Profesional",
        "arg.copa": "Argentine Copa Argentina",
    }

    def _normalizar_evento_com_codigo(self, evento, codigo):
        jogo = super()._normalizar_evento_espn(evento)
        if jogo is None:
            return None
        nome = self.ESPN_CODIGO_NOME.get(str(codigo or ""))
        if nome:
            jogo["league_code"] = str(codigo)
            jogo["liga"] = nome
        return jogo

    def _buscar_espn(self, data_iso):
        """Combina /all com endpoints específicos; os específicos enriquecem metadados."""
        data_compacta = data_iso.replace("-", "")
        self.espn_http_status = None
        self._espn_respondeu = False

        por_id = {}
        erro_global = None
        consultas_validas = 0

        try:
            eventos = self._get_espn("all", data_compacta)
            consultas_validas += 1
            for jogo in self._normalizar_lista_espn(eventos):
                por_id[jogo["id"]] = jogo
        except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
            erro_global = exc

        # A rota /all é ótima para cobertura, mas pode devolver apenas a fase da
        # prova. Consultas específicas, em paralelo, servem só para enriquecer os
        # mesmos event_id com o código real da competição.
        def carregar(codigo):
            return codigo, self._get_espn(codigo, data_compacta)

        with ThreadPoolExecutor(max_workers=min(6, len(self.ESPN_LEAGUES))) as executor:
            futuros = {executor.submit(carregar, codigo): codigo for codigo in self.ESPN_LEAGUES}
            for futuro in as_completed(futuros):
                codigo = futuros[futuro]
                try:
                    _, eventos = futuro.result()
                except (requests.RequestException, RuntimeError, ValueError, TypeError):
                    continue
                consultas_validas += 1
                for evento in eventos:
                    jogo = self._normalizar_evento_com_codigo(evento, codigo)
                    if jogo is not None:
                        por_id[jogo["id"]] = jogo

        if por_id:
            return list(por_id.values())
        if consultas_validas > 0:
            self._espn_respondeu = True
            return []
        if erro_global is not None:
            raise ValueError("Fonte ESPN indisponível.") from None
        return []


class EstatisticasESPNEnriquecidas(EstatisticasESPNResiliente):
    EXTRA_CODIGOS = set(BuscadorJogosEnriquecido.EXTRA_ESPN_LEAGUES)
    EXTRA_NOMES = {
        "english fa cup": "eng.fa",
        "english carabao cup": "eng.league_cup",
        "english league cup": "eng.league_cup",
        "spanish copa del rey": "esp.copa_del_rey",
        "german dfb-pokal": "ger.dfb_pokal",
        "german cup": "ger.dfb_pokal",
        "italian coppa italia": "ita.coppa_italia",
        "french coupe de france": "fra.coupe_de_france",
        "portuguese taca de portugal": "por.taca.portugal",
        "dutch knvb beker": "ned.cup",
        "scottish cup": "sco.tennents",
        "scottish league cup": "sco.cis",
        "brazilian copa do brasil": "bra.copa_do_brazil",
        "argentine copa argentina": "arg.copa",
    }
    EXTRA_SLUGS = (
        ("english-fa-cup", "eng.fa"),
        ("english-carabao-cup", "eng.league_cup"),
        ("english-league-cup", "eng.league_cup"),
        ("spanish-copa-del-rey", "esp.copa_del_rey"),
        ("german-dfb-pokal", "ger.dfb_pokal"),
        ("italian-coppa-italia", "ita.coppa_italia"),
        ("french-coupe-de-france", "fra.coupe_de_france"),
        ("portuguese-taca-de-portugal", "por.taca.portugal"),
        ("dutch-knvb-beker", "ned.cup"),
        ("scottish-league-cup", "sco.cis"),
        ("scottish-cup", "sco.tennents"),
        ("brazilian-copa-do-brasil", "bra.copa_do_brazil"),
        ("copa-argentina", "arg.copa"),
    )

    @staticmethod
    def resolver_liga(jogo):
        jogo = jogo or {}
        codigo = str(jogo.get("league_code") or "").strip()
        suportados = set(EstatisticasESPN.LIGAS.values()) | EstatisticasESPNEnriquecidas.EXTRA_CODIGOS
        if codigo in suportados:
            return codigo

        slug = str(jogo.get("season_slug") or "").lower().strip()
        for trecho, codigo_extra in EstatisticasESPNEnriquecidas.EXTRA_SLUGS:
            if trecho in slug:
                return codigo_extra

        nome = " ".join(str(jogo.get("liga") or "").lower().split())
        extra = EstatisticasESPNEnriquecidas.EXTRA_NOMES.get(nome)
        if extra:
            return extra
        return EstatisticasESPN.resolver_liga(jogo)


class AnalisadorInteligenteEnriquecido(AnalisadorInteligente):
    EXTRA_BANDEIRAS = {
        "english fa cup": "🇬🇧",
        "english carabao cup": "🇬🇧",
        "english league cup": "🇬🇧",
        "spanish copa del rey": "🇪🇸",
        "german dfb-pokal": "🇩🇪",
        "german cup": "🇩🇪",
        "italian coppa italia": "🇮🇹",
        "french coupe de france": "🇫🇷",
        "portuguese taca de portugal": "🇵🇹",
        "dutch knvb beker": "🇳🇱",
        "scottish cup": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "scottish league cup": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "brazilian copa do brasil": "🇧🇷",
        "argentine copa argentina": "🇦🇷",
    }

    @classmethod
    def _bandeira_liga(cls, liga):
        # Correspondência exata para não confundir, por exemplo,
        # Russian Premier League com a Premier League inglesa.
        nome = " ".join(str(liga or "").lower().split())
        if nome in cls.EXTRA_BANDEIRAS:
            return cls.EXTRA_BANDEIRAS[nome]
        return cls.BANDEIRAS.get(nome, "🌍")


class BotPremiumDiarioDiagnostico(BotPremiumDiario):
    def _diagnostico_zero(
        self,
        total_jogos,
        total_futuros,
        total_suportados,
        resumo_novo,
        selecoes_novas,
        fora_cobertura=None,
        historico_indisponivel=None,
        jogos_historico_indisponivel=0,
    ):
        base = super()._diagnostico_zero(
            total_jogos,
            total_futuros,
            total_suportados,
            resumo_novo,
            selecoes_novas,
            fora_cobertura,
            historico_indisponivel,
            jogos_historico_indisponivel,
        )
        erros = dict(self.analisador.estatisticas.ultimo_erros or {})
        if not erros:
            return base
        detalhes = ", ".join(
            f"{codigo}: {str(motivo or 'indisponível')}"
            for codigo, motivo in sorted(erros.items())
        )
        return base + "\n🔎 Motivo técnico: " + detalhes

    def _executar_cobertura(self):
        """Diagnóstico por competição sem guardar ou alterar previsões."""
        agora = datetime.now(TZ_PORTUGAL)
        agora_ts = agora.timestamp()
        jogos = self._jogos_hoje_portugal()
        if not jogos:
            limite = int(getattr(self.analisador, "MAX_SELECOES", 15) or 15)
            estado = str(getattr(self.buscador, "estado", "desconhecido") or "desconhecido")
            fonte = str(getattr(self.buscador, "fonte", "") or "sem fonte confirmada")
            espn_http = getattr(self.buscador, "espn_http_status", None)
            sofa_http = getattr(self.buscador, "sofa_http_status", None)
            diagnostico = [f"estado {estado}", f"fonte {fonte}"]
            if espn_http is not None:
                diagnostico.append(f"ESPN HTTP {espn_http}")
            if sofa_http is not None:
                diagnostico.append(f"SofaScore HTTP {sofa_http}")
            return "\n".join(
                [
                    f"🧭 COBERTURA V1 — {agora.strftime('%d/%m/%Y')}",
                    "📚 Jogos do dia: 0 | Ainda por começar: 0",
                    "",
                    "⚠️ A listagem de jogos veio vazia mesmo após a repetição automática.",
                    "🔎 " + " | ".join(diagnostico),
                    f"🎯 Limite configurado: {limite} seleções",
                    "ℹ️ Não foram gravadas previsões nem alterado o modelo.",
                ]
            )

        futuros = [
            j for j in jogos
            if isinstance(j, dict)
            and isinstance(j.get("timestamp"), (int, float))
            and float(j["timestamp"]) > agora_ts
        ]

        resolver = self.analisador.estatisticas.resolver_liga
        suportados = [j for j in futuros if resolver(j) is not None]
        historicos = (
            self.analisador.estatisticas.carregar_historicos(suportados)
            if suportados else {}
        )

        por_liga = {}
        candidatos = []
        for jogo in futuros:
            original = str(jogo.get("liga") or "Competição").strip() or "Competição"
            nome = nome_liga_pt(original)
            chave = (nome, original)
            linha = por_liga.setdefault(
                chave,
                {"encontrados": 0, "cobertura": 0, "dados": 0, "selecao": 0},
            )
            linha["encontrados"] += 1

            codigo = resolver(jogo)
            if codigo is None:
                continue
            linha["cobertura"] += 1

            analise = self.analisador.estatisticas.analisar_jogo(
                jogo, historicos.get(codigo) or []
            )
            if analise is None:
                continue
            linha["dados"] += 1

            melhor = self.analisador._melhor_selecao(analise)
            if melhor is not None:
                candidatos.append((chave, melhor))

        candidatos.sort(
            key=lambda item: (item[1]["score"], item[1]["qualidade"]),
            reverse=True,
        )
        limite = int(getattr(self.analisador, "MAX_SELECOES", 15) or 15)
        for chave, _ in candidatos[:limite]:
            por_liga[chave]["selecao"] += 1

        total_cobertura = sum(v["cobertura"] for v in por_liga.values())
        total_dados = sum(v["dados"] for v in por_liga.values())
        total_selecao = sum(v["selecao"] for v in por_liga.values())
        fora = max(len(futuros) - total_cobertura, 0)

        linhas = [
            f"🧭 COBERTURA V1 — {agora.strftime('%d/%m/%Y')}",
            f"📚 Jogos do dia: {len(jogos)} | Ainda por começar: {len(futuros)}",
            "",
            "Formato: encontrados → cobertura → dados → seleção",
        ]

        ordenadas = sorted(
            por_liga.items(),
            key=lambda item: (-item[1]["encontrados"], item[0][0].casefold()),
        )
        for (nome, original), valores in ordenadas:
            bandeira = self.analisador._bandeira_liga(original)
            estado = "" if valores["cobertura"] else "  ⛔ fora V1"
            linhas.append(
                f"• {bandeira} {nome}: {valores['encontrados']} → "
                f"{valores['cobertura']} → {valores['dados']} → "
                f"{valores['selecao']}{estado}"
            )

        linhas.extend(
            [
                "",
                f"✅ Dentro da cobertura: {total_cobertura} | 🌍 Fora: {fora}",
                f"🧪 Com dados suficientes: {total_dados}",
                f"🎯 Seleção atual: {total_selecao}/{limite} máximo",
                "ℹ️ Este comando é diagnóstico: não grava previsões nem altera o V1.",
            ]
        )
        erros = dict(self.analisador.estatisticas.ultimo_erros or {})
        if erros:
            linhas.append(
                "⚠️ Histórico indisponível: "
                + ", ".join(sorted(str(codigo) for codigo in erros))
            )
        return "\n".join(linhas)

    def processar_comando(self, chat_id, texto, user_id=None, update_id=None):
        comando_original = texto.strip().partition(" ")[0]
        comando = comando_original
        if "@" in comando:
            comando, alvo = comando.split("@", 1)
            if self.username is None or alvo.lower() != self.username.lower():
                return

        if comando not in ("/cobertura", "/start", "/ajuda"):
            return super().processar_comando(chat_id, texto, user_id, update_id)

        if not self.owner_id or not self.chat_id or chat_id != self.chat_id or user_id != self.owner_id:
            return

        if comando in ("/start", "/ajuda"):
            ajuda = AJUDA.replace(
                "/performance — Liquidar previsões passadas e mostrar auditoria do modelo",
                "/cobertura — Ver onde os jogos passam ou ficam pelos filtros do V1\n"
                "/performance — Liquidar previsões passadas e mostrar auditoria do modelo",
                1,
            )
            self.enviar_mensagem(chat_id, ajuda)
            return

        try:
            resposta = self._executar_cobertura()
        except (requests.RequestException, RuntimeError, ValueError, TypeError):
            resposta = (
                "Não foi possível gerar a cobertura neste momento. "
                "As previsões e o histórico não foram alterados."
            )
        self.enviar_mensagem(chat_id, resposta)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        buscador = BuscadorJogosEnriquecido()
        estatisticas = EstatisticasESPNEnriquecidas()
        analisador = AnalisadorInteligenteEnriquecido(
            buscador_jogos=buscador,
            estatisticas=estatisticas,
        )
        BotPremiumDiarioDiagnostico(
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
