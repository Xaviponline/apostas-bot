"""Sondagem READ-ONLY e limitada: ESPN aceita datas isoladas onde ranges dão 400?

Apenas imprime status HTTP e contagem de eventos, sem previsões nem persistência.
Não é usada para inferir métricas de cobertura.
"""
import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
PROVAS = ("uefa.champions", "por.taca.portugal")
CONSULTAS = ("20261014", "20260916", "20260901-20260914")


def main():
    session = requests.Session()
    for prova in PROVAS:
        for data in CONSULTAS:
            try:
                r = session.get(
                    f"{BASE}/{prova}/scoreboard",
                    params={"dates": data, "limit": 500},
                    timeout=(5, 12),
                )
                eventos = r.json().get("events") if r.status_code == 200 else None
                total = len(eventos) if isinstance(eventos, list) else "n/a"
                print(f"ESPN {prova}: dates={data} HTTP={r.status_code} eventos={total}")
            except (requests.RequestException, ValueError, TypeError):
                print(f"ESPN {prova}: dates={data} indisponível")


if __name__ == "__main__":
    main()
