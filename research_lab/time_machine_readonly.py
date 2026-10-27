"""Consulta SOMENTE LEITURA do último dataset Research Lab.

Executar no ambiente do research-lab (com variáveis LAB_S3_* existentes):
    python -m research_lab.time_machine_readonly

Não grava ficheiros, não chama /run e não modifica modelos.
Nunca imprime credenciais ou previsões individuais.
"""
from __future__ import annotations

import json

from .config import LabConfig
from .storage import LabStorage
from time_machine_auditoria_shadow import auditar


def resumo_ultimo_dataset():
    config = LabConfig.from_env()
    if not config.s3_configurado:
        raise RuntimeError("S3 do Research Lab não configurado: abortado sem fallback local")
    payload = LabStorage(config).get_json("datasets/latest.json", default=None)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise RuntimeError("Dataset latest.json não encontrado ou inválido")
    resultado = auditar(payload["records"])
    resultado["records_count_declarado"] = payload.get("records_count")
    resultado["contagem_consistente"] = resultado["registos"] == payload.get("records_count")
    resultado["nota_jogos_unicos"] = (
        "Não contabilizados: exige identidade estável do fixture para deduplicar."
    )
    return resultado


if __name__ == "__main__":
    print(json.dumps(resumo_ultimo_dataset(), ensure_ascii=False, indent=2))
