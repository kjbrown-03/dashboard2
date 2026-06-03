import pandas as pd
import numpy as np


def generate_excel(file_path, is_mock=False):
    writer = pd.ExcelWriter(file_path, engine='xlsxwriter')
    wb = writer.book

    # ── Formats ──────────────────────────────────────────────────────────────
    header_input = wb.add_format({
        'bold': True, 'bg_color': '#BDD7EE', 'border': 1,
        'text_wrap': True, 'valign': 'vcenter', 'font_size': 10,
    })
    header_calc = wb.add_format({
        'bold': True, 'bg_color': '#E2EFDA', 'border': 1,
        'text_wrap': True, 'valign': 'vcenter', 'font_size': 10,
        'italic': True,
    })
    input_fmt = wb.add_format({'border': 1, 'num_format': '#,##0', 'bg_color': '#FFFFFF'})
    input_date = wb.add_format({'border': 1, 'num_format': 'yyyy-mm-dd', 'bg_color': '#FFFFFF'})
    calc_pct = wb.add_format({'border': 1, 'num_format': '0.00%', 'bg_color': '#F4FFEC', 'italic': True})
    calc_num = wb.add_format({'border': 1, 'num_format': '#,##0', 'bg_color': '#F4FFEC', 'italic': True})
    note_fmt = wb.add_format({
        'bg_color': '#FFF2CC', 'border': 1, 'text_wrap': True,
        'bold': True, 'font_size': 9, 'valign': 'vcenter',
    })
    title_fmt = wb.add_format({
        'bold': True, 'font_size': 12, 'bg_color': '#17663A', 'font_color': '#FFFFFF',
        'border': 1, 'valign': 'vcenter',
    })

    # ── Dates ─────────────────────────────────────────────────────────────────
    dates = pd.date_range(start="2024-04-01", periods=30, freq="D")
    n = len(dates)

    def mock(base, var, is_int=False):
        if not is_mock:
            return [None] * n
        arr = np.random.normal(base, var, n)
        return np.maximum(0, np.round(arr)).astype(int).tolist() if is_int else np.maximum(0, arr).tolist()

    def write_sheet(ws, title, input_cols, calc_specs, data_dict):
        """
        input_cols : list of (header, col_letter, width)
        calc_specs : list of (header, formula_template, is_pct)
        data_dict  : {col_key: list_of_values}
        """
        rows = n

        # Row 0 – big title
        ws.merge_range(0, 0, 0, len(input_cols) + len(calc_specs) - 1, title, title_fmt)
        ws.set_row(0, 22)

        # Row 1 – note
        note_txt = (
            "🔵 Colonnes BLEUES = données à saisir    "
            "🟢 Colonnes VERTES = calculées automatiquement (ne pas modifier)"
        )
        ws.merge_range(1, 0, 1, len(input_cols) + len(calc_specs) - 1, note_txt, note_fmt)
        ws.set_row(1, 30)

        # Row 2 – headers
        for col_idx, (hdr, _, width) in enumerate(input_cols):
            ws.write(2, col_idx, hdr, header_input)
            ws.set_column(col_idx, col_idx, width)

        calc_start = len(input_cols)
        for i, (hdr, _, _) in enumerate(calc_specs):
            ws.write(2, calc_start + i, hdr + "\n[AUTO]", header_calc)
            ws.set_column(calc_start + i, calc_start + i, 22)

        # Rows 3..n+2 – data + formulas  (Excel row = python_row+1 in 1-based)
        keys = [k for _, k, _ in input_cols]
        for r in range(rows):
            xrow = r + 4  # 1-based Excel row for formulas (row 3 = headers → data starts row 4)
            py_row = r + 3  # 0-based python row

            for col_idx, (_, key, _) in enumerate(input_cols):
                val = data_dict.get(key, [None] * n)[r]
                if key == "date":
                    ws.write_datetime(py_row, col_idx, dates[r].to_pydatetime(), input_date)
                elif val is None:
                    ws.write_blank(py_row, col_idx, None, input_fmt)
                else:
                    ws.write_number(py_row, col_idx, float(val), input_fmt)

            for i, (_, formula_tpl, is_pct) in enumerate(calc_specs):
                formula = formula_tpl.format(row=xrow)
                fmt = calc_pct if is_pct else calc_num
                ws.write_formula(py_row, calc_start + i, formula, fmt)

    # ══════════════════════════════════════════════════════════════════════════
    # FINANCIER
    # ══════════════════════════════════════════════════════════════════════════
    fin_data = {
        "date": dates,
        "montant_total_attendu": mock(500_000, 50_000),
        "total_collecte": mock(480_000, 60_000),
        "nombre_beneficiaires": mock(50, 0, True),
    }
    fin_input = [
        ("date",                         "date",                  14),
        ("Montant total attendu (FCFA)",  "montant_total_attendu", 22),
        ("Total collecté (FCFA)",         "total_collecte",        22),
        ("Nombre de bénéficiaires",       "nombre_beneficiaires",  20),
    ]
    # A=date  B=montant_attendu  C=total_collecte  D=nb_beneficiaires
    fin_calc = [
        ("Taux de versement\n(reçu / attendu)",
         "=IF(B{row}=0,0,C{row}/B{row})", True),
        ("Montant moyen / bénéf.\n(FCFA)",
         "=IF(D{row}=0,0,C{row}/D{row})", False),
    ]

    ws_fin = writer.book.add_worksheet("Financier")
    writer.sheets["Financier"] = ws_fin
    write_sheet(ws_fin, "FINANCIER — Données de remboursement", fin_input, fin_calc,
                {k: list(v) if hasattr(v, '__iter__') and not isinstance(v, str) else v for k, v in fin_data.items()})

    # ══════════════════════════════════════════════════════════════════════════
    # OPERATIONNEL
    # ══════════════════════════════════════════════════════════════════════════
    op_data = {
        "date": dates,
        "motos_actives": mock(48, 2, True),
        "total_motos": mock(50, 0, True),
        "motos_panne": mock(1, 1, True),
    }
    op_input = [
        ("date",                "date",          14),
        ("Motos actives (nb)",  "motos_actives", 18),
        ("Total motos (nb)",    "total_motos",   16),
        ("Motos en panne (nb)", "motos_panne",   18),
    ]
    # A=date  B=motos_actives  C=total_motos  D=motos_panne
    op_calc = [
        ("Motos actives\n(nombre)",
         "=B{row}", False),
        ("Taux de motos en panne\n(panne / total)",
         "=IF(C{row}=0,0,D{row}/C{row})", True),
    ]

    ws_op = writer.book.add_worksheet("Operationnel")
    writer.sheets["Operationnel"] = ws_op
    write_sheet(ws_op, "OPÉRATIONNEL — Activité des motos", op_input, op_calc,
                {k: list(v) if hasattr(v, '__iter__') and not isinstance(v, str) else v for k, v in op_data.items()})

    # ══════════════════════════════════════════════════════════════════════════
    # SOCIAL
    # ══════════════════════════════════════════════════════════════════════════
    soc_data = {
        "date": dates,
        "beneficiaires_actifs": mock(48, 2, True),
        "beneficiaires_initial": mock(50, 0, True),
        "revenus_apres": mock(140_000, 15_000),
        "nombre_beneficiaires": mock(50, 0, True),
    }
    soc_input = [
        ("date",                        "date",                  14),
        ("Bénéficiaires actifs (nb)",   "beneficiaires_actifs",  20),
        ("Bénéficiaires initial (nb)",  "beneficiaires_initial", 20),
        ("Revenus après projet (FCFA)", "revenus_apres",         22),
        ("Nombre bénéficiaires (nb)",   "nombre_beneficiaires",  20),
    ]
    # A=date  B=beneficiaires_actifs  C=beneficiaires_initial  D=revenus_apres  E=nombre_beneficiaires
    soc_calc = [
        ("Taux de maintien\n(actifs / initial)",
         "=IF(C{row}=0,0,B{row}/C{row})", True),
        ("Revenu moyen réel\n(rev. après / bénéf.)",
         "=IF(E{row}=0,0,D{row}/E{row})", False),
    ]

    ws_soc = writer.book.add_worksheet("Social")
    writer.sheets["Social"] = ws_soc
    write_sheet(ws_soc, "SOCIAL — Impact social du programme", soc_input, soc_calc,
                {k: list(v) if hasattr(v, '__iter__') and not isinstance(v, str) else v for k, v in soc_data.items()})

    # ══════════════════════════════════════════════════════════════════════════
    # FINTECH
    # ══════════════════════════════════════════════════════════════════════════
    ft_data = {
        "date": dates,
        "transactions": mock(60, 10, True),
        "utilisateurs_actifs": mock(45, 5, True),
    }
    ft_input = [
        ("date",                        "date",               14),
        ("Nombre de transactions (nb)", "transactions",        20),
        ("Utilisateurs actifs (nb)",    "utilisateurs_actifs", 20),
    ]
    # A=date  B=transactions  C=utilisateurs_actifs  — pas de calcul auto
    ft_calc = []

    ws_ft = writer.book.add_worksheet("Fintech")
    writer.sheets["Fintech"] = ws_ft
    write_sheet(ws_ft, "FINTECH — Yunus Pay & transactions digitales", ft_input, ft_calc,
                {k: list(v) if hasattr(v, '__iter__') and not isinstance(v, str) else v for k, v in ft_data.items()})

    # ══════════════════════════════════════════════════════════════════════════
    # DISCIPLINE
    # ══════════════════════════════════════════════════════════════════════════
    disc_data = {
        "date": dates,
        "paiements_temps": mock(45, 5, True),
        "paiements_attendus": mock(50, 0, True),
        "jours_actifs": mock(45, 5, True),
        "jours_totaux": mock(50, 0, True),
        "motos_panne": mock(1, 1, True),
        "total_motos": mock(50, 0, True),
    }
    disc_input = [
        ("date",                    "date",              14),
        ("Paiements à temps (nb)",  "paiements_temps",   20),
        ("Paiements attendus (nb)", "paiements_attendus", 20),
        ("Jours actifs (nb)",       "jours_actifs",      16),
        ("Jours totaux (nb)",       "jours_totaux",      16),
        ("Motos en panne (nb)",     "motos_panne",       18),
        ("Total motos (nb)",        "total_motos",       16),
    ]
    # A=date  B=pmt_ok  C=pmt_att  D=j_act  E=j_tot  F=panne  G=total
    # Score = (B/C×40% + D/E×30% + (1-F/G)×20%) / 0.9
    disc_calc = [
        ("Score discipline moyen\n(40% pmt + 30% act. + 20% entr.)",
         "=IF(OR(C{row}=0,E{row}=0,G{row}=0),0,"
         "((B{row}/C{row})*0.4+(D{row}/E{row})*0.3+(1-F{row}/G{row})*0.2)/0.9)",
         True),
    ]

    ws_disc = writer.book.add_worksheet("Discipline")
    writer.sheets["Discipline"] = ws_disc
    write_sheet(ws_disc, "DISCIPLINE — Score de discipline des bénéficiaires", disc_input, disc_calc,
                {k: list(v) if hasattr(v, '__iter__') and not isinstance(v, str) else v for k, v in disc_data.items()})

    # ══════════════════════════════════════════════════════════════════════════
    # KPI HEBDO  (agrégation hebdomadaire manuelle)
    # ══════════════════════════════════════════════════════════════════════════
    weeks = pd.date_range(start="2024-04-01", periods=8, freq="W-MON")
    nw = len(weeks)

    def mockw(base, var, is_int=False):
        if not is_mock:
            return [None] * nw
        arr = np.random.normal(base, var, nw)
        return np.maximum(0, np.round(arr)).astype(int).tolist() if is_int else np.maximum(0, arr).tolist()

    hebdo_data = {
        "date": weeks,
        "total_collecte_sem": mockw(3_000_000, 200_000),
        "montant_attendu_sem": mockw(3_200_000, 100_000),
        "motos_actives_sem": mockw(48, 2, True),
        "total_motos_sem": mockw(50, 0, True),
    }

    ws_hb = writer.book.add_worksheet("KPI Hebdo")
    writer.sheets["KPI Hebdo"] = ws_hb

    hb_input = [
        ("Semaine (lundi)",                "date",                18),
        ("Total collecté semaine (FCFA)",  "total_collecte_sem",  24),
        ("Montant attendu semaine (FCFA)", "montant_attendu_sem", 24),
        ("Motos actives (nb)",             "motos_actives_sem",   18),
        ("Total motos (nb)",               "total_motos_sem",     16),
    ]
    hb_calc = [
        ("Versement hebdomadaire\n(reçu / attendu)",
         "=IF(C{row}=0,0,B{row}/C{row})", True),
    ]

    def write_hebdo(ws):
        ws.merge_range(0, 0, 0, len(hb_input) + len(hb_calc) - 1,
                       "KPI HEBDO — Indicateurs hebdomadaires essentiels", title_fmt)
        ws.set_row(0, 22)
        note = ("🔵 Colonnes BLEUES = données à saisir    "
                "🟢 Colonnes VERTES = calculées automatiquement (ne pas modifier)")
        ws.merge_range(1, 0, 1, len(hb_input) + len(hb_calc) - 1, note, note_fmt)
        ws.set_row(1, 30)

        for i, (hdr, _, w) in enumerate(hb_input):
            ws.write(2, i, hdr, header_input)
            ws.set_column(i, i, w)
        for i, (hdr, _, _) in enumerate(hb_calc):
            ws.write(2, len(hb_input) + i, hdr + "\n[AUTO]", header_calc)
            ws.set_column(len(hb_input) + i, len(hb_input) + i, 22)

        for r in range(nw):
            xrow = r + 4
            py_row = r + 3
            vals = [
                weeks[r].to_pydatetime(),
                hebdo_data["total_collecte_sem"][r],
                hebdo_data["montant_attendu_sem"][r],
                hebdo_data["motos_actives_sem"][r],
                hebdo_data["total_motos_sem"][r],
            ]
            for c, v in enumerate(vals):
                if c == 0:
                    ws.write_datetime(py_row, c, v, input_date)
                elif v is None:
                    ws.write_blank(py_row, c, None, input_fmt)
                else:
                    ws.write_number(py_row, c, float(v), input_fmt)
            for i, (_, formula_tpl, is_pct) in enumerate(hb_calc):
                ws.write_formula(py_row, len(hb_input) + i,
                                 formula_tpl.format(row=xrow),
                                 calc_pct if is_pct else calc_num)

    write_hebdo(ws_hb)

    # ══════════════════════════════════════════════════════════════════════════
    # BÉNÉFICIAIRES
    # ══════════════════════════════════════════════════════════════════════════
    benef_cols = ["date", "Nom", "Téléphone", "Moto", "Zone/Quartier", "Date_Integration"]
    if is_mock:
        nb = 20
        df_b = pd.DataFrame({
            "date": pd.date_range("2024-04-01", periods=nb, freq="D"),
            "Nom": [f"Bénéficiaire {i+1}" for i in range(nb)],
            "Téléphone": [f"+237 670 110 {220+i}" for i in range(nb)],
            "Moto": [f"MOTO-{1001+i}" for i in range(nb)],
            "Zone/Quartier": ["Bonaberi", "Akwa", "Deido", "Makepe", "Bonamoussadi"] * 4,
            "Date_Integration": pd.date_range("2023-01-01", periods=nb, freq="W").strftime("%Y-%m-%d"),
        })
    else:
        df_b = pd.DataFrame(columns=benef_cols)

    ws_b = writer.book.add_worksheet("Bénéficiaires")
    writer.sheets["Bénéficiaires"] = ws_b
    ws_b.merge_range(0, 0, 0, 5, "BÉNÉFICIAIRES — Répertoire des bénéficiaires", title_fmt)
    ws_b.set_row(0, 22)
    for c, col in enumerate(benef_cols):
        ws_b.write(1, c, col, header_input)
        ws_b.set_column(c, c, 18)
    for r, row in df_b.iterrows():
        for c, col in enumerate(benef_cols):
            val = row[col]
            ws_b.write(r + 2, c, str(val) if pd.notna(val) else "")

    writer.close()


# 1. Template vierge (colonnes bleues vides, formules vertes prêtes)
generate_excel("assets/modele_kpi_multifeuilles_mis_a_jour.xlsx", is_mock=False)

# 2. Fichier de test avec données mock
generate_excel("assets/donnees_test_import.xlsx", is_mock=True)

print("Templates Excel générés avec cellules auto-calculées (colonnes vertes) !")
