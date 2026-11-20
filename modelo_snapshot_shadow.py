"""Consulta exclusivamente local de snapshots imutaveis do modelo.

Sem chamadas externas, sem recalcular probabilidades e sem alterar ficheiros.
"""
import unicodedata


def _normalizar(texto):
    s = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def diagnostico_snapshot(dados, pesquisa):
    termo = str(pesquisa or "").strip()
    if not 3 <= len(termo) <= 80:
        return "🔎 Usa /modelo_snapshot <equipa> (mínimo 3 caracteres)."
    registos = dados.get("previsoes") if isinstance(dados, dict) else None
    if not isinstance(registos, list):
        return "⚠️ Histórico local indisponível."
    encontrados = [
        s for s in registos if isinstance(s, dict)
        and _normalizar(termo) in _normalizar(
            f"{s.get('casa', '')} {s.get('fora', '')} {s.get('event_id', '')}"
        )
    ]
    if not encontrados:
        return "⚪ Sem snapshots locais correspondentes; não é possível reconstruir inputs históricos."
    linhas = [f"🔬 MODELO SNAPSHOT — {termo}", f"📚 Encontrados: {len(encontrados)} | últimos 3"]
    for s in encontrados[-3:][::-1]:
        d = s.get("diagnostico_modelo")
        d = d if isinstance(d, dict) else {}
        def fmt(valor, casas=3):
            try:
                return f"{float(valor):.{casas}f}".replace(".", ",")
            except (TypeError, ValueError, OverflowError):
                return "não registado"
        def inteiro(chave):
            return str(d[chave]) if chave in d else "não registado"
        linhas.extend([
            "",
            f"⚽ {s.get('casa', '?')} vs {s.get('fora', '?')} | {s.get('data_jogo', '?')}",
            f"🎯 {s.get('mercado', '?')} | snapshot #{s.get('id', 'não registado')}",
            f"📈 Prob. conservadora: {fmt(100 * s['probabilidade'], 1) if isinstance(s.get('probabilidade'), (int, float)) else 'não registado'}%",
            f"📊 Prob. bruta: {fmt(100 * s['probabilidade_bruta'], 1) if isinstance(s.get('probabilidade_bruta'), (int, float)) else 'não registado'}%",
            f"🧪 Qualidade: {s.get('qualidade', 'não registada')}",
            f"⚽ Golos esperados: casa {fmt(d.get('lambda_casa'))} | fora {fmt(d.get('lambda_fora'))}",
            f"📚 Amostras totais: casa {inteiro('amostra_casa')} | fora {inteiro('amostra_fora')} | liga {inteiro('amostra_liga')}",
            f"🏟️ Amostras locais: casa {inteiro('amostra_casa_local')} | fora {inteiro('amostra_fora_local')}",
            f"📉 PPG: casa {fmt(d.get('ppg_casa'))} | fora {fmt(d.get('ppg_fora'))}",
            f"💰 Odd inicial: {fmt(s.get('odd_real'), 2)} | EV: {fmt(100 * s['ev_real'], 1) if isinstance(s.get('ev_real'), (int, float)) else 'não registado'}%",
            f"🕒 Snapshot criado: {s.get('criada_em') or 'não registado'}",
        ])
        if not d:
            linhas.append("⚠️ Sem diagnóstico histórico: não inferir inputs em falta.")
    linhas.append("🔒 Apenas leitura local. Não consulta ESPN/OddsPapi nem altera previsões, V1.3 ou CLV.")
    return "\n".join(linhas)
