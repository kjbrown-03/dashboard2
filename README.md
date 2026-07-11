# Dashboard KPI Python

Application Dash pour piloter les KPI Moto et Taxi: financier, operationnel, social, fintech, discipline, KPI hebdo et rapports par vehicule.

## Lancer

```powershell
python app.py
```

Puis ouvrir:

```text
http://127.0.0.1:8060
```

Le dashboard Taxi est lance automatiquement en local sur:

```text
http://127.0.0.1:8061
```

Depuis une autre machine du meme reseau, utiliser l'adresse IP du PC:

```text
http://ADRESSE_IP_DU_PC:8060
```

## Notes

- Les donnees actuelles sont des donnees d'exemple generees dans `app.py`.
- Modele Moto: `assets/modele_kpi_moto_par_frequence.xlsx`.
- Modele Taxi: `dashboard2.1/assets/modele_kpi_taxi_par_frequence.xlsx`.
- Les fichiers Excel sont organises par frequence: `Quotidien`, `Hebdomadaire`, `Mensuel`, plus un `Guide Frequences`.
- Chaque dashboard importe son propre fichier Excel.
- Les KPI mensuels comparent le mois choisi avec le mois precedent.
- Les KPI hebdomadaires comparent la semaine choisie avec la semaine precedente.
- Pour un indicateur mensuel, le filtre semaine est desactive.
- Le KPI Hebdo reprend les indicateurs essentiels des autres blocs: performance hebdomadaire, retards, PAR 7, taux de motos actives et visites terrain.

## Deployer sur Vercel

1. Envoyer ce dossier sur GitHub.
2. Sur Vercel: `Add New Project`, puis importer le repo GitHub.
3. Framework preset: `Other`.
4. Build command: laisser vide.
5. Output directory: laisser vide.
6. Ajouter une base Postgres serverless via Vercel Marketplace, par exemple Neon.
7. Dans les variables d'environnement Vercel, verifier que `DATABASE_URL` existe.
8. Deployer.

Routes apres deploiement:

```text
https://votre-projet.vercel.app/
https://votre-projet.vercel.app/taxi/
```

Sans `DATABASE_URL`, les imports Excel fonctionnent pendant la session serveur, mais ne sont pas persistants. Avec `DATABASE_URL`, le dernier import Moto et le dernier import Taxi sont sauvegardes dans la table `dashboard_imports`.
