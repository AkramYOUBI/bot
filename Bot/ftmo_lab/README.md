# ftmo_lab — labo de backtest FTMO (Docker)

Recherche qui a produit `Bot/FTMOPortfolio.mq5`.

## Lancer
```bash
cd Bot/ftmo_lab
sh download.sh / download2.sh / download3.sh   # (via docker node, voir commandes dans les fichiers) donnees Dukascopy H1
docker compose build
docker compose run --rm lab python final_report.py      # rapport complet -> out/rapport_ftmo_portfolio.txt
docker compose run --rm lab python research5.py grid ftmo   # grille de risque
```
Telechargement des donnees (une fois) :
```bash
docker run --rm -v "$PWD/data":/data -v "$PWD/download.sh":/d.sh node:20-alpine sh /d.sh
docker run --rm -v "$PWD/data":/data -v "$PWD/download_ask.sh":/d.sh node:20-alpine sh /d.sh
docker run --rm -v "$PWD/data":/data -v "$PWD/download2.sh":/d.sh node:20-alpine sh /d.sh
```

## Fichiers
- `lab/data.py` : chargement H1 bid+ask, jours broker (17h New York), couts, swaps
- `lab/engine.py` : simulation trade (SL prioritaire), compte FTMO (numba) : -5 %/jour, -10 %, objectif, 4 jours
- `lab/strategies.py` : toutes les strategies testees
- `lab/portfolio.py` : challenge 2-Step sur departs glissants hebdo + compte finance
- `lab/research1..5.py` : etapes de recherche ; `final_report.py` : rapport final + stress tests

## Regles de simulation
- Achat au ask, vente au bid (spread reel Dukascopy) + commission + swap 5 %/an (crypto 20 %/an)
- Conflit SL/TP dans la meme bougie H1 -> SL
- Perte jour mesuree sur le pire point intrabar de toutes les positions en meme temps
- Signal sur bougie D1 cloturee, execution 2h apres la reouverture
