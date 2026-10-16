"""Registo local append-only de metadados OddsPapi observados em chamadas existentes.

Sem consultar o fornecedor, sem credenciais e sem reescrever qualquer snapshot.
Nao constitui confirmacao independente de odds na app Betano.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import os


class RastreioOdds:
    MAX_BYTES = 20 * 1024 * 1024

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    def registar(self, selecoes, operacao="ODDS"):
        if self.path is None:
            return 0
        linhas = []
        agora = datetime.now(timezone.utc).isoformat()
        for s in selecoes or []:
            if not isinstance(s, dict):
                continue
            jogo = s.get("jogo") or {}
            diag = s.get("_odds_diag")
            meta = s.get("_rastreio_odds") or {}
            # Apenas metadados e cotacoes observadas; nunca guardar payload
            # integral da API, credenciais ou identificadores de clientes.
            if not meta and not diag:
                continue
            pistas = s.get("_odds_descoberta")
            pistas = pistas if isinstance(pistas, dict) and pistas.get("versao") == 1 else {}
            resumo_pistas = {}
            if pistas:
                resumo_pistas = {"versao": 1}
                for campo in ("primarios_vistos", "complementares_vistos"):
                    numero = pistas.get(campo)
                    resumo_pistas[campo] = (
                        min(max(numero, 0), 10000)
                        if isinstance(numero, int) and not isinstance(numero, bool)
                        else 0
                    )
                for campo in (
                    "complementar_consultada", "casa_primaria", "fora_primaria",
                    "casa_complementar", "fora_complementar", "par_invertido",
                ):
                    resumo_pistas[campo] = pistas.get(campo) is True
                if pistas.get("saf_testado") is True:
                    resumo_pistas["saf_testado"] = True
                    for campo in (
                        "saf_casa_primaria", "saf_fora_primaria",
                        "saf_casa_complementar", "saf_fora_complementar",
                    ):
                        resumo_pistas[campo] = pistas.get(campo) is True
                    for campo in (
                        "saf_par_primario", "saf_par_complementar",
                        "saf_par_hora_compativel", "saf_par_hora_divergente",
                        "saf_par_hora_desconhecida",
                    ):
                        numero = pistas.get(campo)
                        resumo_pistas[campo] = (
                            min(max(numero, 0), 99)
                            if isinstance(numero, int) and not isinstance(numero, bool)
                            else 0
                        )
            item = {
                "observado_em": agora,
                "operacao": str(operacao or "ODDS")[:32],
                "jogo": f"{jogo.get('casa') or '?'} vs {jogo.get('fora') or '?'}"[:200],
                "event_id_modelo": str(jogo.get("id") or "")[:64],
                "mercado_modelo": str(s.get("mercado") or "")[:80],
                "timestamp_jogo": jogo.get("timestamp"),
                "odd_observada": s.get("odd_real"),
                "diagnostico": str(diag or "")[:64],
                "fonte": str(s.get("odds_fonte") or "")[:80],
                "fixture_id_fonte": str(s.get("odds_event_id") or "")[:64],
                "odds_atualizada_em": str(s.get("odds_atualizada_em") or "")[:64],
                "mercado_id_fonte": str(meta.get("market_id") or "")[:64],
                "mercado_nome_fonte": str(meta.get("market_name") or "")[:120],
                "periodo_fonte": str(meta.get("period") or "")[:60],
                "linha_fonte": meta.get("handicap"),
                "selecao_nome_fonte": str(meta.get("selection_name") or "")[:120],
                "outcome_ref_fonte": str(meta.get("outcome_ref") or "")[:80],
                "bookmaker_changed_at": str(meta.get("bookmakerChangedAt") or "")[:64],
                "market_updated_at": str(meta.get("market_updated_at") or "")[:64],
                "resultado_associacao": str(meta.get("association") or "")[:64],
                "alertas_contexto": list(s.get("_odds_alertas") or [])[:6],
                "descoberta_passiva": resumo_pistas,
            }
            linhas.append((json.dumps(item, ensure_ascii=False, sort_keys=True)+"\n").encode("utf-8"))
        if not linhas:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise RuntimeError("Rastreio nao pode ser symlink")
        anterior = self.path.stat().st_size if self.path.exists() else 0
        bloco = b"".join(linhas)
        if anterior + len(bloco) > self.MAX_BYTES:
            raise RuntimeError("Rastreio atingiu limite de 20 MB; requer arquivo manual")
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as f:
            f.write(bloco)
            f.flush()
            os.fsync(f.fileno())
        return len(linhas)

    def relatorio(self):
        if self.path is None or not self.path.exists():
            return "🔎 RASTREIO ODDS — ainda sem observacoes locais."
        if self.path.is_symlink():
            return "🔎 RASTREIO ODDS — ficheiro inseguro."
        total = com_ref = anomalias = 0
        ultimos = []
        with self.path.open("r", encoding="utf-8") as f:
            for linha in f:
                if not linha.strip():
                    continue
                item = json.loads(linha)
                total += 1
                if item.get("mercado_id_fonte") and item.get("outcome_ref_fonte"):
                    com_ref += 1
                if item.get("diagnostico") or item.get("alertas_contexto"):
                    anomalias += 1
                if item.get("odd_observada") and item.get("mercado_id_fonte"):
                    ultimos.append(item)
                    ultimos = ultimos[-4:]
        linhas = [
            "🔎 RASTREIO ODDS — AUDITORIA LOCAL",
            f"Observacoes: {total}",
            f"Com ID de mercado e referencia de selecao: {com_ref}",
            f"Com diagnostico/alertas: {anomalias}",
            "",
            "ULTIMAS COTACOES COM REFERENCIAS:",
        ]
        for a in reversed(ultimos):
            linhas.append(f"• {a['jogo']} | {a['mercado_modelo']} @{a['odd_observada']}")
            linhas.append(f"  fixture={a['fixture_id_fonte']} | mercado={a['mercado_id_fonte']} | selecao={a['outcome_ref_fonte']}")
        linhas.extend([
            "ℹ️ Metadados observados; nao valida de forma independente a cotacao na Betano.",
            "🔒 Nao altera odds/modelo, nao consulta API e nao guarda chaves.",
        ])
        return "\n".join(linhas)
