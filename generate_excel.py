from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.offsets import MonthBegin


ROOT = Path(__file__).resolve().parent


def generate_excel(file_path: str | Path, vehicle: str = "moto", is_mock: bool = False) -> None:
    vehicle = vehicle.lower()
    if vehicle not in {"moto", "taxi"}:
        raise ValueError("vehicle doit etre 'moto' ou 'taxi'")

    is_taxi = vehicle == "taxi"
    vehicle_label = "voiture" if is_taxi else "moto"
    vehicle_label_plural = "voitures" if is_taxi else "motos"
    vehicle_id_col = "voiture_id" if is_taxi else "moto_id"
    vehicle_id_title = "voiture_id" if is_taxi else "moto_id"
    vehicle_prefix = "VOITURE" if is_taxi else "MOTO"
    active_col = "voitures_actives" if is_taxi else "motos_actives"
    total_col = "total_voitures" if is_taxi else "total_motos"
    panne_col = "voitures_panne" if is_taxi else "motos_panne"

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42 if not is_taxi else 84)
    today = pd.Timestamp.today().normalize()
    previous_month_start = today.replace(day=1) - MonthBegin(1)
    dates = pd.date_range(start=previous_month_start, end=today, freq="D")
    weeks = pd.date_range(start=previous_month_start, end=today, freq="W-MON")
    if len(weeks) == 0 or weeks[-1] < today:
        weeks = weeks.append(pd.DatetimeIndex([today]))
    months = pd.date_range(start=previous_month_start, end=today.replace(day=1), freq="MS")

    def values(base: float, var: float, count: int, as_int: bool = False):
        if not is_mock:
            return [None] * count
        arr = np.maximum(0, rng.normal(base, var, count))
        return np.round(arr).astype(int).tolist() if as_int else arr.tolist()

    def ids(count: int = 20) -> list[str]:
        return [f"{vehicle_prefix}-{1001 + i}" for i in range(count)]

    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        wb = writer.book
        header_input = wb.add_format({"bold": True, "bg_color": "#BDD7EE", "border": 1, "text_wrap": True, "valign": "vcenter", "font_size": 10})
        header_calc = wb.add_format({"bold": True, "bg_color": "#E2EFDA", "border": 1, "text_wrap": True, "valign": "vcenter", "font_size": 10, "italic": True})
        input_fmt = wb.add_format({"border": 1, "num_format": "#,##0", "bg_color": "#FFFFFF"})
        text_fmt = wb.add_format({"border": 1, "bg_color": "#FFFFFF"})
        input_date = wb.add_format({"border": 1, "num_format": "yyyy-mm-dd", "bg_color": "#FFFFFF"})
        pct_fmt = wb.add_format({"border": 1, "num_format": "0.00%", "bg_color": "#F4FFEC", "italic": True})
        calc_num = wb.add_format({"border": 1, "num_format": "#,##0", "bg_color": "#F4FFEC", "italic": True})
        note_fmt = wb.add_format({"bg_color": "#FFF2CC", "border": 1, "text_wrap": True, "bold": True, "font_size": 9, "valign": "vcenter"})
        title_fmt = wb.add_format({"bold": True, "font_size": 12, "bg_color": "#17663A", "font_color": "#FFFFFF", "border": 1, "valign": "vcenter"})

        def write_table(sheet: str, title: str, rows: list[dict], columns: list[tuple[str, str, int]], formulas: list[tuple[str, str, str]] | None = None) -> None:
            formulas = formulas or []
            ws = wb.add_worksheet(sheet)
            writer.sheets[sheet] = ws
            last_col = max(0, len(columns) + len(formulas) - 1)
            ws.merge_range(0, 0, 0, last_col, title, title_fmt)
            ws.merge_range(
                1,
                0,
                1,
                last_col,
                "Feuille organisee par frequence. Colonnes BLEUES = donnees a saisir. Colonnes VERTES = indicateurs calcules automatiquement.",
                note_fmt,
            )
            for col, (header, _, width) in enumerate(columns):
                ws.write(2, col, header, header_input)
                ws.set_column(col, col, width)
            calc_start = len(columns)
            for idx, (header, _, _) in enumerate(formulas):
                col = calc_start + idx
                ws.write(2, col, f"{header}\n[AUTO]", header_calc)
                ws.set_column(col, col, 26)

            for ridx, row in enumerate(rows, start=3):
                xrow = ridx + 1
                for col, (_, key, _) in enumerate(columns):
                    val = row.get(key)
                    if (key == "date" or isinstance(val, (pd.Timestamp,))) and pd.notna(val):
                        ws.write_datetime(ridx, col, pd.to_datetime(val).to_pydatetime(), input_date)
                    elif val is None or pd.isna(val):
                        ws.write_blank(ridx, col, None, input_fmt)
                    elif isinstance(val, str):
                        ws.write(ridx, col, val, text_fmt)
                    else:
                        ws.write_number(ridx, col, float(val), input_fmt)
                for idx, (_, formula, fmt_kind) in enumerate(formulas):
                    fmt = pct_fmt if fmt_kind == "pct" else calc_num
                    ws.write_formula(ridx, calc_start + idx, formula.format(row=xrow), fmt)
            ws.freeze_panes(3, 1)

        def financial_rows(periods: pd.DatetimeIndex, factor: float = 1.0) -> list[dict]:
            n = len(periods)
            return [
                {
                    "date": periods[i],
                    "montant_total_attendu": values(500_000 * factor, 45_000 * factor, n)[i],
                    "total_collecte": values(470_000 * factor, 55_000 * factor, n)[i],
                    "nombre_beneficiaires": values(50, 2, n, True)[i],
                }
                for i in range(n)
            ]

        def operational_rows(periods: pd.DatetimeIndex) -> list[dict]:
            n = len(periods)
            return [
                {
                    "date": periods[i],
                    active_col: values(48, 2, n, True)[i],
                    total_col: values(50, 0, n, True)[i],
                    panne_col: values(1, 1, n, True)[i],
                }
                for i in range(n)
            ]

        def social_rows(periods: pd.DatetimeIndex) -> list[dict]:
            n = len(periods)
            return [
                {
                    "date": periods[i],
                    "beneficiaires_actifs": values(48, 2, n, True)[i],
                    "beneficiaires_initial": values(50, 0, n, True)[i],
                    "revenus_apres": values(140_000, 12_000, n)[i],
                    "nombre_beneficiaires": values(50, 2, n, True)[i],
                }
                for i in range(n)
            ]

        def fintech_rows(periods: pd.DatetimeIndex, factor: float = 1.0) -> list[dict]:
            n = len(periods)
            return [
                {
                    "date": periods[i],
                    "transactions": values(60 * factor, 10 * factor, n, True)[i],
                    "utilisateurs_actifs": values(45, 5, n, True)[i],
                }
                for i in range(n)
            ]

        def discipline_rows(periods: pd.DatetimeIndex) -> list[dict]:
            n = len(periods)
            return [
                {
                    "date": periods[i],
                    "paiements_temps": values(45, 5, n, True)[i],
                    "paiements_attendus": values(50, 0, n, True)[i],
                    "jours_actifs": values(45, 5, n, True)[i],
                    "jours_totaux": values(50, 0, n, True)[i],
                    panne_col: values(1, 1, n, True)[i],
                    total_col: values(50, 0, n, True)[i],
                }
                for i in range(n)
            ]

        def combine_rows(*row_groups: list[dict]) -> list[dict]:
            if not row_groups:
                return []
            merged = []
            for row_parts in zip(*row_groups):
                row = {}
                for part in row_parts:
                    row.update(part)
                merged.append(row)
            return merged

        base_fin_cols = [
            ("date", "date", 14),
            ("Montant total attendu (FCFA)", "montant_total_attendu", 24),
            ("Total collecte (FCFA)", "total_collecte", 22),
            ("Nombre de beneficiaires", "nombre_beneficiaires", 22),
        ]
        op_cols = [
            ("date", "date", 14),
            (f"{vehicle_label_plural.capitalize()} actives (nb)", active_col, 22),
            (f"Total {vehicle_label_plural} (nb)", total_col, 20),
            (f"{vehicle_label_plural.capitalize()} en panne (nb)", panne_col, 24),
        ]
        social_cols = [
            ("date", "date", 14),
            ("Beneficiaires actifs (nb)", "beneficiaires_actifs", 24),
            ("Beneficiaires initial (nb)", "beneficiaires_initial", 24),
            ("Revenus apres projet (FCFA)", "revenus_apres", 26),
            ("Nombre beneficiaires (nb)", "nombre_beneficiaires", 24),
        ]
        fintech_cols = [
            ("date", "date", 14),
            ("Nombre de transactions (nb)", "transactions", 26),
            ("Utilisateurs actifs (nb)", "utilisateurs_actifs", 24),
        ]
        discipline_cols = [
            ("date", "date", 14),
            ("Paiements a temps (nb)", "paiements_temps", 23),
            ("Paiements attendus (nb)", "paiements_attendus", 24),
            ("Jours actifs (nb)", "jours_actifs", 18),
            ("Jours totaux (nb)", "jours_totaux", 18),
            (f"{vehicle_label_plural.capitalize()} en panne (nb)", panne_col, 24),
            (f"Total {vehicle_label_plural} (nb)", total_col, 20),
        ]

        write_table(
            "Quotidien",
            "FREQUENCE QUOTIDIENNE - Indicateurs quotidiens",
            combine_rows(financial_rows(dates), operational_rows(dates)),
            base_fin_cols + op_cols[1:],
            [
                ("Taux de versement du jour", "=IF(B{row}=0,0,C{row}/B{row})", "pct"),
                (f"{vehicle_label_plural.capitalize()} actives", "=E{row}", "num"),
            ],
        )

        write_table(
            "Hebdomadaire",
            "FREQUENCE HEBDOMADAIRE - Indicateurs hebdomadaires",
            combine_rows(financial_rows(weeks, 6), operational_rows(weeks), fintech_rows(weeks, 6), social_rows(weeks), discipline_rows(weeks)),
            base_fin_cols + op_cols[1:] + fintech_cols[1:] + social_cols[1:] + discipline_cols[1:],
            [
                ("Taux de versement hebdomadaire", "=IF(B{row}=0,0,C{row}/B{row})", "pct"),
                (f"Taux de {vehicle_label_plural} en panne", "=IF(F{row}=0,0,G{row}/F{row})", "pct"),
                ("Nombre de transactions semaine", "=H{row}", "num"),
                ("Taux de maintien dans le programme", "=IF(K{row}=0,0,J{row}/K{row})", "pct"),
                ("Score discipline moyen", "=IF(OR(O{row}=0,Q{row}=0,S{row}=0),0,((N{row}/O{row})*0.4+(P{row}/Q{row})*0.3+(1-R{row}/S{row})*0.2)/0.9)", "pct"),
            ],
        )

        write_table(
            "Mensuel",
            "FREQUENCE MENSUELLE - Indicateurs mensuels",
            combine_rows(financial_rows(months, 26), operational_rows(months), fintech_rows(months, 26), social_rows(months), discipline_rows(months)),
            base_fin_cols + op_cols[1:] + fintech_cols[1:] + social_cols[1:] + discipline_cols[1:],
            [
                ("Taux de versement moyen", "=IF(B{row}=0,0,C{row}/B{row})", "pct"),
                ("Montant moyen paye par beneficiaire", "=IF(D{row}=0,0,C{row}/D{row})", "num"),
                (f"{vehicle_label_plural.capitalize()} actives", "=E{row}", "num"),
                ("Nombre de transactions", "=H{row}", "num"),
                ("Nombre d'utilisateurs actifs", "=I{row}", "num"),
                ("Revenu moyen reel", "=IF(M{row}=0,0,L{row}/M{row})", "num"),
                ("Taux de maintien dans le programme", "=IF(K{row}=0,0,J{row}/K{row})", "pct"),
                ("Score discipline moyen", "=IF(OR(O{row}=0,Q{row}=0,S{row}=0),0,((N{row}/O{row})*0.4+(P{row}/Q{row})*0.3+(1-R{row}/S{row})*0.2)/0.9)", "pct"),
            ],
        )

        guide_rows = [
            {"frequence": "Quotidien", "indicateur": "Taux de versement du jour", "bloc": "Financier"},
            {"frequence": "Quotidien / Hebdomadaire / Mensuel", "indicateur": f"{vehicle_label_plural.capitalize()} actives", "bloc": "Operationnel"},
            {"frequence": "Hebdomadaire", "indicateur": f"Taux de {vehicle_label_plural} en panne", "bloc": "Operationnel"},
            {"frequence": "Hebdomadaire", "indicateur": "Nombre de transactions semaine", "bloc": "Fintech"},
            {"frequence": "Mensuel", "indicateur": "Taux de versement moyen", "bloc": "Financier"},
            {"frequence": "Mensuel", "indicateur": "Montant moyen paye par beneficiaire", "bloc": "Financier"},
            {"frequence": "Mensuel", "indicateur": "Revenu moyen reel", "bloc": "Social"},
            {"frequence": "Mensuel", "indicateur": "Nombre de transactions", "bloc": "Fintech"},
            {"frequence": "Mensuel", "indicateur": "Nombre d'utilisateurs actifs", "bloc": "Fintech"},
            {"frequence": "Hebdomadaire / Mensuel", "indicateur": "Taux de maintien dans le programme", "bloc": "Social"},
            {"frequence": "Hebdomadaire / Mensuel", "indicateur": "Score discipline moyen", "bloc": "Discipline"},
            {"frequence": "Hebdomadaire / Mensuel", "indicateur": "Top 20 des plus disciplines", "bloc": "Discipline"},
            {"frequence": "Hebdomadaire / Mensuel", "indicateur": "Top 20 des plus indisciplines", "bloc": "Discipline"},
            {"frequence": "Quotidien / Hebdomadaire / Mensuel", "indicateur": f"Rapport des versements par {vehicle_label}", "bloc": f"Rapport {vehicle_label_plural}"},
        ]
        write_table(
            "Guide Frequences",
            "GUIDE - Indicateurs classes par frequence",
            guide_rows,
            [("Frequence", "frequence", 34), ("Indicateur", "indicateur", 42), ("Bloc KPI", "bloc", 24)],
        )

        report_rows = []
        if is_mock:
            for date_idx, dt in enumerate(dates):
                for vehicle_idx, vehicle_code in enumerate(ids()):
                    expected = max(0, 24_500 + (vehicle_idx % 6) * 850 + rng.normal(0, 1200))
                    rate = np.clip(0.88 + ((date_idx + vehicle_idx) % 9) / 100 + rng.normal(0, 0.035), 0.68, 1.05)
                    report_rows.append({"date": dt, vehicle_id_col: vehicle_code, "versement_attendu": expected, "versement_recu": expected * rate})
        else:
            report_rows = [{"date": dt, vehicle_id_col: "", "versement_attendu": None, "versement_recu": None} for dt in dates]
        write_table(
            f"Rapport {vehicle_label_plural.capitalize()}",
            f"RAPPORT {vehicle_label_plural.upper()} - Versements par {vehicle_label}",
            report_rows,
            [("date", "date", 14), (vehicle_id_title, vehicle_id_col, 18), ("versement_attendu", "versement_attendu", 22), ("versement_recu", "versement_recu", 20)],
        )

        benef_rows = []
        if is_mock:
            for i, vehicle_code in enumerate(ids()):
                benef_rows.append({
                    "date": dates[min(i, len(dates) - 1)],
                    "Nom": f"Beneficiaire {i + 1}",
                    "Telephone": f"+237 670 110 {220 + i}",
                    vehicle_label.capitalize(): vehicle_code,
                    "Zone/Quartier": ["Bonaberi", "Akwa", "Deido", "Makepe", "Bonamoussadi"][i % 5],
                    "Date_Integration": pd.Timestamp("2023-01-01") + pd.DateOffset(weeks=i),
                })
        write_table(
            "Beneficiaires",
            "BENEFICIAIRES - Repertoire",
            benef_rows,
            [("date", "date", 14), ("Nom", "Nom", 24), ("Telephone", "Telephone", 18), (vehicle_label.capitalize(), vehicle_label.capitalize(), 18), ("Zone/Quartier", "Zone/Quartier", 20), ("Date_Integration", "Date_Integration", 20)],
        )


if __name__ == "__main__":
    generate_excel(ROOT / "assets" / "modele_kpi_moto_par_frequence.xlsx", vehicle="moto", is_mock=False)
    generate_excel(ROOT / "assets" / "donnees_test_moto_par_frequence.xlsx", vehicle="moto", is_mock=True)

    # Compatibilite avec l'ancien lien/nom de fichier.
    generate_excel(ROOT / "assets" / "modele_kpi_multifeuilles_mis_a_jour.xlsx", vehicle="moto", is_mock=False)
    generate_excel(ROOT / "assets" / "donnees_test_import.xlsx", vehicle="moto", is_mock=True)

    print("Modeles Excel Moto generes par frequence.")
