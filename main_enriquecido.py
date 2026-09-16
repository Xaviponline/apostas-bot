"""Arranque de produção com enriquecimento de competições ESPN.

Mantém o modelo V1 e os seus filtros intactos. A única função desta camada é
combinar a listagem global da ESPN com endpoints específicos de competições
conhecidas para guardar um código de liga fiável (ex.: uefa.europa, esp.1).
O histórico usa ainda uma recolha resiliente por blocos quando a ESPN rejeita
uma janela longa de datas.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import requests

from analisador_inteligente import AnalisadorInteligente
from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_espn import EstatisticasESPN
from estatisticas_espn_resiliente import EstatisticasESPNResiliente
from main_diario import BotPremiumDiario, RegistoPrevisoesDiario


class BuscadorJogosEnriquecido(BuscadorJogosReais):
    """Preserva todos os jogos globais e enriquece os que têm código conhecido."""

    ESPN_CODIGO_NOME = {
        "eng.1": "English Premier League",
        "esp.1": "Spanish LaLiga",
        "ita.1": "Italian Serie A",
        "ger.1": "German Bundesliga",
        "fra.1": "French Ligue 1",
        "por.1": "Portuguese Primeira Liga",
        "ned.1": "Eredivisie",
        "bel.1": "Belgian Pro League",
        "uefa.champions": "UEFA Champions League",
        "uefa.europa": "UEFA Europa League",
        "uefa.europa.conf": "UEFA Conference League",
        "uefa.nations": "UEFA Nations League",
        "fifa.world": "FIFA World Cup",
        "usa.1": "Major League Soccer",
        "bra.1": "Brasileiro Serie A",
        "arg.1": "Argentine Liga Profesional",
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
    @staticmethod
    def resolver_liga(jogo):
        codigo = str((jogo or {}).get("league_code") or "").strip()
        suportados = set(EstatisticasESPN.LIGAS.values())
        if codigo in suportados:
            return codigo
        return EstatisticasESPN.resolver_liga(jogo)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        buscador = BuscadorJogosEnriquecido()
        estatisticas = EstatisticasESPNEnriquecidas()
        analisador = AnalisadorInteligente(
            buscador_jogos=buscador,
            estatisticas=estatisticas,
        )
        BotPremiumDiario(
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
