import pandas as pd
import numpy as np

def generate_excel(file_path, is_mock=False):
    writer = pd.ExcelWriter(file_path, engine='xlsxwriter')
    
    # 30 days of data
    dates = pd.date_range(start="2024-04-01", periods=30, freq="D")
    n = len(dates)

    def mock_data(base, variance, is_int=False):
        if not is_mock:
            return [0] * n
        arr = np.random.normal(base, variance, n)
        if is_int:
            return np.maximum(0, np.round(arr)).astype(int)
        return np.maximum(0, arr)

    # --- FINANCIER ---
    df_fin = pd.DataFrame({
        "date": dates,
        "montant_total_attendu": mock_data(500000, 50000),
        "montant_total_rembourse": mock_data(480000, 60000),
        "montant_total_finance": mock_data(10000000, 0),
        "montant_en_defaut": mock_data(200000, 20000),
        "paiements_temps": mock_data(45, 5, True),
        "paiements_attendus": mock_data(50, 0, True),
        "total_collecte": mock_data(480000, 60000),
        "nombre_beneficiaires": mock_data(50, 0, True),
        "montant_recupere": mock_data(10000, 2000),
        "montant_total_prete": mock_data(10000000, 0),
        "cout_total_projet": mock_data(100000, 0),
        "beneficiaires_finances": mock_data(50, 0, True),
        "montant_recupere_apres_defaut": mock_data(5000, 1000)
    })

    # --- OPERATIONNEL ---
    df_op = pd.DataFrame({
        "date": dates,
        "motos_actives": mock_data(48, 2, True),
        "total_motos": mock_data(50, 0, True),
        "jours_actifs": mock_data(45, 5, True),
        "jours_totaux": mock_data(50, 0, True),
        "courses": mock_data(200, 30, True),
        "jours_sans_activite": mock_data(2, 1, True),
        "motos_panne": mock_data(1, 1, True)
    })

    # --- SOCIAL ---
    df_soc = pd.DataFrame({
        "date": dates,
        "revenus_estimes": mock_data(150000, 20000),
        "beneficiaires_actifs": mock_data(48, 2, True),
        "beneficiaires_initial": mock_data(50, 0, True),
        "emplois_directs": mock_data(50, 0, True),
        "emplois_indirects": mock_data(100, 5, True),
        "revenus_avant": mock_data(100000, 0),
        "revenus_apres": mock_data(140000, 15000)
    })

    # --- FINTECH ---
    df_fintech = pd.DataFrame({
        "date": dates,
        "paiements_digitaux": mock_data(45, 5, True),
        "paiements_totaux": mock_data(50, 0, True),
        "volume_transactions": mock_data(400000, 50000),
        "commissions": mock_data(4000, 500),
        "utilisateurs_actifs": mock_data(45, 5, True),
        "transactions": mock_data(60, 10, True)
    })

    # --- DISCIPLINE ---
    df_disc = pd.DataFrame({
        "date": dates,
        "paiements_temps": mock_data(45, 5, True),
        "paiements_attendus": mock_data(50, 0, True),
        "jours_actifs": mock_data(45, 5, True),
        "jours_totaux": mock_data(50, 0, True),
        "motos_panne": mock_data(1, 1, True),
        "total_motos": mock_data(50, 0, True),
    })
    
    # --- KPI HEBDO ---
    df_hebdo = pd.DataFrame({
        "date": dates
    })

    # --- BENEFICIAIRES ---
    if is_mock:
        df_benef = pd.DataFrame({
            "date": pd.date_range(start="2024-04-01", periods=20, freq="D"),
            "Nom": [f"Bénéficiaire {i+1}" for i in range(20)],
            "Téléphone": [f"+237 670 110 {220+i}" for i in range(20)],
            "Moto": [f"MOTO-{1000+i+1}" for i in range(20)],
            "Zone/Quartier": ["Bonaberi", "Akwa", "Deido", "Makepe", "Bonamoussadi"] * 4,
            "Date_Integration": pd.date_range(start="2023-01-01", periods=20, freq="W").strftime("%Y-%m-%d")
        })
    else:
        df_benef = pd.DataFrame({
            "date": [],
            "Nom": [],
            "Téléphone": [],
            "Moto": [],
            "Zone/Quartier": [],
            "Date_Integration": []
        })

    # Write to Excel
    df_fin.to_excel(writer, sheet_name="Financier", index=False)
    df_op.to_excel(writer, sheet_name="Operationnel", index=False)
    df_soc.to_excel(writer, sheet_name="Social", index=False)
    df_fintech.to_excel(writer, sheet_name="Fintech", index=False)
    df_disc.to_excel(writer, sheet_name="Discipline", index=False)
    df_hebdo.to_excel(writer, sheet_name="KPI Hebdo", index=False)
    df_benef.to_excel(writer, sheet_name="Bénéficiaires", index=False)

    workbook = writer.book

    # Add formats
    header_format = workbook.add_format({
        'bold': True, 'text_wrap': True, 'valign': 'top', 'fg_color': '#D7E4BC', 'border': 1
    })
    formula_format = workbook.add_format({
        'bg_color': '#F2F2F2', 'border': 1, 'num_format': '0.00%'
    })
    formula_num_format = workbook.add_format({
        'bg_color': '#F2F2F2', 'border': 1, 'num_format': '#,##0'
    })

    formulas = {
        "Financier": [
            ("Performance (%)", '=IF(B{row}=0, 0, H{row}/B{row})', formula_format),
            ("Montant moyen / bénéf (FCFA)", '=IF(I{row}=0, 0, H{row}/I{row})', formula_num_format),
        ],
        "Operationnel": [
            ("Taux motos actives (%)", '=IF(C{row}=0, 0, B{row}/C{row})', formula_format),
            ("Taux de pannes (%)", '=IF(C{row}=0, 0, H{row}/C{row})', formula_format),
        ],
        "Social": [
            ("Taux maintien (%)", '=IF(D{row}=0, 0, C{row}/D{row})', formula_format),
            ("Amélioration revenus (%)", '=IF(G{row}=0, 0, (H{row}-G{row})/G{row})', formula_format),
            ("Emplois créés", '=E{row}+F{row}', formula_num_format),
        ],
        "Fintech": [
            ("Taux digitalisation (%)", '=IF(C{row}=0, 0, B{row}/C{row})', formula_format),
        ],
        "Discipline": [
            ("Score discipline (%)", '=IF(OR(C{row}=0,E{row}=0,G{row}=0),0,((B{row}/C{row})*0.4+(D{row}/E{row})*0.3+(1-F{row}/G{row})*0.2)/0.9)', formula_format),
        ],
        "KPI Hebdo": [],
        "Bénéficiaires": []
    }

    df_map = {
        "Financier": df_fin,
        "Operationnel": df_op,
        "Social": df_soc,
        "Fintech": df_fintech,
        "Discipline": df_disc,
        "KPI Hebdo": df_hebdo,
        "Bénéficiaires": df_benef
    }

    for sheet_name in formulas.keys():
        worksheet = writer.sheets[sheet_name]
        df = df_map[sheet_name]
        start_col = len(df.columns)
        
        # Write formula headers
        for i, (col_name, _, _) in enumerate(formulas[sheet_name]):
            worksheet.write(0, start_col + i, col_name, header_format)
            
        # Write formulas
        for row_idx in range(1, len(df) + 1):
            for i, (_, formula_str, fmt) in enumerate(formulas[sheet_name]):
                actual_formula = formula_str.format(row=row_idx + 1)
                worksheet.write_formula(row_idx, start_col + i, actual_formula, fmt)

    writer.close()

# 1. Blank Template
generate_excel("assets/modele_kpi_multifeuilles_mis_a_jour.xlsx", is_mock=False)

# 2. Mock Data File for Testing
generate_excel("assets/donnees_test_import.xlsx", is_mock=True)

print("Both Excel files generated successfully without Terrain/Risque and with Beneficiaires!")
