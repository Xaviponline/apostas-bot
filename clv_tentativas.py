"""Auditoria passiva de capturas CLV em ficheiro separado dos snapshots."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile


class DiarioTentativasCLV:
    """Um evento por seleção em cada ciclo. Nunca consulta a fonte de odds."""

    MOTIVOS = frozenset({
        "evento_nao_encontrado", "evento_ambiguo", "evento_sem_id",
        "mercado_nao_disponivel", "linha_ou_selecao_nao_disponivel",
        "betano_sem_odds_no_evento", "odds_evento_indisponiveis",
        "mercado_ambiguo", "odds_payload_evento_divergente",
        "horario_recuperacao_nao_validado", "probabilidade_invalida",
        "odds_http_400", "odds_http_404", "odds_http_429",
        "odds_rate_limit_429", "odds_quota_esgotada",
    })

    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def para_previsoes(cls, previsoes):
        path = getattr(previsoes, "path", None)
        return cls(Path(path).with_name("clv_tentativas.json")) if path else None

    def _ler(self):
        if self.path.is_symlink():
            raise RuntimeError("Ficheiro de auditoria inseguro")
        if not self.path.exists():
            return {"versao": 1, "eventos": []}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Auditoria inválida; não sobrescrever") from exc
        if (not isinstance(dados, dict) or dados.get("versao") != 1
                or not isinstance(dados.get("eventos"), list)
                or any(not isinstance(e, dict) for e in dados["eventos"])):
            raise RuntimeError("Auditoria inválida; não sobrescrever")
        return dados

    def _guardar(self, dados):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise RuntimeError("Ficheiro de auditoria inseguro")
        fd, temp = tempfile.mkstemp(prefix=".clv_", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def registar(self, previsoes, selecoes, estado, enriquecidas=None, agora=None):
        """Regista só factos do ciclo já executado; sem consulta adicional.

        Um diagnóstico desconhecido nunca é transformado em causa certa.
        """
        if estado not in {"consulta_concluida", "quota_nao_autorizou", "consulta_interrompida"}:
            raise ValueError("Estado de captura não reconhecido")
        agora = agora or datetime.now(timezone.utc)
        if agora.tzinfo is None:
            raise ValueError("Hora UTC inválida")
        instante = agora.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        indices = {
            (str(p.get("event_id")), str(p.get("mercado"))): (i, p)
            for i, p in enumerate(previsoes.dados.get("previsoes", []), 1)
        }
        extras = {
            (str((s.get("jogo") or {}).get("id")), str(s.get("mercado"))): s
            for s in (enriquecidas or [])
        }
        eventos = []
        for s in (selecoes or []):
            chave = (str((s.get("jogo") or {}).get("id")), str(s.get("mercado")))
            if chave not in indices:
                continue
            indice, previsao = indices[chave]
            enriquecida = extras.get(chave) or {}
            if estado != "consulta_concluida":
                resultado, motivo = "sem_fecho", estado
            elif previsoes._odd_real_valida(previsao.get("odd_fecho")) is not None:
                resultado, motivo = "fecho_capturado", "fecho_persistido"
            else:
                resultado = "sem_fecho"
                codigo = str(enriquecida.get("_odds_diag") or "")
                if codigo in self.MOTIVOS:
                    motivo = codigo
                elif enriquecida.get("odd_real") is not None:
                    motivo = "cotacao_sem_fecho_persistido"
                else:
                    motivo = "motivo_nao_confirmado"
            eventos.append({
                "snapshot": indice,
                "data_jogo": str(previsao.get("data_jogo") or ""),
                "registado_em": instante,
                "resultado": resultado,
                "motivo": motivo,
            })
        if not eventos:
            return 0
        dados = self._ler()
        dados["eventos"].extend(eventos)
        self._guardar(dados)
        return len(eventos)

    def por_snapshot(self):
        """Contagens e última observação; histórico vazio ≠ ausência de tentativa."""
        resumo = {}
        for e in self._ler()["eventos"]:
            try:
                indice = int(e.get("snapshot"))
            except (ValueError, TypeError):
                continue
            if indice < 1:
                continue
            item = resumo.setdefault(indice, {"tentativas": 0, "ultima": None})
            item["tentativas"] += 1
            item["ultima"] = e
        return resumo
