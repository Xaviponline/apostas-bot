"""Testes independentes da coerência matemática do 1X2 em produção.

Não altera fórmula, seleção ou snapshots.
"""
from math import exp, isclose
from estatisticas_espn import EstatisticasESPN


def _poisson_1x2_independente(lc, lf, limite=45):
    # Soma não truncada na região relevante: controlo independente do
    # truncamento a 10 golos do motor de produção.
    pc = [exp(-lc)]
    pf = [exp(-lf)]
    for i in range(1, limite + 1):
        pc.append(pc[-1]*lc/i)
        pf.append(pf[-1]*lf/i)
    casa = empate = fora = 0.0
    for i, p in enumerate(pc):
        for j, q in enumerate(pf):
            if i > j:
                casa += p*q
            elif i == j:
                empate += p*q
            else:
                fora += p*q
    return casa, empate, fora


def test_probabilidades_1x2_coerentes_em_gama_real():
    for lc, lf in ((.2,.2),(.8,1.3),(1.3,.8),(2.025,3.214),
                   (3.8,.2),(.2,3.8),(3.8,3.8)):
        p = EstatisticasESPN._probabilidades(lc, lf)
        assert p is not None
        assert all(0 <= p[k] <= 1 for k in ("Vitória Casa","Empate","Vitória Fora"))
        assert isclose(sum(p[k] for k in ("Vitória Casa","Empate","Vitória Fora")),1,abs_tol=1e-10)
        assert isclose(p["1X (Casa ou Empate)"],p["Vitória Casa"]+p["Empate"],abs_tol=1e-10)
        assert isclose(p["X2 (Empate ou Fora)"],p["Vitória Fora"]+p["Empate"],abs_tol=1e-10)
        assert isclose(p["Under 2.5 Golos"]+p["Over 2.5 Golos"],1,abs_tol=1e-10)
        assert isclose(p["Under 3.5 Golos"]+p["Over 3.5 Golos"],1,abs_tol=1e-10)
        esperado = _poisson_1x2_independente(lc,lf)
        for nome, alvo in zip(("Vitória Casa","Empate","Vitória Fora"),esperado):
            assert abs(p[nome]-alvo)<0.0001, (lc,lf,nome,p[nome],alvo)


def test_simetria_e_empate():
    for lc,lf in ((.2,3.8),(1.2,1.8),(3.8,3.8)):
        a=EstatisticasESPN._probabilidades(lc,lf)
        b=EstatisticasESPN._probabilidades(lf,lc)
        assert isclose(a["Vitória Casa"],b["Vitória Fora"],abs_tol=1e-10)
        assert isclose(a["Empate"],b["Empate"],abs_tol=1e-10)
