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
