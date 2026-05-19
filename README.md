# Dashboard KPI Python

Application Dash pour piloter les KPI financiers, operationnels, sociaux, fintech, risques, suivi terrain et KPI hebdomadaires.

## Lancer

```powershell
python app.py
```

Puis ouvrir:

```text
http://127.0.0.1:8060
```

Depuis une autre machine du meme reseau, utiliser l'adresse IP du PC:

```text
http://ADRESSE_IP_DU_PC:8060
```

## Notes

- Les donnees actuelles sont des donnees d'exemple generees dans `app.py`.
- Pour importer vos propres donnees, remplir `assets/data_template.xlsx`, puis cliquer sur `Importer Excel` dans l'application.
- Les KPI mensuels comparent le mois choisi avec le mois precedent.
- Les KPI hebdomadaires comparent la semaine choisie avec la semaine precedente.
- Pour un indicateur mensuel, le filtre semaine est desactive.
- Le KPI Hebdo reprend les indicateurs essentiels des autres blocs: performance hebdomadaire, retards, PAR 7, taux de motos actives et visites terrain.
