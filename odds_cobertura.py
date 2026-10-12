"""Observatorio passivo de cobertura Betano por liga/mercado.

Nao consulta APIs, nao filtra selecoes e nao altera snapshots. Observacoes
repetidas do mesmo evento/mercado contam como uma so unidade estatistica.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from nomes_ligas import nome_liga_pt


TZ_PT = ZoneInfo("Europe/Lisbon")
CATEGORIAS = {
    "odd_confirmada", "betano_sem_odds", "mercado_indisponivel", "incerto"
}
DIAGNOSTICOS_MERCADO = {
    "mercado_nao_disponivel", "linha_ou_selecao_nao_disponivel",
}
# HTTP 400/404, fixtures omitidos, eventos nao associados e rate limits sao
# inconclusivos sobre cobertura comercial. Nunca sao prova de nao cobertura.
DIAGNOSTICOS_BETANO = {"betano_sem_odds_no_evento"}


def _dia_jogo(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone(TZ_PT).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _odd_valida(valor):
    try:
        return float(valor) > 1.0
    except (TypeError, ValueError):
        return False


def _categoria(selecao):
    if _odd_valida(selecao.get("odd_real")):
        return "odd_confirmada"
    diag = str(selecao.get("_odds_diag") or "")
    if diag in DIAGNOSTICOS_BETANO:
        return "betano_sem_odds"
    if diag in DIAGNOSTICOS_MERCADO:
        return "mercado_indisponivel"
    return "incerto"


def _dados_chave(liga, data_iso, event_id, mercado):
    if not liga or not data_iso or event_id is None or str(event_id) == "" or not mercado:
        return None
    dados = json.dumps(
        [str(liga).casefold(), str(data_iso), str(event_id), str(mercado).casefold()],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(dados.encode("utf-8")).hexdigest()


class ObservatorioCobertura:
    MAX_REGISTOS = 4500
    DIAS_RETENCAO = 120

    def __init__(self, path):
        self.path = Path(path)

    def _ler(self):
        if not self.path.exists():
            return {"versao": 1, "observacoes": {}}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Historico de cobertura invalido; nao foi substituido.") from exc
        if not isinstance(dados, dict) or not isinstance(dados.get("observacoes"), dict):
            raise ValueError("Estrutura de cobertura invalida; nao foi substituida.")
        return dados

    def _guardar(self, dados):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix="cobertura_", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, self.path)
        finally:
            if os.path.exists(temporario):
                os.unlink(temporario)

    @staticmethod
    def _normalizar_liga(liga):
        original = str(liga or "").strip()
        return str(nome_liga_pt(original) or original).strip()[:90]

    @classmethod
    def _extrair(cls, selecao):
        jogo = selecao.get("jogo") or {}
        liga = cls._normalizar_liga(jogo.get("liga"))
        mercado = str(selecao.get("mercado") or "").strip()[:80]
        data = _dia_jogo(jogo.get("timestamp"))
        chave = _dados_chave(liga, data, jogo.get("id"), mercado)
        if not chave:
            return None
        return chave, liga, mercado, data, _categoria(selecao)

    def registar(self, selecoes):
        """Grava so resultados de consultas JA realizadas; sem trafego externo."""
        observacoes_novas = []
        for selecao in selecoes or []:
            if not isinstance(selecao, dict):
                continue
            if not (_odd_valida(selecao.get("odd_real")) or selecao.get("_odds_diag")):
                continue
            item = self._extrair(selecao)
            if item:
                observacoes_novas.append(item)
        if not observacoes_novas:
            return 0

        dados = self._ler()
        observacoes = dados["observacoes"]
        agora = datetime.now(timezone.utc).isoformat()
        novas = 0
        for chave, liga, mercado, dia, categoria in observacoes_novas:
            existente = observacoes.get(chave)
            if not isinstance(existente, dict):
                existente = {
                    "liga": liga, "mercado": mercado, "dia": dia,
                    "categorias": [], "primeira_observacao": agora,
                    "tentativas": 0,
                }
                observacoes[chave] = existente
                novas += 1
            categorias = set(existente.get("categorias") or [])
            categorias.add(categoria)
            existente["categorias"] = sorted(categorias & CATEGORIAS)
            existente["ultima_categoria"] = categoria
            existente["ultima_observacao"] = agora
            existente["tentativas"] = min(int(existente.get("tentativas") or 0) + 1, 10000)

        # Retencao de estados agregados, sem guardar nomes de equipas, odds,
        # payloads, tokens ou dados identificaveis do fornecedor.
        limite = (datetime.now(TZ_PT).date() - timedelta(days=self.DIAS_RETENCAO)).isoformat()
        for chave, reg in list(observacoes.items()):
            if not isinstance(reg, dict) or str(reg.get("dia") or "") < limite:
                observacoes.pop(chave, None)
        if len(observacoes) > self.MAX_REGISTOS:
            ordenar = sorted(observacoes, key=lambda k: str(observacoes[k].get("ultima_observacao") or ""))
            for chave in ordenar[:len(observacoes)-self.MAX_REGISTOS]:
                observacoes.pop(chave, None)
        self._guardar(dados)
        return novas

    def _amostras(self, snapshots=None):
        registos = dict(self._ler()["observacoes"])
        confirmacoes_historicas = 0
        for p in snapshots or []:
            if not isinstance(p, dict):
                continue
            fonte = str(p.get("odds_fonte") or "").casefold()
            if "oddspapi" not in fonte:
                continue
            if not _odd_valida(p.get("odd_real")):
                continue
            liga = self._normalizar_liga(p.get("liga"))
            dia = str(p.get("data_jogo") or "")
            mercado = str(p.get("mercado") or "").strip()[:80]
            chave = _dados_chave(liga, dia, p.get("event_id"), mercado)
            if not chave:
                continue
            if chave not in registos:
                registos[chave] = {
                    "liga": liga, "mercado": mercado, "dia": dia,
                    "categorias": ["odd_confirmada"],
                    "tentativas": 0,
                    "origem": "snapshot_historico",
                }
                confirmacoes_historicas += 1
            else:
                categorias = set(registos[chave].get("categorias") or [])
                categorias.add("odd_confirmada")
                registos[chave]["categorias"] = sorted(categorias)
        return registos, confirmacoes_historicas

    def calcular(self, snapshots=None):
        registos, historicas = self._amostras(snapshots)
        grupos = defaultdict(lambda: {"eventos": 0, "confirmados": 0, "betano_sem_odds": 0,
                                    "mercado_indisponivel": 0, "incertos": 0, "dias": set()})
        for reg in registos.values():
            if not isinstance(reg, dict):
                continue
            liga, mercado = str(reg.get("liga") or ""), str(reg.get("mercado") or "")
            dia = str(reg.get("dia") or "")
            if not liga or not mercado or not dia:
                continue
            grupo = grupos[(liga, mercado)]
            grupo["eventos"] += 1
            grupo["dias"].add(dia)
            categorias = set(reg.get("categorias") or [])
            # Se algum dia se confirmou uma odd, o evento tem cobertura
            # observada, mesmo que mais tarde o mercado tenha encerrado.
            if "odd_confirmada" in categorias:
                grupo["confirmados"] += 1
            elif "mercado_indisponivel" in categorias:
                grupo["mercado_indisponivel"] += 1
            elif "betano_sem_odds" in categorias:
                grupo["betano_sem_odds"] += 1
            else:
                grupo["incertos"] += 1

        saida = []
        for (liga, mercado), d in grupos.items():
            n, ok = d["eventos"], d["confirmados"]
            decisivos = d["betano_sem_odds"] + d["mercado_indisponivel"]
            dias = len(d["dias"])
            if ok and decisivos >= 2 and n >= 5 and dias >= 2:
                estado = "PARCIAL OBSERVADA"
            elif ok:
                estado = "OBSERVADA"
            else:
                estado = "NAO CONFIRMADA"
            # Proposta de revisao humana, jamais exclusao automatica.
            rever = bool(n >= 12 and dias >= 3 and ok == 0 and decisivos >= 10)
            saida.append({
                "liga": liga, "mercado": mercado, "eventos": n, "dias": dias,
                "confirmados": ok, "betano_sem_odds": d["betano_sem_odds"],
                "mercado_indisponivel": d["mercado_indisponivel"],
                "incertos": d["incertos"], "estado": estado,
                "candidata_revisao": rever,
            })
        saida.sort(key=lambda g: (-g["eventos"], g["liga"], g["mercado"]))
        return {"grupos": saida, "observacoes_unicas": len(registos),
                "confirmacoes_historicas": historicas}

    def relatorio(self, snapshots=None, limite=18):
        dados = self.calcular(snapshots)
        grupos = dados["grupos"]
        linhas = [
            "🧭 COBERTURA ODDS — BETANO PT",
            "🔎 Observatorio passivo | apenas leitura",
            f"• Eventos/mercados distintos: {dados['observacoes_unicas']}",
            f"• Confirmacoes importadas de snapshots: {dados['confirmacoes_historicas']}",
            f"• Grupos liga/mercado: {len(grupos)}",
            "",
        ]
        if not grupos:
            linhas.extend([
                "Ainda nao existem observacoes locais de cobertura.",
                "A recolha inicia-se apenas com consultas que o bot ja efetuar normalmente.",
            ])
        for d in grupos[:limite]:
            linhas.append(
                f"• {d['liga']} | {d['mercado']}: "
                f"{d['confirmados']}/{d['eventos']} com odd | "
                f"{d['dias']} dia(s) | {d['estado']}"
            )
            if d["candidata_revisao"]:
                linhas.append("  ⚠️ Candidata a revisao manual, sem bloqueio")
            elif d["incertos"]:
                linhas.append(f"  ℹ️ {d['incertos']} inconclusivo(s); HTTP/fixture omitido nao provam falta de cobertura")
        if len(grupos) > limite:
            linhas.append(f"… mais {len(grupos)-limite} grupos nao apresentados.")
        linhas.extend([
            "",
            "⚠️ Amostras limitadas a jogos selecionados, nao a todos os jogos da liga.",
            "Sem odds historicas falhadas antes deste observatorio.",
            "HTTP 400/404 e fixtures omitidos nunca provam falta de cobertura.",
            "🔒 Nao exclui ligas, nao consulta a API e nao altera V1.2, SEL1 ou V1.3.",
        ])
        return "\n".join(linhas)
