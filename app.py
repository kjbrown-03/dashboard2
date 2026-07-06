from __future__ import annotations

import base64
import io
import logging
import threading
import webbrowser
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, State, callback_context, dcc, html, no_update
from werkzeug.exceptions import HTTPException


LOGGER = logging.getLogger(__name__)
BRAND = "#17663a"
ACCENT = "#0f766e"
WARNING = "#b7791f"
DANGER = "#b91c1c"
INFO = "#475569"


@dataclass(frozen=True)
class Indicator:
    key: str
    name: str
    group: str
    formula: str
    frequency: str
    unit: str = ""
    higher_is_better: bool = True
    good: float | None = None
    watch: float | None = None


GROUPS = {
    "financier": "Financier",
    "operationnel": "Operationnel",
    "social": "Social",
    "fintech": "Fintech",
    "hebdo": "KPI Hebdo",
    "discipline": "Discipline",
    "rapport": "Rapport motos",
}

MOCK_NAMES = [
    "Amadou B.", "Awa N.", "Baba S.", "Binta F.", "Cheikh T.",
    "Coumba D.", "Demba K.", "Diallo M.", "Fatou D.", "Hawa C.",
    "Ibrahima S.", "Issa Y.", "Kadiatou B.", "Lamine D.", "Mamadou L.",
    "Mariama C.", "Moussa D.", "Oumar B.", "Ousmane S.", "Ramatoulaye T.",
    "Samba F.", "Sidi K.", "Souleymane D.", "Tidiane M.", "Yacouba D.",
    "Zeinabou S.", "Abdoulaye K.", "Aminata T.", "Bakary D.", "Fanta M."
]

INDICATORS = [
    # --- FINANCIER QUOTIDIEN ---
    Indicator("performance_jour", "Taux de versement du jour", "financier", "Versement recu du jour / Versement attendu du jour", "daily", "%", True, 95, 90),
    # --- FINANCIER HEBDOMADAIRE ---
    Indicator("performance_hebdomadaire", "Taux de versement hebdomadaire", "financier", "Versement recu de la semaine / Versement attendu de la semaine", "weekly", "%", True, 95, 90),
    # --- FINANCIER MENSUEL ---
    Indicator("performance_mensuelle", "Taux de versement moyen", "financier", "Versement recu du mois / Versement attendu du mois", "monthly", "%", True, 95, 90),
    Indicator("montant_moyen", "Montant moyen paye par beneficiaire", "financier", "Total collecte / Nombre de beneficiaires", "monthly", "FCFA", True),
    # --- OPERATIONNEL (all = quotidien + hebdo + mensuel) ---
    Indicator("motos_actives", "Motos actives", "operationnel", "Nombre de motos actives", "all", "", True),
    Indicator("taux_pannes", "Taux de motos en panne", "operationnel", "Nombre motos en panne / Nombre total motos x 100", "weekly", "%", False, 3, 7),
    # --- SOCIAL ---
    Indicator("revenu_moyen_reel", "Revenu moyen reel", "social", "Revenus apres projet / Nombre beneficiaires", "monthly", "FCFA", True),
    Indicator("taux_maintien", "Taux de maintien dans le programme", "social", "Nombre beneficiaires actifs / Nombre initial x 100", "both", "%", True, 98, 95),
    Indicator("volume_transactions_semaine", "Nombre de transactions semaine", "fintech", "Nombre total de transactions sur la semaine", "weekly", "", True),
    Indicator("volume_transactions", "Nombre de transactions", "fintech", "Nombre total de transactions", "monthly", "", True),
    Indicator("nb_utilisateurs_actifs", "Nombre d'utilisateurs actifs", "fintech", "Utilisateurs ayant realise au moins une transaction", "monthly", "", True),
    Indicator("score_discipline", "Score discipline moyen", "discipline", "(Paiements a temps x 40%) + (Activite x 30%) + (Entretien x 20%), moyenne par moto", "both", "%", True, 90, 70),
    Indicator("top_beneficiaires", "Top 20 des plus disciplinés", "discipline", "Les 20 beneficiaires les plus disciplines", "both", "", True),
    Indicator("flop_beneficiaires", "Top 20 des plus indisciplinés", "discipline", "Les 20 beneficiaires les moins disciplines", "both", "", False, 5, 15),
    Indicator("hebdo_performance", "Versement hebdomadaire", "hebdo", "Repris du KPI financier", "weekly", "%", True, 95, 90),
    Indicator("hebdo_motos_actives", "Motos actives", "hebdo", "Repris du KPI operationnel", "weekly", "", True, 95, 90),
    Indicator("rapport_motos", "Rapport des versements par moto", "rapport", "Versement recu et versement attendu par identifiant moto", "all", "", True),
]

INDICATOR_BY_KEY = {indicator.key: indicator for indicator in INDICATORS}

INACTIVE_MOTO_INDICATORS = {
    "motos_actives",
    "hebdo_motos_actives",
}

OPERATIONAL_MOTO_INDICATORS = {
    "motos_actives",
    "taux_pannes",
    "hebdo_motos_actives",
}

FINANCIAL_PERFORMANCE_INDICATORS = {
    "performance_jour",
    "performance_hebdomadaire",
    "performance_mensuelle",
    "hebdo_performance",
}

DISCIPLINE_WEIGHTS = {
    "paiement_temps": 0.40,
    "activite": 0.30,
    "entretien": 0.20,
}
DISCIPLINE_WEIGHT_TOTAL = sum(DISCIPLINE_WEIGHTS.values())

SOCIAL_INDICATORS_IMPLEMENTED = {
    "revenu_moyen_reel",
    "taux_maintien",
}

HEBDO_SOURCE_INDICATORS = {
    "hebdo_performance": "performance_hebdomadaire",
    "hebdo_motos_actives": "motos_actives",
}

REQUIRED_COLUMNS = [
    "date",
    "montant_total_attendu",
    "montant_total_rembourse",
    "montant_total_finance",
    "paiements_temps",
    "paiements_attendus",
    "total_collecte",
    "nombre_beneficiaires",
    "montant_recupere",
    "montant_total_prete",
    "motos_actives",
    "total_motos",
    "jours_actifs",
    "jours_totaux",
    "courses",
    "jours_sans_activite",
    "motos_panne",
    "revenus_estimes",
    "beneficiaires_actifs",
    "beneficiaires_initial",
    "emplois_directs",
    "emplois_indirects",
    "revenus_apres",
    "paiements_digitaux",
    "paiements_totaux",
    "volume_transactions",
    "utilisateurs_actifs",
    "transactions",
    "beneficiaires_finances",
    "score_discipline",
    "top_beneficiaires",
    "flop_beneficiaires",
]

MOTO_REPORT_COLUMNS = [
    "date",
    "moto_id",
    "versement_attendu",
    "versement_recu",
]


def safe_ratio(num: float, den: float) -> float:
    return 0 if den in (0, None) else num / den


def percent_change(current: float, previous: float) -> float:
    if previous in (0, None):
        return 0 if current in (0, None) else 100
    return ((current - previous) / abs(previous)) * 100


def stable_offset(text: str) -> int:
    return sum(ord(char) for char in text)


def mock_beneficiary_name(index: int, key: str = "") -> str:
    return MOCK_NAMES[(index + stable_offset(key)) % len(MOCK_NAMES)]


def clamp_percent(value: float) -> float:
    return max(0, min(100, value))


def discipline_components_from_sums(sums: dict[str, float]) -> dict[str, float]:
    paiement_temps = safe_ratio(sums.get("paiements_temps", 0), sums.get("paiements_attendus", 0)) * 100
    activite = safe_ratio(sums.get("jours_actifs", 0), sums.get("jours_totaux", 0)) * 100
    panne_rate = safe_ratio(sums.get("motos_panne", 0), sums.get("total_motos", 0))
    entretien = (1 - panne_rate) * 100
    return {
        "paiement_temps": clamp_percent(paiement_temps),
        "activite": clamp_percent(activite),
        "entretien": clamp_percent(entretien),
    }


def discipline_score_from_sums(sums: dict[str, float]) -> float:
    components = discipline_components_from_sums(sums)
    weighted_score = sum(components[key] * weight for key, weight in DISCIPLINE_WEIGHTS.items())
    return safe_ratio(weighted_score, DISCIPLINE_WEIGHT_TOTAL)


def make_sample_data() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    start = date.today() - timedelta(days=210)
    rows = []
    total_motos = 240
    initial_beneficiaries = 185

    for i in range(211):
        current_date = start + timedelta(days=i)
        growth = 1 + i * 0.0018
        beneficiaires = int(initial_beneficiaries * growth)
        expected = 1_350_000 * growth + rng.normal(0, 45_000)
        repayment_rate = np.clip(92 + 4 * np.sin(i / 18) + rng.normal(0, 2.1), 81, 101)
        reimbursed = expected * repayment_rate / 100
        financed = 62_000_000 * growth
        encours_total = 48_000_000 * growth
        amount_default = financed * np.clip(0.055 + rng.normal(0, 0.012), 0.015, 0.14)
        encours_late7 = encours_total * np.clip(0.07 + rng.normal(0, 0.018), 0.02, 0.17)
        encours_late30 = encours_total * np.clip(0.035 + rng.normal(0, 0.01), 0.01, 0.12)
        payments_expected = max(1, int(74 * growth))
        payments_on_time = int(payments_expected * np.clip(repayment_rate / 103 + rng.normal(0, 0.025), 0.68, 1))
        late_count = max(0, payments_expected - payments_on_time)
        active_motos = int(total_motos * np.clip(0.93 + 0.04 * np.sin(i / 13) + rng.normal(0, 0.02), 0.79, 1))
        broken_motos = int(total_motos * np.clip(0.035 + rng.normal(0, 0.012), 0, 0.11))
        courses = int(active_motos * np.clip(8.4 + rng.normal(0, 1.2), 4.5, 13.5))
        visits_planned = max(1, int(beneficiaires / 18))
        visits_done = int(visits_planned * np.clip(0.87 + rng.normal(0, 0.055), 0.58, 1))
        incidents = max(1, int(np.clip(3 + rng.normal(0, 1.4), 0, 9)))
        incidents_resolus = int(incidents * np.clip(0.86 + rng.normal(0, 0.08), 0.45, 1))
        digital_payments = int(payments_expected * np.clip(0.78 + i * 0.001 + rng.normal(0, 0.03), 0.55, 1))
        transaction_volume = digital_payments * np.clip(18_500 + rng.normal(0, 1_200), 14_000, 25_000)
        revenues_estimated = beneficiaires * np.clip(16_000 + rng.normal(0, 1_100), 10_000, 25_000)
        revenues_before = beneficiaires * 12_000

        rows.append(
            {
                "date": pd.to_datetime(current_date),
                "montant_total_attendu": expected,
                "montant_total_rembourse": reimbursed,
                "montant_total_finance": financed,
                "montant_en_defaut": amount_default,
                "encours_total": encours_total,
                "encours_retard_7": encours_late7,
                "encours_retard_30": encours_late30,
                "paiements_temps": payments_on_time,
                "paiements_attendus": payments_expected,
                "total_collecte": reimbursed,
                "nombre_beneficiaires": beneficiaires,
                "montant_recupere": reimbursed * np.clip(0.91 + rng.normal(0, 0.025), 0.75, 1),
                "montant_total_prete": financed,
                "motos_actives": active_motos,
                "total_motos": total_motos,
                "jours_actifs": active_motos,
                "jours_totaux": total_motos,
                "courses": courses,
                "jours_sans_activite": total_motos - active_motos,
                "motos_panne": broken_motos,
                "revenus_estimes": revenues_estimated,
                "beneficiaires_actifs": int(beneficiaires * np.clip(0.97 + rng.normal(0, 0.012), 0.88, 1)),
                "beneficiaires_initial": initial_beneficiaries,
                "emplois_directs": int(beneficiaires * 1.05),
                "emplois_indirects": int(beneficiaires * 0.32),
                "revenus_apres": revenues_estimated,
                "paiements_digitaux": digital_payments,
                "paiements_totaux": payments_expected,
                "volume_transactions": transaction_volume,
                "utilisateurs_actifs": int(beneficiaires * np.clip(0.78 + i * 0.0007, 0.72, 0.95)),
                "transactions": digital_payments,
                "visites_realisees": visits_done,
                "visites_prevues": visits_planned,
                "delai_reaction": np.clip(1.5 + rng.normal(0, 0.45), 0.4, 4.8),
                "incidents_resolus": incidents_resolus,
                "incidents_detectes": incidents,
                "beneficiaires_retard": late_count,
                "cas_defaut": max(0, int(late_count * np.clip(0.25 + rng.normal(0, 0.08), 0.05, 0.55))),
                "retard_total_jours": late_count * np.clip(2.8 + rng.normal(0, 1.1), 0.5, 9),
                "montant_recupere_apres_defaut": amount_default * np.clip(0.72 + rng.normal(0, 0.08), 0.35, 0.95),
                "motos_recuperees": 1 if rng.random() > 0.965 else 0,
                "beneficiaires_finances": beneficiaires,
                "score_discipline": np.clip(8.0 + rng.normal(0, 0.8) - late_count * 0.015, 2, 10),
                "top_beneficiaires": max(0, int(beneficiaires * np.clip(0.28 + rng.normal(0, 0.04), 0.12, 0.45))),
                "flop_beneficiaires": max(0, int(late_count * np.clip(0.35 + rng.normal(0, 0.08), 0.10, 0.65))),
            }
        )
    return pd.DataFrame(rows)


def prepare_data(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    aliases = {
        "Periode": "date",
        "Date": "date",
        "week_start": "date",
        "beneficiaires": "nombre_beneficiaires",
        "jours_inactifs": "jours_sans_activite",
        "Total collecté": "total_collecte",
        "Montant total remboursé": "montant_total_rembourse",
        "Montant total attendu": "montant_total_attendu",
    }
    aliases.update(
        {
            "Semaine (lundi)": "date",
            "Total collecté": "total_collecte",
            "Total collecté (FCFA)": "total_collecte",
            "Total collecte (FCFA)": "total_collecte",
            "Total collecté semaine (FCFA)": "total_collecte",
            "Montant total remboursé": "montant_total_rembourse",
            "Montant total attendu (FCFA)": "montant_total_attendu",
            "Montant attendu semaine (FCFA)": "montant_total_attendu",
            "Nombre de bénéficiaires": "nombre_beneficiaires",
            "Nombre bénéficiaires (nb)": "nombre_beneficiaires",
            "Motos actives (nb)": "motos_actives",
            "Motos actives\n(nombre)\n[AUTO]": "motos_actives",
            "Total motos (nb)": "total_motos",
            "Motos en panne (nb)": "motos_panne",
            "Bénéficiaires actifs (nb)": "beneficiaires_actifs",
            "Bénéficiaires initial (nb)": "beneficiaires_initial",
            "Revenus après projet (FCFA)": "revenus_apres",
            "Nombre de transactions (nb)": "transactions",
            "Utilisateurs actifs (nb)": "utilisateurs_actifs",
            "Paiements à temps (nb)": "paiements_temps",
            "Paiements attendus (nb)": "paiements_attendus",
            "Jours actifs (nb)": "jours_actifs",
            "Jours totaux (nb)": "jours_totaux",
        }
    )
    prepared = prepared.rename(columns={k: v for k, v in aliases.items() if k in prepared.columns})
    if prepared.columns.duplicated().any():
        deduped = pd.DataFrame(index=prepared.index)
        for column in dict.fromkeys(prepared.columns):
            matches = prepared.loc[:, prepared.columns == column]
            deduped[column] = matches.iloc[:, 0] if matches.shape[1] == 1 else matches.bfill(axis=1).iloc[:, 0]
        prepared = deduped
    if "date" not in prepared.columns:
        raise ValueError("Colonne manquante: date")
    for column in REQUIRED_COLUMNS:
        if column != "date" and column not in prepared.columns:
            prepared[column] = 0
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["date"])
    for column in REQUIRED_COLUMNS:
        if column != "date":
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0)
    inactive_from_motos = (prepared["total_motos"] - prepared["motos_actives"]).clip(lower=0)
    prepared["jours_sans_activite"] = prepared["jours_sans_activite"].where(
        prepared["jours_sans_activite"] > 0,
        inactive_from_motos,
    )
    prepared["month"] = prepared["date"].dt.to_period("M").dt.to_timestamp()
    prepared["week_start"] = prepared["date"] - pd.to_timedelta(prepared["date"].dt.weekday, unit="D")
    return prepared.sort_values("date").reset_index(drop=True)


def prepare_moto_report(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "Date": "date",
        "Periode": "date",
        "Semaine": "date",
        "Moto": "moto_id",
        "moto": "moto_id",
        "Identifiant moto": "moto_id",
        "identifiant_moto": "moto_id",
        "Versement attendu": "versement_attendu",
        "versement attendu": "versement_attendu",
        "montant_attendu": "versement_attendu",
        "Montant attendu": "versement_attendu",
        "Versement recu": "versement_recu",
        "Versement reçu": "versement_recu",
        "versement reçu": "versement_recu",
        "montant_recu": "versement_recu",
        "Montant recu": "versement_recu",
        "Montant reçu": "versement_recu",
    }
    prepared = frame.copy().rename(columns={k: v for k, v in aliases.items() if k in frame.columns})
    missing = [column for column in MOTO_REPORT_COLUMNS if column not in prepared.columns]
    if missing:
        raise ValueError(f"Colonnes rapport motos manquantes: {', '.join(missing)}")
    prepared = prepared[MOTO_REPORT_COLUMNS].copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["moto_id"] = prepared["moto_id"].astype(str).str.strip().str.upper()
    prepared = prepared.dropna(subset=["date"])
    prepared = prepared[prepared["moto_id"] != ""]
    for column in ("versement_attendu", "versement_recu"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0)
    prepared["month"] = prepared["date"].dt.to_period("M").dt.to_timestamp()
    prepared["week_start"] = prepared["date"] - pd.to_timedelta(prepared["date"].dt.weekday, unit="D")
    return prepared.sort_values(["moto_id", "date"]).reset_index(drop=True)


def promote_excel_header(sheet_frame: pd.DataFrame) -> pd.DataFrame:
    header_markers = {
        "date",
        "Date",
        "Periode",
        "week_start",
        "Semaine",
        "Semaine (lundi)",
        "moto_id",
        "Moto",
        "Identifiant moto",
    }
    if any(str(column).strip() in header_markers for column in sheet_frame.columns):
        return sheet_frame
    for row_index in range(min(8, len(sheet_frame))):
        values = [str(value).strip() for value in sheet_frame.iloc[row_index].tolist()]
        if any(value in header_markers for value in values):
            promoted = sheet_frame.iloc[row_index + 1 :].copy()
            promoted.columns = values
            promoted = promoted.loc[:, [column not in {"", "nan", "NaN", "None"} for column in promoted.columns]]
            return promoted.reset_index(drop=True)
    return sheet_frame


def make_sample_moto_report(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    motos = [f"MOTO-{1001 + index}" for index in range(30)]
    for row_index, row in frame.iterrows():
        expected_total = float(row.get("montant_total_attendu", 0))
        received_total = float(row.get("total_collecte", row.get("montant_total_rembourse", 0)))
        expected_weights = np.array([1 + ((stable_offset(moto) + row_index) % 7) / 20 for moto in motos], dtype=float)
        received_weights = np.array([1 + ((stable_offset(moto) + row_index * 3) % 9) / 24 for moto in motos], dtype=float)
        expected_values = expected_total * expected_weights / expected_weights.sum()
        received_values = received_total * received_weights / received_weights.sum()
        for moto, expected, received in zip(motos, expected_values, received_values):
            rows.append(
                {
                    "date": row["date"],
                    "moto_id": moto,
                    "versement_attendu": round(float(expected), 0),
                    "versement_recu": round(float(received), 0),
                }
            )
    return prepare_moto_report(pd.DataFrame(rows))


SAMPLE_DATA = prepare_data(make_sample_data())
MOTO_REPORT_DATA = make_sample_moto_report(SAMPLE_DATA)
DATA_VERSION = 0


def period_options() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    months = [
        {"label": pd.to_datetime(month).strftime("%m/%Y"), "value": pd.to_datetime(month).strftime("%Y-%m")}
        for month in sorted(SAMPLE_DATA["month"].dropna().unique())
    ]
    weeks = [
        {"label": f"Semaine du {pd.to_datetime(week).strftime('%d/%m/%Y')}", "value": pd.to_datetime(week).strftime("%Y-%m-%d")}
        for week in sorted(SAMPLE_DATA["week_start"].dropna().unique())
    ]
    days = [
        {"label": pd.to_datetime(day).strftime("%d/%m/%Y"), "value": pd.to_datetime(day).strftime("%Y-%m-%d")}
        for day in sorted(SAMPLE_DATA["date"].dropna().unique())
    ]
    return months, weeks, days


def default_periods() -> tuple[str, str, str]:
    last_day = SAMPLE_DATA["date"].max()
    return (
        last_day.to_period("M").strftime("%Y-%m"),
        (last_day - pd.Timedelta(days=last_day.weekday())).strftime("%Y-%m-%d"),
        last_day.strftime("%Y-%m-%d"),
    )


def filter_period(selected_day: str, selected_week: str, selected_month: str, mode: str) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    if mode == "daily":
        current_day = pd.to_datetime(selected_day)
        previous_day = current_day - pd.Timedelta(days=1)
        return (
            SAMPLE_DATA[SAMPLE_DATA["date"] == current_day],
            SAMPLE_DATA[SAMPLE_DATA["date"] == previous_day],
            current_day.strftime("%d/%m/%Y"),
            previous_day.strftime("%d/%m/%Y"),
        )
    if mode == "weekly":
        current_start = pd.to_datetime(selected_week)
        previous_start = current_start - pd.Timedelta(days=7)
        return (
            SAMPLE_DATA[(SAMPLE_DATA["date"] >= current_start) & (SAMPLE_DATA["date"] < current_start + pd.Timedelta(days=7))],
            SAMPLE_DATA[(SAMPLE_DATA["date"] >= previous_start) & (SAMPLE_DATA["date"] < previous_start + pd.Timedelta(days=7))],
            f"Semaine du {current_start.strftime('%d/%m/%Y')}",
            f"Semaine du {previous_start.strftime('%d/%m/%Y')}",
        )
    current_month = pd.to_datetime(selected_month + "-01")
    previous_month = current_month - pd.DateOffset(months=1)
    return (
        SAMPLE_DATA[SAMPLE_DATA["month"] == current_month],
        SAMPLE_DATA[SAMPLE_DATA["month"] == previous_month],
        current_month.strftime("%m/%Y"),
        previous_month.strftime("%m/%Y"),
    )


def compute_metrics(frame: pd.DataFrame, mode: str) -> dict[str, float]:
    if frame.empty:
        return {indicator.key: 0 for indicator in INDICATORS}
    sums = frame.sum(numeric_only=True).to_dict()
    avgs = frame.mean(numeric_only=True).to_dict()
    first = frame.iloc[0].to_dict()
    last = frame.iloc[-1].to_dict()
    days = max(len(frame), 1)
    values = {
        "performance_jour": safe_ratio(sums["total_collecte"], sums["montant_total_attendu"]) * 100,
        "performance_hebdomadaire": safe_ratio(sums["total_collecte"], sums["montant_total_attendu"]) * 100,
        "performance_mensuelle": safe_ratio(sums["total_collecte"], sums["montant_total_attendu"]) * 100,

        "montant_moyen": safe_ratio(sums["total_collecte"], last["nombre_beneficiaires"]),
        "motos_actives": float(last.get("motos_actives", 0)),
        "taux_pannes": safe_ratio(sums.get("motos_panne", 0), sums.get("total_motos", 0)) * 100,
        "revenu_moyen_reel": safe_ratio(sums["revenus_apres"], sums["nombre_beneficiaires"]),
        "taux_maintien": safe_ratio(last["beneficiaires_actifs"], first["beneficiaires_initial"]) * 100,
        "volume_transactions_semaine": float(sums.get("transactions", 0)),
        "volume_transactions": float(sums.get("transactions", 0)),
        "nb_utilisateurs_actifs": last["utilisateurs_actifs"],

        "score_discipline": discipline_score_from_sums(sums),
        "top_beneficiaires": last["top_beneficiaires"],
        "flop_beneficiaires": last["flop_beneficiaires"],
    }
    values["hebdo_performance"] = values["performance_hebdomadaire"]
    values["hebdo_motos_actives"] = values["motos_actives"]
    values["rapport_motos"] = float(MOTO_REPORT_DATA["moto_id"].nunique()) if not MOTO_REPORT_DATA.empty else 0
    return values


def format_value(value: float, unit: str) -> str:
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "FCFA":
        return f"{value:,.0f} FCFA".replace(",", " ")
    if unit == "jours":
        return f"{round(value):,.0f} j".replace(",", " ")
    if unit == "/10":
        return f"{value:.1f}/10"
    if unit == "pts":
        return f"{value:.1f} pts"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.1f}"
    return f"{value:,.0f}".replace(",", " ")


def format_delta(value: float, unit: str) -> str:
    return f"{value:+.1f}%"


def format_indicator_delta(indicator: Indicator, value: float) -> str:
    if abs(value) < 0.05:
        return "Stable"
    return f"{value:+.1f}%"


def alert_for(indicator: Indicator, value: float) -> tuple[str, str, str]:
    if indicator.good is None or indicator.watch is None:
        return "info", "A suivre", INFO
    if indicator.higher_is_better:
        if value >= indicator.good:
            return "ok", "Excellent", BRAND
        if value >= indicator.watch:
            return "watch", "Acceptable", WARNING
        return "danger", "Alert", DANGER
    if value < indicator.good:
        return "ok", "Bon", BRAND
    if value <= indicator.watch:
        return "watch", "A surveiller", WARNING
    return "danger", "Alert", DANGER


FREQUENCY_LABELS = {
    "daily": "Quotidien",
    "weekly": "Hebdomadaire",
    "monthly": "Mensuel",
}


def indicator_modes(indicator: Indicator) -> list[str]:
    if indicator.frequency == "all":
        return ["daily", "weekly", "monthly"]
    if indicator.frequency == "both":
        return ["weekly", "monthly"]
    return [indicator.frequency]


def frequency_options(indicator: Indicator) -> list[dict[str, str]]:
    return [{"label": FREQUENCY_LABELS[mode], "value": mode} for mode in indicator_modes(indicator)]


def group_frequency_options(group: str) -> list[dict[str, str]]:
    available_modes = {
        mode
        for indicator in indicators_for_group(group)
        for mode in indicator_modes(indicator)
    }
    return [
        {"label": FREQUENCY_LABELS[mode], "value": mode}
        for mode in ("daily", "weekly", "monthly")
        if mode in available_modes
    ]


def default_mode_for_indicator(indicator: Indicator) -> str:
    return frequency_options(indicator)[0]["value"]


def period_context(selected_day: str, selected_week: str, selected_month: str) -> dict[str, dict]:
    context = {}
    for mode in ("daily", "weekly", "monthly"):
        current, previous, current_label, previous_label = filter_period(selected_day, selected_week, selected_month, mode)
        context[mode] = {
            "current": current,
            "previous": previous,
            "current_label": current_label,
            "previous_label": previous_label,
            "values": compute_metrics(current, mode),
        }
    return context


def indicator_value(indicator: Indicator, context: dict[str, dict]) -> float:
    mode = default_mode_for_indicator(indicator)
    return context[mode]["values"].get(indicator.key, 0)


def group_options() -> list[dict[str, str]]:
    return [{"label": label, "value": key} for key, label in GROUPS.items()]


def indicators_for_group(group: str, mode: str | None = None) -> list[Indicator]:
    indicators = [indicator for indicator in INDICATORS if indicator.group == group]
    if mode is None:
        return indicators
    return [indicator for indicator in indicators if mode in indicator_modes(indicator)]


def indicator_options(group: str, mode: str | None = None) -> list[dict[str, str]]:
    return [{"label": indicator.name, "value": indicator.key} for indicator in indicators_for_group(group, mode)]



# Map hidden groups (removed from GROUPS) to visible ones for dashboard rendering
HIDDEN_GROUP_REMAP = {
    "risque": "financier",
    "terrain": "operationnel",
}


def source_indicator_key(indicator_key: str) -> str:
    """Resolve a hebdo alias to its real source indicator key."""
    return HEBDO_SOURCE_INDICATORS.get(indicator_key, indicator_key)


def source_group_for_indicator(indicator_key: str) -> str:
    """Get the visible group for an indicator, resolving hebdo aliases first."""
    real_key = source_indicator_key(indicator_key)
    key = real_key if real_key in INDICATOR_BY_KEY else indicator_key
    if key in INDICATOR_BY_KEY:
        group = INDICATOR_BY_KEY[key].group
        return HIDDEN_GROUP_REMAP.get(group, group)
    return "financier"


def kpi_card(title: str, value: str, status: str, color: str, button_id: dict | None = None) -> html.Div:
    children = [
        html.Div(html.Span(status, className="alert", style={"backgroundColor": color}), className="card-top"),
        html.H3(title),
    ]
    if value:
        children.append(html.Div(value, className="big-value"))
    if button_id:
        return html.Button(children, id=button_id, n_clicks=0, className="kpi-card clickable-card", style={"borderTopColor": color}, type="button")
    return html.Div(children, className="kpi-card", style={"borderTopColor": color})


def indicator_card(indicator: Indicator, values: dict[str, float]) -> html.Div:
    _, status, color = alert_for(indicator, values.get(indicator.key, 0))
    return kpi_card(
        indicator.name,
        "" if indicator.key in {"top_beneficiaires", "flop_beneficiaires"} else format_value(values.get(indicator.key, 0), indicator.unit),
        status,
        color,
        {"type": "indicator-button", "indicator": indicator.key},
    )


def indicator_context_card(indicator: Indicator, context: dict[str, dict]) -> html.Div:
    value = indicator_value(indicator, context)
    _, status, color = alert_for(indicator, value)
    return kpi_card(
        indicator.name,
        format_value(value, indicator.unit),
        status,
        color,
        {"type": "indicator-button", "indicator": indicator.key},
    )


def selected_value_card(indicator: Indicator, value: float) -> html.Div:
    _, status, color = alert_for(indicator, value)
    return kpi_card(indicator.name, format_value(value, indicator.unit), status, color)


def grouped_indicators_by_alert(group: str, context: dict[str, dict]) -> tuple[list[Indicator], list[Indicator]]:
    alert_items = []
    watch_items = []
    for indicator in indicators_for_group(group):
        state, _, _ = alert_for(indicator, indicator_value(indicator, context))
        if state == "danger":
            alert_items.append(indicator)
        elif state == "watch":
            watch_items.append(indicator)
    return alert_items, watch_items


def group_has_alert(group: str, context: dict[str, dict]) -> bool:
    alert_items, _ = grouped_indicators_by_alert(group, context)
    return bool(alert_items)


def indicator_section(title: str, description: str, indicators: list[Indicator], context: dict[str, dict], empty_text: str, class_name: str = "alert-section") -> html.Div:
    if indicators:
        body = html.Div([indicator_context_card(indicator, context) for indicator in indicators], className="cards-grid alert-grid")
    else:
        body = html.Div([kpi_card(empty_text, "OK", "Stable", BRAND)], className="cards-grid single-indicator-grid")
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Alert" if "alerte" in title.lower() else "Suivi", className="eyebrow"),
                    html.H2(title),
                    html.P(description),
                ],
                className="section-title",
            ),
            body,
        ],
        className=class_name,
    )


def alert_indicators_for_group(group: str, values: dict[str, float], mode: str) -> list[Indicator]:
    alerts = []
    for indicator in indicators_for_group(group):
        allowed_modes = {option["value"] for option in frequency_options(indicator)}
        if mode not in allowed_modes:
            continue
        state, _, _ = alert_for(indicator, values.get(indicator.key, 0))
        if state == "danger":
            alerts.append(indicator)
    return alerts


def alert_cause_count(indicator: Indicator, frame: pd.DataFrame, values: dict[str, float]) -> int:
    if frame.empty:
        return 0
    state, _, _ = alert_for(indicator, values.get(indicator.key, 0))
    if state not in {"danger", "watch"} and indicator.key not in OPERATIONAL_MOTO_INDICATORS:
        return 0
    last = frame.iloc[-1]
    sums = frame.sum(numeric_only=True).to_dict()
    key = indicator.key
    count = 0

    if key in {"motos_actives", "hebdo_motos_actives"}:
        count = int(max(last["total_motos"] - last["motos_actives"], 0))
    elif key in {"taux_pannes"}:
        count = int(max(last["motos_panne"], 0))
    elif key in FINANCIAL_PERFORMANCE_INDICATORS:
        count = int(max(sums.get("paiements_temps", 0), last.get("paiements_temps", 0)))
    elif key in {"taux_paiement_temps", "hebdo_performance"}:
        count = int(max(sums.get("paiements_attendus", 0) - sums.get("paiements_temps", 0), last.get("beneficiaires_retard", 0)))
    elif key in {"flop_beneficiaires", "score_discipline"}:
        count = int(max(values.get("flop_beneficiaires", 0), last.get("flop_beneficiaires", 0)))
    return max(count, 0)


def involved_title(indicator: Indicator) -> str:
    if indicator.key in FINANCIAL_PERFORMANCE_INDICATORS:
        return "Bénéficiaires défaillants"
    if indicator.key in INACTIVE_MOTO_INDICATORS:
        return "Motos inactives"
    if indicator.key == "taux_pannes":
        return "Motos en panne"
    if indicator.key in OPERATIONAL_MOTO_INDICATORS:
        return "Motos impliquees"
    return "Beneficiaires impliques"


def involved_description(indicator: Indicator) -> str:
    if indicator.key in FINANCIAL_PERFORMANCE_INDICATORS:
        return "Liste des bénéficiaires avec leur taux de versement sur la période actuelle et précédente."
    if indicator.key in INACTIVE_MOTO_INDICATORS:
        return "Liste filtrée des motos inactives qui causent l'alerte de l'indicateur sélectionné."
    if indicator.key == "taux_pannes":
        return "Liste filtree des motos en panne qui causent l'alerte de l'indicateur selectionne."
    if indicator.key in OPERATIONAL_MOTO_INDICATORS:
        return "Liste des motos liees a l'indicateur operationnel selectionne."
    return "Liste filtree des codes, telephones et motos qui causent l'alerte de l'indicateur selectionne."


def alert_cause_category(indicator: Indicator) -> str:
    if indicator.key in OPERATIONAL_MOTO_INDICATORS:
        return "Moto"
    return "Beneficiaire"


def is_inactive_moto_indicator(indicator: Indicator) -> bool:
    return indicator.key in INACTIVE_MOTO_INDICATORS


def involved_note(indicator: Indicator, index: int, frame: pd.DataFrame, values: dict[str, float]) -> str:
    last = frame.iloc[-1]
    key = indicator.key
    if key in FINANCIAL_PERFORMANCE_INDICATORS:
        return "Paiement recu"
    if key in INACTIVE_MOTO_INDICATORS:
        suffix = {"daily": "J", "weekly": "S", "monthly": "M"}.get(values.get("__mode"), "S")
        return f"{max(0, int(last['total_motos'] - last['motos_actives']))} {suffix} inactif"
    if key == "taux_pannes":
        return "Panne signalee"
    if key in {"taux_paiement_temps", "hebdo_performance"}:
        return "Paiement attendu non regularise"
    if key in {"par7", "hebdo_par7"}:
        return "Encours en retard > 7 j"
    if key in {"taux_defaut"}:
        return "Cas de defaut"
    if key in {"flop_beneficiaires", "score_discipline"}:
        return "Score discipline faible"
    return indicator.name


def alert_cause_rows(indicator: Indicator, frame: pd.DataFrame, previous_frame: pd.DataFrame, values: dict[str, float]) -> list[dict[str, str]]:
    if frame.empty:
        return []
    last = frame.iloc[-1]
    
    if indicator.key == "score_discipline":
        sums = frame.sum(numeric_only=True).to_dict()
        base_components = discipline_components_from_sums(sums)
        rows = []
        prev_sums = previous_frame.sum(numeric_only=True).to_dict() if not previous_frame.empty else {}
        prev_base_score = discipline_score_from_sums(prev_sums) if prev_sums else 0
        
        for i, nom in enumerate(MOCK_NAMES):
            moto = f"MOTO-{1000 + i}"
            offset = (stable_offset(f"{nom}-{moto}") % 31) - 15
            paiement_temps = clamp_percent(base_components["paiement_temps"] + offset * 0.7)
            activite = clamp_percent(base_components["activite"] + offset * 0.9)
            entretien = clamp_percent(base_components["entretien"] + offset * 0.5)
            score = safe_ratio(
                paiement_temps * DISCIPLINE_WEIGHTS["paiement_temps"]
                + activite * DISCIPLINE_WEIGHTS["activite"]
                + entretien * DISCIPLINE_WEIGHTS["entretien"],
                DISCIPLINE_WEIGHT_TOTAL,
            )
            score_prec = max(0, min(100, prev_base_score + (stable_offset(nom) % 40) - 20)) if prev_sums else 0
            rows.append({
                "nom": nom,
                "telephone": f"+237 6{70 + (i % 20):02d} {110 + i:03d} {220 + i:03d}",
                "moto": moto,
                "paiement_temps": f"{paiement_temps:.1f}%",
                "activite": f"{activite:.1f}%",
                "entretien": f"{entretien:.1f}%",
                "score_discipline": f"{score:.1f}%",
                "score_discipline_prec": f"{score_prec:.1f}%",
            })
        rows.sort(key=lambda x: x["nom"])
        return rows

    rows = []
    category = alert_cause_category(indicator)
    row_limit = 20 if category == "Moto" else 8
    count = min(alert_cause_count(indicator, frame, values), row_limit)
    for index in range(count):
        phone = f"+237 6{70 + (index % 20):02d} {110 + index:03d} {220 + index:03d}"
        name = mock_beneficiary_name(index, indicator.key)
        note = involved_note(indicator, index, frame, values)
        moto = f"MOTO-{1000 + index + 1}"
        r = {
            "nom": name,
            "telephone": phone,
            "moto": moto,
        }
        
        if is_inactive_moto_indicator(indicator):
            r["taux_inactivite"] = note
            mode = values.get("__mode", "weekly")
            prev_values = compute_metrics(previous_frame, mode) if not previous_frame.empty else {}
            prev_values["__mode"] = mode
            r["taux_inactivite_prec"] = involved_note(indicator, index, previous_frame, prev_values) if not previous_frame.empty else "N/A"

            last = frame.iloc[-1]
            jours_total = float(last["jours_totaux"]) if "jours_totaux" in last else 0.0
            base_actifs = float(last["jours_actifs"]) if "jours_actifs" in last else 0.0

            # Per-row (moto) values: deterministic small variation by index
            delta_actifs = (index % 5) - 2
            jours_actifs_row = max(0.0, min(jours_total if jours_total > 0 else base_actifs, base_actifs + delta_actifs))
            r["jours_activite"] = format_value(jours_actifs_row, "")

            if not previous_frame.empty:
                prev_last = previous_frame.iloc[-1]
                prev_total = float(prev_last["jours_totaux"]) if "jours_totaux" in prev_last else 0.0
                base_inactifs = float(prev_last["jours_sans_activite"]) if "jours_sans_activite" in prev_last else 0.0
                delta_inactifs = (index % 3) - 1
                jours_inactifs_prev_row = max(0.0, min(prev_total if prev_total > 0 else base_inactifs, base_inactifs + delta_inactifs))
                r["jours_inactivite_prec"] = format_value(jours_inactifs_prev_row, "")
            else:
                r["jours_inactivite_prec"] = "N/A"
        else:
            r["note"] = note
            
        rows.append(r)
    return rows


@lru_cache(maxsize=256)
def involved_timeseries_cached(indicator_key: str, mode: str, data_version: int) -> tuple[tuple[pd.Timestamp, float], ...]:
    indicator = INDICATOR_BY_KEY[indicator_key]
    rows = []
    if mode == "daily":
        groups = SAMPLE_DATA.groupby("date")
    elif mode == "weekly":
        groups = SAMPLE_DATA.groupby("week_start")
    else:
        groups = SAMPLE_DATA.groupby("month")
    for period, frame in groups:
        values = {indicator.key: fast_indicator_value(indicator, frame, mode)}
        rows.append({"periode": period, "value": alert_cause_count(indicator, frame, values)})
    return tuple((row["periode"], row["value"]) for row in rows)


def involved_timeseries(indicator: Indicator, mode: str) -> pd.DataFrame:
    rows = involved_timeseries_cached(indicator.key, mode, DATA_VERSION)
    return pd.DataFrame(rows, columns=["periode", "value"])


def fast_indicator_value(indicator: Indicator, frame: pd.DataFrame, mode: str) -> float:
    if frame.empty:
        return 0
    key = indicator.key
    sums = frame.sum(numeric_only=True).to_dict()
    first = frame.iloc[0].to_dict()
    last = frame.iloc[-1].to_dict()
    days = max(len(frame), 1)

    if key in FINANCIAL_PERFORMANCE_INDICATORS:
        return safe_ratio(sums["total_collecte"], sums["montant_total_attendu"]) * 100
    if key in {"motos_actives", "hebdo_motos_actives"}:
        return float(last.get("motos_actives", 0))
    if key == "taux_pannes":
        return safe_ratio(sums.get("motos_panne", 0), sums.get("total_motos", 0)) * 100
    if key == "score_discipline":
        return discipline_score_from_sums(sums)
    if key == "top_beneficiaires":
        return last["top_beneficiaires"]
    if key == "flop_beneficiaires":
        return last["flop_beneficiaires"]
    if key == "taux_visites":
        return safe_ratio(sums["visites_prevues"], sums["visites_realisees"]) * 100
    if key == "motos_visitees":
        total_motos = last["total_motos"] if last.get("total_motos", 0) > 0 else sums["visites_realisees"]
        return min(sums["visites_realisees"], total_motos)
    if key == "taux_maintien":
        return safe_ratio(last["beneficiaires_actifs"], first["beneficiaires_initial"]) * 100
    return compute_metrics(frame, mode).get(key, 0)


def build_involved_trend_chart(indicator: Indicator, mode: str) -> go.Figure:
    series = involved_timeseries(indicator, mode)
    fig = go.Figure()

    if mode == "weekly" and not series.empty:
        labels = [f"Sem {int(p.strftime('%W'))} - {p.strftime('%d %b')}" for p in series["periode"]]
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=series["value"],
                mode="lines+markers",
                line={"color": DANGER, "width": 3},
                marker={"size": 8, "color": DANGER},
                fill="tozeroy",
                fillcolor="rgba(185, 28, 28, 0.10)",
                hovertemplate="<b>%{x}</b><br>Impliques: %{y}<extra></extra>",
            )
        )
        fig.update_xaxes(showgrid=False, tickangle=-40)
    else:
        fig.add_trace(
            go.Scatter(
                x=series["periode"],
                y=series["value"],
                mode="lines+markers",
                line={"color": DANGER, "width": 3},
                marker={"size": 7, "color": DANGER},
                fill="tozeroy",
                fillcolor="rgba(185, 28, 28, 0.10)",
                hovertemplate="<b>%{x|%b %Y}</b><br>Impliques: %{y}<extra></extra>",
            )
        )
        if mode == "daily":
            fig.update_xaxes(showgrid=False, tickformat="%d %b")
        else:
            fig.update_xaxes(showgrid=False, tickformat="%b %Y")

    fig.update_layout(
        height=310,
        margin={"l": 20, "r": 20, "t": 20, "b": 55},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
        font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": "#111827"},
    )
    fig.update_yaxes(title="Impliques", gridcolor="#edf2f7", zerolinecolor="#dbe3ea", rangemode="tozero")
    return fig


def top_inactive_motos(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["moto", "beneficiaire", "label", "value"])
    total_motos = int(max(frame["total_motos"].max(), 0))
    if total_motos <= 0:
        return pd.DataFrame(columns=["moto", "beneficiaire", "label", "value"])
    top_n = min(20, total_motos)
    inactive_events = int(max((frame["total_motos"] - frame["motos_actives"]).clip(lower=0).sum(), 0))
    if inactive_events <= 0:
        values = [0 for _ in range(top_n)]
    else:
        weights = np.arange(top_n, 0, -1, dtype=float)
        raw_values = inactive_events * weights / weights.sum()
        values = np.maximum(1, np.rint(raw_values).astype(int)).tolist()
    motos = [f"MOTO-{1000 + index + 1}" for index in range(top_n)]
    names = [mock_beneficiary_name(index, "motos_inactives") for index in range(top_n)]
    return pd.DataFrame(
        {
            "moto": motos,
            "beneficiaire": names,
            "label": [f"{moto} - {name}" for moto, name in zip(motos, names)],
            "value": values,
        }
    ).sort_values("value", ascending=True)


def build_top_inactive_motos_chart(frame: pd.DataFrame) -> go.Figure:
    series = top_inactive_motos(frame)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=series["value"],
            y=series["label"],
            orientation="h",
            marker_color=DANGER,
            text=series["value"],
            textposition="auto",
            customdata=np.stack([series["moto"], series["beneficiaire"]], axis=-1) if not series.empty else None,
            hovertemplate="<b>%{customdata[0]}</b><br>Beneficiaire: %{customdata[1]}<br>Inactivite: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        height=520,
        margin={"l": 170, "r": 20, "t": 20, "b": 35},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
        font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": "#111827"},
    )
    fig.update_xaxes(title="Jours / occurrences d'inactivite", gridcolor="#edf2f7", zerolinecolor="#dbe3ea", rangemode="tozero")
    fig.update_yaxes(showgrid=False)
    return fig


def discipline_ranking(frame: pd.DataFrame, is_top: bool) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["beneficiaire", "value", "nom"])
    
    sums = frame.sum(numeric_only=True).to_dict()
    base_score = discipline_score_from_sums(sums)
    
    top_n = 20
    names = MOCK_NAMES[:top_n]
    if is_top:
        max_score = min(100, base_score + 15)
        min_score = min(max_score, base_score + 5)
        values = np.linspace(max_score, min_score, top_n).round(1).tolist()
    else:
        min_score = max(0, base_score - 25)
        max_score = max(min_score, base_score - 10)
        values = np.linspace(min_score, max_score, top_n).round(1).tolist()
        
    return pd.DataFrame(
        {
            "beneficiaire": names,
            "value": values,
            "nom": names,
        }
    ).sort_values("value", ascending=True)


def build_discipline_ranking_chart(frame: pd.DataFrame, is_top: bool) -> go.Figure:
    series = discipline_ranking(frame, is_top)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=series["value"],
            y=series["beneficiaire"],
            orientation="h",
            marker_color=BRAND if is_top else DANGER,
            text=[f"{v:.1f}%" for v in series["value"]],
            textposition="auto",
        )
    )
    fig.update_layout(
        height=520,
        margin={"l": 88, "r": 20, "t": 20, "b": 35},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
        font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": "#111827"},
    )
    fig.update_xaxes(title="Score de discipline (%)", gridcolor="#edf2f7", zerolinecolor="#dbe3ea", rangemode="tozero", range=[0, 100])
    fig.update_yaxes(showgrid=False)
    return fig


def involved_visual_title(indicator: Indicator) -> str:
    if indicator.key in FINANCIAL_PERFORMANCE_INDICATORS:
        return "Montants attendus vs recus"
    if is_inactive_moto_indicator(indicator):
        return "Top 20 des motos les plus inactives"
    if indicator.key == "top_beneficiaires":
        return "Top 20 des plus disciplinés"
    if indicator.key == "flop_beneficiaires":
        return "Top 20 des plus indisciplinés"
    return f"Tendance - {involved_title(indicator)}"


def involved_visual_description(indicator: Indicator) -> str:
    if indicator.key in FINANCIAL_PERFORMANCE_INDICATORS:
        return "Comparaison des montants attendus et recus pour les 20 premiers beneficiaires de la liste."
    if is_inactive_moto_indicator(indicator):
        return "Classement des motos qui concentrent le plus d'inactivite sur la periode selectionnee."
    if indicator.key == "top_beneficiaires":
        return "Classement des 20 beneficiaires ayant les meilleurs scores de discipline."
    if indicator.key == "flop_beneficiaires":
        return "Classement des 20 beneficiaires ayant les moins bons scores de discipline."
    return "Evolution du nombre d'elements impliques dans l'alerte de cet indicateur."


def build_involved_visual(indicator: Indicator, frame: pd.DataFrame, previous_frame: pd.DataFrame, mode: str) -> go.Figure:
    if indicator.key in FINANCIAL_PERFORMANCE_INDICATORS:
        return build_payment_amounts_chart(frame, previous_frame)
    if is_inactive_moto_indicator(indicator):
        return build_top_inactive_motos_chart(frame)
    if indicator.key == "top_beneficiaires":
        return build_discipline_ranking_chart(frame, True)
    if indicator.key == "flop_beneficiaires":
        return build_discipline_ranking_chart(frame, False)
    return build_involved_trend_chart(indicator, mode)


def beneficiary_payment_rows(frame: pd.DataFrame, previous_frame: pd.DataFrame) -> list[dict[str, str]]:
    if frame.empty:
        return []
    sums = frame.sum(numeric_only=True).to_dict()
    last = frame.iloc[-1]
    count = int(max(last.get("nombre_beneficiaires", 0), sums.get("paiements_attendus", 0), 0))
    if count <= 0:
        return []

    expected_each = safe_ratio(sums.get("montant_total_attendu", 0), count)
    raw = []
    for index in range(count):
        name = f"{mock_beneficiary_name(index, 'beneficiaire_paiement')} {index + 1:03d}"
        factor = 0.82 + ((stable_offset(name) % 37) / 100)
        raw.append(expected_each * factor)
    raw_total = sum(raw)
    scale = safe_ratio(sums.get("total_collecte", 0), raw_total)

    rows = []
    
    prev_sums = previous_frame.sum(numeric_only=True).to_dict() if not previous_frame.empty else {}
    prev_count = int(max(previous_frame.iloc[-1].get("nombre_beneficiaires", 0) if not previous_frame.empty else 0, prev_sums.get("paiements_attendus", 0), 0))
    prev_expected_each = safe_ratio(prev_sums.get("montant_total_attendu", 0), prev_count) if prev_count > 0 else 0
    prev_raw = [prev_expected_each * (0.82 + ((stable_offset(f"{mock_beneficiary_name(i, 'beneficiaire_paiement')} {i + 1:03d}") % 37) / 100)) for i in range(prev_count)]
    prev_scale = safe_ratio(prev_sums.get("total_collecte", 0), sum(prev_raw)) if prev_raw else 0
    
    for index, raw_received in enumerate(raw):
        montant_attendu_val = expected_each
        montant_recu_val = max(0, raw_received * scale)
        performance_val = safe_ratio(montant_recu_val, montant_attendu_val) * 100
        
        prev_perf_val = 0
        if index < len(prev_raw):
            prev_attendu = prev_expected_each
            prev_recu = max(0, prev_raw[index] * prev_scale)
            prev_perf_val = safe_ratio(prev_recu, prev_attendu) * 100

        rows.append(
            {
                "nom": f"{mock_beneficiary_name(index, 'beneficiaire_paiement')} {index + 1:03d}",
                "telephone": f"+237 6{70 + (index % 20):02d} {110 + index:03d} {220 + index:03d}",
                "moto": f"MOTO-{1000 + index + 1}",
                "performance": format_value(performance_val, "%"),
                "performance_prec": format_value(prev_perf_val, "%"),
                "raw_perf": performance_val,
                "raw_perf_prec": prev_perf_val,
            }
        )
    return rows


def beneficiary_payment_table(frame: pd.DataFrame, previous_frame: pd.DataFrame, mode: str) -> html.Div:
    rows = beneficiary_payment_rows(frame, previous_frame)
    if not rows:
        return html.Div()

    suffix = {"daily": "J", "weekly": "S", "monthly": "M"}.get(mode, "S")

    return html.Div(
        [
            html.Div(
                [
                    html.H3("Bénéficiaires défaillants"),
                    html.P("Liste des bénéficiaires avec leur taux de versement actuel et celui de la période précédente."),
                ],
                className="chart-copy",
            ),
            html.Div(
                html.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Nom beneficiaire"),
                                    html.Th("Telephone"),
                                    html.Th("Moto"),
                                    html.Th(f"Tx versement reçu/attendu ({suffix})"),
                                    html.Th(f"Tx versement reçu/attendu ({suffix}-1)"),
                                ]
                            )
                        ),
                        html.Tbody(
                            [
                                html.Tr(
                                    [
                                        html.Td(row["nom"]),
                                        html.Td(row["telephone"]),
                                        html.Td(row["moto"]),
                                        html.Td(row["performance"]),
                                        html.Td(row["performance_prec"]),
                                    ]
                                )
                                for row in rows
                            ]
                        ),
                    ],
                    className="cause-table",
                ),
                className="table-scroll",
            ),
        ],
        id="involved-section",
        className="chart-panel involved-panel",
    )


def build_payment_amounts_chart(frame: pd.DataFrame, previous_frame: pd.DataFrame) -> go.Figure:
    rows = beneficiary_payment_rows(frame, previous_frame)[:20]
    fig = go.Figure()
    labels = [row["nom"] for row in rows]
    current_perf = [row["raw_perf"] for row in rows]
    prev_perf = [row["raw_perf_prec"] for row in rows]
    fig.add_trace(go.Bar(name="Versement (S-1)", x=labels, y=prev_perf, marker_color="#94a3b8"))
    fig.add_trace(go.Bar(name="Versement (S)", x=labels, y=current_perf, marker_color=ACCENT))
    fig.update_layout(
        height=420,
        barmode="group",
        margin={"l": 20, "r": 20, "t": 20, "b": 110},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend={"orientation": "h", "y": 1.08, "x": 0},
        font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": "#111827"},
    )
    fig.update_yaxes(title="Versement (%)", gridcolor="#edf2f7", zerolinecolor="#dbe3ea", rangemode="tozero")
    fig.update_xaxes(showgrid=False, tickangle=-45)
    return fig


def alert_cause_table(indicator: Indicator, frame: pd.DataFrame, previous_frame: pd.DataFrame, values: dict[str, float]) -> html.Div:
    if indicator.key in {"top_beneficiaires", "flop_beneficiaires"}:
        return html.Div()
    if indicator.key in FINANCIAL_PERFORMANCE_INDICATORS:
        return beneficiary_payment_table(frame, previous_frame, values.get("__mode", "weekly"))
    rows = alert_cause_rows(indicator, frame, previous_frame, values)
    return involved_table_from_rows(rows, involved_title(indicator), involved_description(indicator), values.get("__mode", "weekly"))


def involved_table_from_rows(rows: list[dict[str, str]], title: str, description: str, mode: str = "weekly") -> html.Div:
    if not rows:
        return html.Div()

    suffix = {"daily": "J", "weekly": "S", "monthly": "M"}.get(mode, "S")
    
    # We define the order of columns to display
    ordered_keys = ["nom", "telephone", "moto", "paiement_temps", "activite", "entretien", "jours_activite", "jours_inactivite_prec", "taux_inactivite", "taux_inactivite_prec", "score_discipline", "score_discipline_prec", "note", "note_prec", "date_visite"]
    
    key_to_header = {
        "nom": "Nom",
        "telephone": "Téléphone",
        "moto": "Moto",
        "paiement_temps": "Paiements a temps",
        "activite": "Activite",
        "entretien": "Entretien",
        "jours_activite": f"Jours d'activité ({suffix})",
        "jours_inactivite_prec": f"Jours d'inactivité ({suffix}-1)",
        "taux_inactivite": f"Taux d'inactivité ({suffix})",
        "taux_inactivite_prec": f"Taux d'inactivité ({suffix}-1)",
        "score_discipline": "Score disciplinaire",
        "score_discipline_prec": "Score disciplinaire précédent",
        "note": "Note",
        "note_prec": "Note précédente",
        "date_visite": "Date de visite terrain"
    }
    
    # Get all keys present in the rows
    available_keys = []
    for k in ordered_keys:
        if any(k in r for r in rows):
            available_keys.append(k)
            
    headers = [html.Th(key_to_header[k]) for k in available_keys]
        
    tbody_rows = []
    for r in rows:
        tds = [html.Td(r.get(k, "")) for k in available_keys]
        tbody_rows.append(html.Tr(tds))

    return html.Div(
        [
            html.Div(
                [
                    html.H3(title),
                    html.P(description),
                ],
                className="chart-copy",
            ),
            html.Table(
                [
                    html.Thead(html.Tr(headers)),
                    html.Tbody(tbody_rows),
                ],
                className="cause-table",
            ),
        ],
        id="involved-section",
        className="chart-panel involved-panel",
    )


def delta_status(indicator: Indicator, delta: float) -> tuple[str, str]:
    if delta == 0:
        return "Ecart stable", INFO
    favorable = delta > 0 if indicator.higher_is_better else delta < 0
    return ("Ecart favorable", BRAND) if favorable else ("Ecart defavorable", DANGER)


def build_comparison_chart(indicator: Indicator, current_value: float, previous_value: float, current_label: str, previous_label: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[previous_label, current_label],
            y=[previous_value, current_value],
            marker_color=["#94a3b8", ACCENT],
            text=[format_value(previous_value, indicator.unit), format_value(current_value, indicator.unit)],
            textposition="auto",
        )
    )
    fig.update_layout(
        height=345,
        margin={"l": 20, "r": 20, "t": 20, "b": 35},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
        font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": "#111827"},
    )
    fig.update_yaxes(gridcolor="#edf2f7", zerolinecolor="#dbe3ea")
    fig.update_xaxes(showgrid=False)
    return fig


@lru_cache(maxsize=256)
def indicator_timeseries_cached(indicator_key: str, mode: str, data_version: int) -> tuple[tuple[pd.Timestamp, float], ...]:
    indicator = INDICATOR_BY_KEY[indicator_key]
    rows = []
    if mode == "daily":
        for day, frame in SAMPLE_DATA.groupby("date"):
            rows.append({"periode": day, "value": fast_indicator_value(indicator, frame, "daily")})
    elif mode == "weekly":
        for week, frame in SAMPLE_DATA.groupby("week_start"):
            rows.append({"periode": week, "value": fast_indicator_value(indicator, frame, "weekly")})
    else:
        for month, frame in SAMPLE_DATA.groupby("month"):
            rows.append({"periode": month, "value": fast_indicator_value(indicator, frame, "monthly")})
    return tuple((row["periode"], row["value"]) for row in rows)


def indicator_timeseries(indicator: Indicator, mode: str) -> pd.DataFrame:
    rows = indicator_timeseries_cached(indicator.key, mode, DATA_VERSION)
    return pd.DataFrame(rows, columns=["periode", "value"])


def build_trend_chart(indicator: Indicator, mode: str) -> go.Figure:
    series = indicator_timeseries(indicator, mode)
    fig = go.Figure()

    if mode == "weekly" and not series.empty:
        labels = [f"Sem {int(p.strftime('%W'))} - {p.strftime('%d %b')}" for p in series["periode"]]
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=series["value"],
                mode="lines+markers",
                line={"color": ACCENT, "width": 3},
                marker={"size": 8, "color": ACCENT},
                fill="tozeroy",
                fillcolor="rgba(15, 118, 110, 0.11)",
                hovertemplate="<b>%{x}</b><br>Valeur: %{y:.1f} " + indicator.unit + "<extra></extra>",
            )
        )
        fig.update_xaxes(showgrid=False, tickangle=-40)
    else:
        fig.add_trace(
            go.Scatter(
                x=series["periode"],
                y=series["value"],
                mode="lines+markers",
                line={"color": ACCENT, "width": 3},
                marker={"size": 7, "color": ACCENT},
                fill="tozeroy",
                fillcolor="rgba(15, 118, 110, 0.11)",
                hovertemplate="<b>%{x|%b %Y}</b><br>Valeur: %{y:.1f} " + indicator.unit + "<extra></extra>",
            )
        )
        if mode == "daily":
            fig.update_xaxes(showgrid=False, tickformat="%d %b")
        else:
            fig.update_xaxes(showgrid=False, tickformat="%b %Y")

    fig.update_layout(
        height=345,
        margin={"l": 20, "r": 20, "t": 20, "b": 55},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        showlegend=False,
        font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": "#111827"},
    )
    fig.update_yaxes(title=indicator.unit, gridcolor="#edf2f7", zerolinecolor="#dbe3ea")
    return fig


def moto_options() -> list[dict[str, str]]:
    if MOTO_REPORT_DATA.empty:
        return []
    return [
        {"label": moto, "value": moto}
        for moto in sorted(MOTO_REPORT_DATA["moto_id"].dropna().unique())
    ]


def default_moto_id() -> str | None:
    options = moto_options()
    return options[0]["value"] if options else None


def moto_report_frequency_frame(moto_id: str | None, mode: str) -> pd.DataFrame:
    if not moto_id or MOTO_REPORT_DATA.empty:
        return pd.DataFrame(columns=["periode", "versement_attendu", "versement_recu", "taux_versement"])
    frame = MOTO_REPORT_DATA[MOTO_REPORT_DATA["moto_id"] == str(moto_id).upper()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["periode", "versement_attendu", "versement_recu", "ecart", "taux_versement"])
    if mode == "weekly":
        grouped = frame.groupby("week_start", as_index=False)[["versement_attendu", "versement_recu"]].sum()
        grouped = grouped.rename(columns={"week_start": "periode"})
    elif mode == "monthly":
        grouped = frame.groupby("month", as_index=False)[["versement_attendu", "versement_recu"]].sum()
        grouped = grouped.rename(columns={"month": "periode"})
    else:
        grouped = frame.groupby("date", as_index=False)[["versement_attendu", "versement_recu"]].sum()
        grouped = grouped.rename(columns={"date": "periode"})
    grouped["taux_versement"] = grouped.apply(
        lambda row: safe_ratio(row["versement_recu"], row["versement_attendu"]) * 100,
        axis=1,
    )
    grouped["ecart"] = grouped["versement_attendu"] - grouped["versement_recu"]
    return grouped.sort_values("periode", ascending=False).reset_index(drop=True)


def moto_report_cumulative_to_last_payment(moto_id: str | None) -> tuple[float, pd.Timestamp | None]:
    if not moto_id or MOTO_REPORT_DATA.empty:
        return 0.0, None
    frame = MOTO_REPORT_DATA[MOTO_REPORT_DATA["moto_id"] == str(moto_id).upper()].copy()
    if frame.empty:
        return 0.0, None
    last_payment_date = frame.loc[frame["versement_recu"] > 0, "date"].max()
    if pd.isna(last_payment_date):
        return 0.0, None
    cumulative = frame.loc[frame["date"] <= last_payment_date, "versement_recu"].sum()
    return float(cumulative), pd.to_datetime(last_payment_date)


def moto_report_download_frame(moto_id: str | None, mode: str) -> pd.DataFrame:
    frame = moto_report_frequency_frame(moto_id, mode)
    if frame.empty:
        return pd.DataFrame(columns=["Moto", "Frequence", "Periode", "Versement attendu", "Versement recu", "Ecart", "Taux de versement"])
    export = frame.copy()
    export.insert(0, "moto_id", str(moto_id).upper())
    export.insert(1, "frequence", FREQUENCY_LABELS.get(mode, mode))
    export["periode"] = export["periode"].dt.strftime("%Y-%m-%d")
    export["taux_versement"] = export["taux_versement"].round(2)
    return export.rename(
        columns={
            "moto_id": "Moto",
            "frequence": "Frequence",
            "periode": "Periode",
            "versement_attendu": "Versement attendu",
            "versement_recu": "Versement recu",
            "ecart": "Ecart",
            "taux_versement": "Taux de versement",
        }
    )


def build_moto_report_chart(frame: pd.DataFrame, mode: str) -> go.Figure:
    fig = go.Figure()
    chart_frame = frame.sort_values("periode").tail(18)
    if mode == "weekly":
        labels = [f"Sem {int(period.strftime('%W'))} - {period.strftime('%d/%m')}" for period in chart_frame["periode"]]
    elif mode == "monthly":
        labels = [period.strftime("%m/%Y") for period in chart_frame["periode"]]
    else:
        labels = [period.strftime("%d/%m") for period in chart_frame["periode"]]
    fig.add_trace(
        go.Bar(
            x=labels,
            y=chart_frame["versement_attendu"],
            name="Attendu",
            marker_color="#94a3b8",
            hovertemplate="<b>%{x}</b><br>Attendu: %{y:,.0f} FCFA<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=chart_frame["versement_recu"],
            name="Recu",
            marker_color=ACCENT,
            hovertemplate="<b>%{x}</b><br>Recu: %{y:,.0f} FCFA<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=chart_frame["ecart"],
            name="Ecart",
            mode="lines+markers",
            line={"color": DANGER, "width": 3},
            marker={"size": 7, "color": DANGER},
            hovertemplate="<b>%{x}</b><br>Ecart: %{y:,.0f} FCFA<extra></extra>",
        )
    )
    fig.update_layout(
        height=345,
        barmode="group",
        margin={"l": 20, "r": 20, "t": 20, "b": 55},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend={"orientation": "h", "y": 1.08, "x": 0},
        font={"family": "Inter, Segoe UI, Arial, sans-serif", "color": "#111827"},
    )
    fig.update_yaxes(title="FCFA", gridcolor="#edf2f7", zerolinecolor="#dbe3ea")
    fig.update_xaxes(showgrid=False, tickangle=-35 if mode != "monthly" else 0)
    return fig


def render_moto_report_detail(moto_id: str | None, mode: str) -> html.Div:
    if not moto_id:
        return html.Div("Aucune moto disponible dans les donnees importees.", className="empty-state")
    frame = moto_report_frequency_frame(moto_id, mode)
    if frame.empty:
        return html.Div(f"Aucun versement trouve pour {moto_id}.", className="empty-state")
    latest = frame.iloc[0]
    total_expected = float(latest["versement_attendu"])
    total_received = float(latest["versement_recu"])
    gap = float(latest["ecart"])
    rate = safe_ratio(total_received, total_expected) * 100
    cumulative_received, last_payment_date = moto_report_cumulative_to_last_payment(moto_id)
    cumulative_status = (
        f"Jusqu'au {last_payment_date.strftime('%d/%m/%Y')}"
        if last_payment_date is not None
        else "Aucun versement"
    )
    if mode == "weekly":
        period_status = f"Semaine du {pd.to_datetime(latest['periode']).strftime('%d/%m/%Y')}"
    elif mode == "monthly":
        period_status = pd.to_datetime(latest["periode"]).strftime("%m/%Y")
    else:
        period_status = pd.to_datetime(latest["periode"]).strftime("%d/%m/%Y")
    rows = []
    for _, row in frame.head(80).iterrows():
        period = row["periode"]
        if mode == "weekly":
            label = f"Semaine du {period.strftime('%d/%m/%Y')}"
        elif mode == "monthly":
            label = period.strftime("%m/%Y")
        else:
            label = period.strftime("%d/%m/%Y")
        rows.append(
            html.Tr(
                [
                    html.Td(label),
                    html.Td(format_value(float(row["versement_attendu"]), "FCFA")),
                    html.Td(format_value(float(row["versement_recu"]), "FCFA")),
                    html.Td(format_value(float(row["ecart"]), "FCFA")),
                    html.Td(format_value(float(row["taux_versement"]), "%")),
                ]
            )
        )
    return html.Div(
        [
            html.Div(
                [
                    kpi_card("Moto selectionnee", moto_id, FREQUENCY_LABELS.get(mode, mode), ACCENT),
                    kpi_card("Versement attendu", format_value(total_expected, "FCFA"), period_status, INFO),
                    kpi_card("Versement recu", format_value(total_received, "FCFA"), period_status, BRAND),
                    kpi_card("Ecart", format_value(gap, "FCFA"), period_status, DANGER if gap > 0 else BRAND),
                    kpi_card("Taux de versement", format_value(rate, "%"), period_status, BRAND if rate >= 90 else WARNING),
                    kpi_card("Total versements a jour J", format_value(cumulative_received, "FCFA"), cumulative_status, ACCENT),
                ],
                className="cards-grid report-summary-grid",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Versements par periode"),
                            html.P(
                                f"Derniere periode chargee: {pd.to_datetime(latest['periode']).strftime('%d/%m/%Y')}."
                            ),
                        ],
                        className="chart-copy",
                    ),
                    dcc.Graph(figure=build_moto_report_chart(frame, mode), config={"displayModeBar": False}),
                ],
                className="chart-panel",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Detail des versements"),
                            html.P("Les lignes affichent le versement attendu, le versement recu et le taux obtenu."),
                        ],
                        className="chart-copy",
                    ),
                    html.Div(
                        html.Table(
                            [
                                html.Thead(
                                    html.Tr(
                                        [
                                            html.Th("Periode"),
                                            html.Th("Versement attendu"),
                                            html.Th("Versement recu"),
                                            html.Th("Ecart"),
                                            html.Th("Taux"),
                                        ]
                                    )
                                ),
                                html.Tbody(rows),
                            ],
                            className="cause-table",
                        ),
                        className="table-scroll",
                    ),
                ],
                className="chart-panel report-print-area",
            ),
        ],
        id="moto-report-printable",
        className="report-detail",
    )


def render_moto_report_page() -> html.Section:
    options = moto_options()
    selected_moto = options[0]["value"] if options else None
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Rapport motos", className="eyebrow"),
                            html.H2("Rapport des versements par moto"),
                            html.P("Recherchez une moto par identifiant, choisissez la frequence, puis imprimez le rapport."),
                        ],
                        className="section-title",
                    ),
                    html.Div(
                        [
                            html.Button("Imprimer", id="print-report-button", n_clicks=0, className="secondary-button", type="button"),
                        ],
                        className="report-actions",
                    ),
                ],
                className="dashboard-title-row report-title-row",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Rechercher une moto"),
                            dcc.Dropdown(
                                options,
                                selected_moto,
                                id="moto-search",
                                clearable=False,
                                searchable=True,
                                placeholder="Exemple: MOTO-1002",
                            ),
                        ],
                        className="filter-field",
                    ),
                    html.Div(
                        [
                            html.Label("Frequence"),
                            dcc.RadioItems(
                                frequency_options(INDICATOR_BY_KEY["rapport_motos"]),
                                "daily",
                                id="report-frequency",
                                className="period-mode report-frequency",
                                inputClassName="period-input",
                                labelClassName="period-label",
                            ),
                        ],
                        className="filter-field",
                    ),
                ],
                className="report-filters",
            ),
            html.Div(id="moto-report-detail", children=render_moto_report_detail(selected_moto, "daily")),
        ],
        className="report-panel",
    )


def home_block(group: str, context: dict[str, dict]) -> html.Div:
    indicators = indicators_for_group(group)
    states = [alert_for(indicator, indicator_value(indicator, context))[0] for indicator in indicators]
    if "danger" in states:
        status, color = "Alert", DANGER
    elif "watch" in states:
        status, color = "A surveiller", WARNING
    else:
        status, color = "Stable", BRAND
    danger_count = states.count("danger")
    return kpi_card(
        GROUPS[group],
        f"{danger_count} alerte(s)" if danger_count else "OK",
        status,
        color,
        {"type": "group-button", "group": group},
    )


def layout() -> html.Div:
    month_options, week_options, day_options = period_options()
    default_month, default_week, default_day = default_periods()
    default_group = "financier"
    default_mode = group_frequency_options(default_group)[0]["value"]
    default_indicator = indicators_for_group(default_group, default_mode)[0]
    return html.Div(
        [
            dcc.Store(id="selected-page", data="accueil"),
            dcc.Store(id="upload-refresh", data=0),
            dcc.Store(id="requested-indicator"),
            html.Header(
                [
                    html.Div(
                        [
                            html.H1("YUNUS CAM-MOTO"),
                            html.P("Accueil, blocs KPI, alertes, comparaisons quotidiennes, hebdomadaires et mensuelles."),
                        ]
                    ),
                    html.Div(
                        [
                            dcc.Upload(id="data-upload", children=html.Button("Importer Excel", className="secondary-button"), accept=".xlsx", multiple=False),
                            html.A("Modèle Excel", href="/assets/modele_kpi_multifeuilles_mis_a_jour.xlsx", className="template-link"),
                            html.Button("Mois précédent", id="previous-month-button", n_clicks=0, className="secondary-button"),
                            html.Button("Accueil", id="home-button", n_clicks=0, className="secondary-button", disabled=True),
                        ],
                        className="header-actions",
                    ),
                ],
                className="app-header",
            ),
            html.Main(
                [
                    html.Aside(
                        [
                            html.Div([html.Span("Filtres", className="eyebrow"), html.H2("Dashboard")], className="sidebar-title"),
                            html.Div([html.Label("Bloc KPI"), dcc.Dropdown(group_options(), default_group, id="group-filter", clearable=False)], className="filter-field hidden-filter"),
                            html.Div([html.Label("Indicateur"), dcc.Dropdown(indicator_options(default_group, default_mode), default_indicator.key, id="indicator-filter", clearable=False)], className="filter-field"),
                            html.Div(
                                [
                                    html.Label("Frequence"),
                                    dcc.RadioItems(
                                        group_frequency_options(default_group),
                                        default_mode,
                                        id="period-mode",
                                        className="period-mode",
                                        inputClassName="period-input",
                                        labelClassName="period-label",
                                    ),
                                ],
                                className="filter-field",
                            ),
                            html.Div([html.Label("Mois"), dcc.Dropdown(month_options, default_month, id="month-filter", clearable=False)], className="filter-field"),
                            html.Div([html.Label("Semaine"), dcc.Dropdown(week_options, default_week, id="week-filter", clearable=False)], className="filter-field"),
                            html.Div([html.Label("Jour"), dcc.Dropdown(day_options, default_day, id="day-filter", clearable=False)], className="filter-field"),
                            html.Div(id="filter-note", className="filter-note"),
                        ],
                        id="sidebar",
                        className="sidebar is-hidden",
                    ),
                    html.Div([html.Div(id="upload-status", className="upload-status"), html.Div(id="page-content")], className="content-stack"),
                ],
                id="main-shell",
                className="shell home-shell",
            ),
        ]
    )


app = Dash(__name__)
app.title = "YUNUS CAM-MOTO"
app.config.suppress_callback_exceptions = True
app.server.config.update(PROPAGATE_EXCEPTIONS=False)
app.enable_dev_tools(
    debug=False,
    dev_tools_ui=False,
    dev_tools_props_check=False,
    dev_tools_hot_reload=False,
    dev_tools_serve_dev_bundles=False,
    dev_tools_prune_errors=True,
)
app.layout = layout


@app.server.errorhandler(Exception)
def handle_unexpected_error(exc: Exception):
    if isinstance(exc, HTTPException):
        return exc
    LOGGER.exception("Erreur serveur non exposee au navigateur")
    return "Erreur interne. Consultez les journaux du serveur.", 500


@app.callback(
    Output("selected-page", "data"),
    Output("group-filter", "value"),
    Output("requested-indicator", "data"),
    Output("home-button", "disabled"),
    Output("previous-month-button", "disabled"),
    Input("home-button", "n_clicks"),
    Input("previous-month-button", "n_clicks"),
    Input({"type": "group-button", "group": ALL}, "n_clicks"),
    Input({"type": "indicator-button", "indicator": ALL}, "n_clicks"),
    State("selected-page", "data"),
    State("group-filter", "value"),
    State("day-filter", "value"),
    State("week-filter", "value"),
    State("month-filter", "value"),
)
def navigate(home_clicks: int, previous_month_clicks: int, group_clicks: list[int], indicator_clicks: list[int], selected_page: str, current_group: str, selected_day: str, selected_week: str, selected_month: str):
    triggered = callback_context.triggered_id
    
    def page_button_states(page: str):
        return page == "accueil", page == "previous-month"
    
    if triggered == "home-button":
        return "accueil", current_group, no_update, True, False
    if triggered == "previous-month-button":
        return "previous-month", current_group, no_update, False, True
    if isinstance(triggered, dict) and triggered.get("type") == "group-button":
        group = triggered["group"]
        if group == "rapport":
            return "moto-report", group, "rapport_motos", False, False
        if group == "hebdo":
            first_indicator = indicators_for_group(group)[0].key
            return "hebdo-home", group, first_indicator, False, False
        if not selected_day or not selected_week or not selected_month:
            selected_month, selected_week, selected_day = default_periods()
        context = period_context(selected_day, selected_week, selected_month)
        alert_items, watch_items = grouped_indicators_by_alert(group, context)
        if alert_items:
            first_alert = source_indicator_key(alert_items[0].key)
            return "dashboard", source_group_for_indicator(first_alert), first_alert, False, False
        if watch_items:
            first_watch = source_indicator_key(watch_items[0].key)
            return "dashboard", source_group_for_indicator(first_watch), first_watch, False, False
        first_indicator = source_indicator_key(indicators_for_group(group)[0].key)
        return "dashboard", group, first_indicator, False, False
    if isinstance(triggered, dict) and triggered.get("type") == "indicator-button":
        indicator_key = triggered["indicator"]
        if indicator_key in INDICATOR_BY_KEY and INDICATOR_BY_KEY[indicator_key].group == "hebdo":
            return "dashboard", "hebdo", indicator_key, False, False
        real_key = source_indicator_key(indicator_key)
        real_group = source_group_for_indicator(real_key)
        return "dashboard", real_group, real_key, False, False
    return selected_page, current_group, no_update, selected_page == "accueil", selected_page == "previous-month"


@app.callback(
    Output("indicator-filter", "options"),
    Output("indicator-filter", "value"),
    Input("group-filter", "value"),
    Input("period-mode", "value"),
    Input("requested-indicator", "data"),
    State("indicator-filter", "value"),
)
def sync_indicator(group: str, mode: str, requested_indicator: str | None, selected_indicator: str):
    options = indicator_options(group, mode)
    allowed = {option["value"] for option in options}
    triggered = callback_context.triggered_id
    selected_group = INDICATOR_BY_KEY[selected_indicator].group if selected_indicator in INDICATOR_BY_KEY else None
    if requested_indicator and (triggered == "requested-indicator" or selected_group != group):
        requested_indicator = source_indicator_key(requested_indicator)
        if requested_indicator in allowed:
            return options, requested_indicator
    if selected_indicator in allowed:
        return options, selected_indicator
    return options, options[0]["value"]


@app.callback(
    Output("period-mode", "options"),
    Output("period-mode", "value"),
    Input("group-filter", "value"),
    Input("requested-indicator", "data"),
    State("period-mode", "value"),
)
def sync_frequency(group: str, requested_indicator: str | None, current_mode: str):
    options = group_frequency_options(group)
    allowed = {option["value"] for option in options}
    triggered = callback_context.triggered_id
    if triggered == "requested-indicator" and requested_indicator in INDICATOR_BY_KEY:
        requested_mode = default_mode_for_indicator(INDICATOR_BY_KEY[requested_indicator])
        if requested_mode in allowed:
            return options, requested_mode
    if current_mode in allowed:
        return options, current_mode
    return options, options[0]["value"]


@app.callback(
    Output("month-filter", "options"),
    Output("month-filter", "value"),
    Output("week-filter", "options"),
    Output("week-filter", "value"),
    Output("day-filter", "options"),
    Output("day-filter", "value"),
    Input("upload-refresh", "data"),
)
def refresh_filters(refresh: int):
    months, weeks, days = period_options()
    default_month, default_week, default_day = default_periods()
    return months, default_month, weeks, default_week, days, default_day


@app.callback(
    Output("upload-status", "children"),
    Output("upload-refresh", "data"),
    Input("data-upload", "contents"),
    State("data-upload", "filename"),
    State("upload-refresh", "data"),
)
def import_data(contents: str | None, filename: str | None, refresh: int):
    global SAMPLE_DATA, MOTO_REPORT_DATA, DATA_VERSION
    if not contents:
        return "", refresh
    try:
        _, encoded = contents.split(",", 1)
        decoded = base64.b64decode(encoded)
        sheets = pd.read_excel(io.BytesIO(decoded), sheet_name=None, engine="openpyxl")
        frames = []
        moto_frames = []
        metric_column_candidates = set(REQUIRED_COLUMNS) | {
            "Montant total attendu (FCFA)",
            "Total collecté (FCFA)",
            "Total collecté semaine (FCFA)",
            "Montant attendu semaine (FCFA)",
            "Nombre de bénéficiaires",
            "Nombre bénéficiaires (nb)",
            "Motos actives (nb)",
            "Total motos (nb)",
            "Motos en panne (nb)",
            "Bénéficiaires actifs (nb)",
            "Bénéficiaires initial (nb)",
            "Revenus après projet (FCFA)",
            "Nombre de transactions (nb)",
            "Utilisateurs actifs (nb)",
            "Paiements à temps (nb)",
            "Paiements attendus (nb)",
            "Jours actifs (nb)",
            "Jours totaux (nb)",
        }
        for sheet_name, sheet in sheets.items():
            if str(sheet_name).strip().lower() == "kpi hebdo":
                continue
            sheet_frame = promote_excel_header(sheet.copy())
            sheet_frame = sheet_frame.loc[:, ~sheet_frame.columns.duplicated()]
            normalized_columns = {str(column).strip() for column in sheet_frame.columns}
            moto_column_candidates = {"moto_id", "Moto", "moto", "Identifiant moto", "identifiant_moto"}
            expected_candidates = {"versement_attendu", "Versement attendu", "versement attendu", "montant_attendu", "Montant attendu"}
            received_candidates = {"versement_recu", "Versement recu", "Versement reçu", "versement reçu", "montant_recu", "Montant recu", "Montant reçu"}
            if (
                normalized_columns & moto_column_candidates
                and normalized_columns & expected_candidates
                and normalized_columns & received_candidates
            ):
                moto_frames.append(sheet_frame)
                continue
            if "date" not in sheet_frame.columns:
                for date_column in ("week_start", "Periode", "Date", "Semaine (lundi)"):
                    if date_column in sheet_frame.columns:
                        sheet_frame = sheet_frame.rename(columns={date_column: "date"})
                        break
            if "date" not in sheet_frame.columns:
                continue
            if not any(column in metric_column_candidates and column != "date" for column in sheet_frame.columns):
                continue
            sheet_frame["date"] = pd.to_datetime(sheet_frame["date"], errors="coerce")
            sheet_frame = sheet_frame.dropna(subset=["date"])
            sheet_frame = sheet_frame.loc[:, ~sheet_frame.columns.duplicated()]
            frames.append(sheet_frame)
        if not frames:
            raise ValueError("Aucune feuille avec une colonne date ou week_start.")
        frame = frames[0]
        for sheet_frame in frames[1:]:
            frame = pd.merge(frame, sheet_frame, on="date", how="outer", suffixes=("", "_dup"))
            for duplicate in [column for column in frame.columns if column.endswith("_dup")]:
                original = duplicate[:-4]
                if original in frame.columns:
                    frame[original] = frame[original].where(frame[original].notna(), frame[duplicate])
                else:
                    frame = frame.rename(columns={duplicate: original})
            frame = frame.drop(columns=[column for column in frame.columns if column.endswith("_dup")])
        SAMPLE_DATA = prepare_data(frame)
        if moto_frames:
            MOTO_REPORT_DATA = prepare_moto_report(pd.concat(moto_frames, ignore_index=True))
        else:
            MOTO_REPORT_DATA = make_sample_moto_report(SAMPLE_DATA)
        DATA_VERSION += 1
        indicator_timeseries_cached.cache_clear()
        involved_timeseries_cached.cache_clear()
        return f"Import reussi: {filename} ({len(SAMPLE_DATA)} lignes).", refresh + 1
    except Exception as exc:
        LOGGER.exception("Import Excel impossible")
        return "Import impossible: le fichier ne correspond pas au modele attendu.", refresh


@app.callback(
    Output("moto-report-detail", "children"),
    Input("moto-search", "value"),
    Input("report-frequency", "value"),
)
def update_moto_report_detail(moto_id: str | None, mode: str):
    return render_moto_report_detail(moto_id, mode or "daily")


@app.callback(
    Output("page-content", "children"),
    Output("day-filter", "disabled"),
    Output("week-filter", "disabled"),
    Output("month-filter", "disabled"),
    Output("filter-note", "children"),
    Output("sidebar", "className"),
    Output("sidebar", "style"),
    Output("main-shell", "className"),
    Input("selected-page", "data"),
    Input("group-filter", "value"),
    Input("indicator-filter", "value"),
    Input("month-filter", "value"),
    Input("week-filter", "value"),
    Input("day-filter", "value"),
    Input("period-mode", "value"),
    Input("upload-refresh", "data"),
    Input("requested-indicator", "data"),
)
def render_page(selected_page: str, group: str, indicator_key: str, selected_month: str, selected_week: str, selected_day: str, mode: str, refresh: int, requested_indicator: str | None):
    if not indicator_key or indicator_key not in INDICATOR_BY_KEY:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    if selected_page == "accueil":
        context = period_context(selected_day, selected_week, selected_month)
        current_label = context["monthly"]["current_label"]
        return (
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Accueil", className="eyebrow"),
                            html.H2("Vue générale des indicateurs"),
                            html.P(f"État général calculé sur la période sélectionnée: {current_label}. Cliquez sur un bloc pour ouvrir son dashboard."),
                        ],
                        className="section-title home-title",
                    ),
                    html.Div([home_block(group_key, context) for group_key in GROUPS], className="cards-grid home-grid"),
                ],
                className="home-panel",
            ),
            True,
            True,
            False,
            "Accueil: le mois reste actif pour calculer l'état général des blocs.",
            "sidebar is-hidden",
            {},
            "shell home-shell",
        )

    if selected_page == "previous-month":
        selected_month_start = pd.to_datetime(selected_month + "-01")
        previous_month = selected_month_start - pd.DateOffset(months=1)
        frame = SAMPLE_DATA[SAMPLE_DATA["month"] == previous_month]
        values = compute_metrics(frame, "monthly")
        EXCLUDE_FROM_MONTHLY = {"top_beneficiaires", "flop_beneficiaires"}
        monthly_sections = []
        for group_key, group_label in GROUPS.items():
            monthly_indicators = [i for i in indicators_for_group(group_key, "monthly") if i.key not in EXCLUDE_FROM_MONTHLY]
            if not monthly_indicators:
                continue
            monthly_sections.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(group_label, className="eyebrow"),
                                html.H3(group_label),
                            ],
                            className="chart-copy",
                        ),
                        html.Div([indicator_card(indicator, values) for indicator in monthly_indicators], className="cards-grid"),
                    ],
                    className="monthly-group",
                )
            )
        return (
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Mois précédent", className="eyebrow"),
                            html.H2(f"Indicateurs mensuels - {previous_month.strftime('%m/%Y')}"),
                            html.P("Cette page affiche uniquement les indicateurs mensuels du mois précédent par bloc KPI."),
                        ],
                        className="section-title home-title",
                    ),
                    html.Div(monthly_sections, className="monthly-sections"),
                ],
                className="home-panel",
            ),
            True,
            True,
            False,
            "Mois précédent: seuls les indicateurs mensuels sont affichés.",
            "sidebar is-hidden",
            {},
            "shell home-shell",
        )

    if selected_page == "hebdo-home":
        current, _, current_label, _ = filter_period(selected_day, selected_week, selected_month, "weekly")
        values = compute_metrics(current, "weekly")
        return (
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("KPI Hebdo", className="eyebrow"),
                            html.H2("Accueil KPI Hebdo"),
                            html.P(f"Indicateurs indispensables de la semaine sélectionnée: {current_label}. Cliquez sur un indicateur pour ouvrir son dashboard."),
                        ],
                        className="section-title home-title",
                    ),
                    html.Div([indicator_card(indicator, values) for indicator in indicators_for_group("hebdo")], className="cards-grid hebdo-home-grid"),
                ],
                className="home-panel",
            ),
            True,
            True,
            True,
            "KPI Hebdo: accueil des indicateurs hebdomadaires. Revenez à l'accueil pour changer la date.",
            "sidebar is-hidden",
            {},
            "shell home-shell",
        )

    if selected_page == "moto-report":
        return (
            render_moto_report_page(),
            True,
            True,
            True,
            "Rapport motos: utilisez la recherche et la frequence dans la page.",
            "sidebar is-hidden",
            {},
            "shell home-shell",
        )

    if selected_page == "group-overview":
        group = HIDDEN_GROUP_REMAP.get(group, group)
        if group not in GROUPS:
            group = "financier"
        context = period_context(selected_day, selected_week, selected_month)
        alert_items, watch_items = grouped_indicators_by_alert(group, context)
        if not alert_items:
            selected_page = "dashboard"
        else:
            involved_rows = []
            for alert_indicator in alert_items:
                alert_mode = default_mode_for_indicator(alert_indicator)
                involved_rows.extend(alert_cause_rows(alert_indicator, context[alert_mode]["current"], context[alert_mode]["previous"], context[alert_mode]["values"]))
            return (
                html.Section(
                    [
                        html.Div(
                            [
                                html.Span(GROUPS[group], className="eyebrow"),
                                html.H2(f"Synthèse {GROUPS[group]}"),
                                html.P("Cliquez sur une carte rouge pour ouvrir l'interface de l'indicateur et filtrer les bénéficiaires ou motos impliqués."),
                            ],
                            className="section-title home-title",
                        ),
                        indicator_section(
                            "Indicateurs qui génèrent l'alerte",
                            "Ces indicateurs sont en rouge et demandent une action immédiate.",
                            alert_items,
                            context,
                            "Aucune alerte",
                        ),
                        indicator_section(
                            "Indicateurs à suivre",
                            "Ces indicateurs sont en surveillance et doivent être contrôlés.",
                            watch_items,
                            context,
                            "Aucun indicateur à suivre",
                        ),
                        involved_table_from_rows(involved_rows, "Bénéficiaires impliqués", "Bénéficiaires et motos filtrés par les indicateurs en alerte."),
                    ],
                    className="home-panel",
                ),
                True,
                True,
                True,
                "Synthèse KPI en alerte: cliquez sur une carte rouge pour ouvrir le dashboard détaillé.",
                "sidebar is-hidden",
                {},
                "shell home-shell",
            )

    # Resolve hebdo aliases only when NOT already in the hebdo group context
    if indicator_key not in INDICATOR_BY_KEY or INDICATOR_BY_KEY[indicator_key].group != "hebdo":
        indicator_key = source_indicator_key(indicator_key)

    # Determine display group (visible in GROUPS)
    if indicator_key in INDICATOR_BY_KEY:
        real_group = INDICATOR_BY_KEY[indicator_key].group
        group = HIDDEN_GROUP_REMAP.get(real_group, real_group)
        if group not in GROUPS:
            group = "financier"
    else:
        group = HIDDEN_GROUP_REMAP.get(group, group)
        if group not in GROUPS:
            group = "financier"
        indicator_key = indicators_for_group(group)[0].key

    if indicator_key not in INDICATOR_BY_KEY:
        indicator_key = indicators_for_group(group)[0].key

    indicator = INDICATOR_BY_KEY[indicator_key]

    # Mode based on the indicator itself
    mode_options_for_ind = frequency_options(indicator)
    allowed_modes = {opt["value"] for opt in mode_options_for_ind}
    mode = mode if mode in allowed_modes else mode_options_for_ind[0]["value"]

    indicator = INDICATOR_BY_KEY[indicator_key]
    current, previous, current_label, previous_label = filter_period(selected_day, selected_week, selected_month, mode)
    values = compute_metrics(current, mode)
    previous_values = compute_metrics(previous, mode)
    values["__mode"] = mode
    value = values[indicator.key]
    previous_value = previous_values[indicator.key]
    delta = percent_change(value, previous_value)
    _, status, color = alert_for(indicator, value)
    delta_text, delta_color = delta_status(indicator, delta)

    frequency_label = {"monthly": "Mensuel", "weekly": "Hebdomadaire", "daily": "Quotidien"}[mode]
    disabled_day = True
    disabled_week = True
    disabled_month = True
    note = f"Mode {frequency_label}: l'indicateur est affiché. Revenez à l'accueil pour changer la date."

    selected_indicator_card = selected_value_card(indicator, value)
    context = period_context(selected_day, selected_week, selected_month)
    alert_items, watch_items = grouped_indicators_by_alert(group, context)
    current_state, _, _ = alert_for(indicator, value)
    if current_state == "danger":
        related_items = [alert_item for alert_item in alert_items if source_indicator_key(alert_item.key) != indicator.key]
        side_label = "Alerte"
        side_title = "Autres indicateurs en alerte"
        side_description = "Cliquez sur une carte rouge pour ouvrir son indicateur et descendre directement aux impliqués."
    elif current_state == "watch":
        related_items = [watch_item for watch_item in watch_items if source_indicator_key(watch_item.key) != indicator.key]
        side_label = "Surveillance"
        side_title = "Autres indicateurs à surveiller"
        side_description = "Cliquez sur une carte jaune pour ouvrir son indicateur et descendre directement aux impliqués."
    else:
        related_items = []
        side_label = ""
        side_title = ""
        side_description = ""
    alert_panel = (
        html.Div(
            [
                html.Div(
                    [
                        html.Span(side_label, className="eyebrow"),
                        html.H3(side_title),
                        html.P(side_description),
                    ],
                    className="chart-copy",
                ),
                html.Div([indicator_context_card(related_indicator, context) for related_indicator in related_items], className="cards-grid dashboard-alert-grid"),
            ],
            className="alert-side-panel",
        )
        if related_items
        else None
    )
    kpi_row_children = [html.Div([selected_indicator_card], className="cards-grid single-indicator-grid indicator-grid")]
    if alert_panel:
        kpi_row_children.append(alert_panel)
    return (
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(GROUPS[group], className="eyebrow"),
                                html.H2(f"Dashboard {GROUPS[group]}"),
                                html.P("La première carte affiche la valeur, la carte suivante affiche uniquement l'écart."),
                            ],
                            className="section-title",
                        ),
                        html.Div(className="period-pill", children=current_label),
                    ],
                    className="dashboard-title-row",
                ),
                html.Div(
                    kpi_row_children,
                    className="dashboard-kpi-row has-alerts" if alert_panel else "dashboard-kpi-row no-alerts",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(delta_text, className="alert", style={"backgroundColor": delta_color}),
                                html.Div(format_indicator_delta(indicator, delta), className="hero-value"),
                                html.P(f"vs {previous_label}", className="muted"),
                            ],
                            className="summary-main",
                        ),
                        html.Div(
                            [
                                html.Div([html.Span("Indicateur"), html.Strong(indicator.name)]),
                                html.Div([html.Span("Fréquence"), html.Strong(frequency_label)]),
                                html.Div([html.Span("Sens attendu"), html.Strong("Hausse" if indicator.higher_is_better else "Baisse")]),
                            ],
                            className="summary-details",
                        ),
                    ],
                    className="indicator-summary",
                ),
                html.Div(
                    [
                        html.Div([
                            html.H3("Comparaison" if mode != "daily" else "Versement J vs J-1"),
                            html.P({
                                "daily": f"Versement du jour {current_label} comparé au jour précédent {previous_label}.",
                                "weekly": f"Semaine {current_label} vs semaine précédente {previous_label}.",
                                "monthly": f"Mois {current_label} vs mois précédent {previous_label}.",
                            }.get(mode, "Comparaison de la période sélectionnée vs la période précédente."))
                        ], className="chart-copy"),
                        dcc.Graph(figure=build_comparison_chart(indicator, value, previous_value, current_label, previous_label), config={"displayModeBar": False}),
                    ],
                    className="chart-panel",
                ),
                alert_cause_table(indicator, current, previous, values),
                html.Div(
                    [
                        html.Div([html.H3(involved_visual_title(indicator)), html.P(involved_visual_description(indicator))], className="chart-copy"),
                        dcc.Graph(figure=build_involved_visual(indicator, current, previous, mode), config={"displayModeBar": False}),
                    ],
                    className="chart-panel",
                ) if indicator.key not in {"visites_terrain_jour", "taux_visites", "hebdo_visites", "motos_visitees"} else None,
                html.Div(
                    [
                        html.Div([html.H3("Tendance"), html.P("Évolution historique de l'indicateur sélectionné.")], className="chart-copy"),
                        dcc.Graph(figure=build_trend_chart(indicator, mode), config={"displayModeBar": False}),
                    ],
                    className="chart-panel",
                ),
            ]
        ),
        disabled_day,
        disabled_week,
        disabled_month,
        note,
        "sidebar",
        {},
        "shell",
    )


app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            :root { --bg: #f5f7f8; --panel: #ffffff; --ink: #111827; --muted: #64748b; --line: #dbe3ea; --soft: #eef7f4; }
            * { box-sizing: border-box; }
            body { margin: 0; font-family: Inter, Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--ink); }
            h1, h2, h3, p { margin: 0; }
            h1 { font-size: 28px; font-weight: 850; letter-spacing: 0; }
            h2 { font-size: 24px; letter-spacing: 0; }
            h3 { font-size: 16px; line-height: 1.25; letter-spacing: 0; }
            p { color: var(--muted); line-height: 1.45; }
            .app-header { min-height: 88px; padding: 20px 32px; display: flex; align-items: center; justify-content: space-between; gap: 18px; background: white; border-bottom: 1px solid var(--line); }
            .header-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
            .secondary-button, .open-button { border: 0; border-radius: 7px; background: #17663a; color: white; font-weight: 850; min-height: 40px; padding: 0 15px; cursor: pointer; }
            .secondary-button:disabled { opacity: 0.45; cursor: not-allowed; pointer-events: none; }
            .open-button { background: #0f766e; margin-top: 14px; }
            .template-link { min-height: 40px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--line); border-radius: 7px; background: #fff; color: #0f766e; font-size: 13px; font-weight: 850; padding: 0 12px; text-decoration: none; }
            .shell { max-width: 1480px; margin: 0 auto; padding: 24px; display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 22px; align-items: start; }
            .shell.home-shell { max-width: 1180px; grid-template-columns: 1fr; }
            .content-stack { display: grid; gap: 14px; min-width: 0; }
            .upload-status { color: #0f766e; font-size: 13px; font-weight: 800; }
            .sidebar { position: sticky; top: 18px; background: white; border: 1px solid var(--line); border-radius: 8px; padding: 18px; display: grid; gap: 16px; box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06); }
            .sidebar.is-hidden { display: none; }
            .is-disabled { pointer-events: none; opacity: 0.5; }
            .sidebar-title { display: grid; gap: 4px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
            .eyebrow { color: #0f766e; font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: 0; }
            .filter-field { display: grid; gap: 7px; }
            .hidden-filter { display: none; }
            .filter-field label { display: block; font-weight: 800; font-size: 13px; color: #334155; }
            .filter-note { color: var(--muted); font-size: 13px; line-height: 1.45; border-top: 1px solid var(--line); padding-top: 12px; }
            .period-mode { display: grid; gap: 8px; }
            .period-label { display: flex !important; align-items: center; gap: 7px; min-height: 38px; border: 1px solid var(--line); border-radius: 7px; background: white; padding: 0 11px; font-weight: 800 !important; margin: 0 !important; color: #334155 !important; }
            .section-title { display: grid; gap: 6px; max-width: 860px; }
            .home-title { margin-bottom: 18px; }
            .dashboard-title-row { display: flex; justify-content: space-between; align-items: start; gap: 16px; margin-bottom: 18px; }
            .period-pill { border: 1px solid #b7d8cf; background: var(--soft); color: #115e59; border-radius: 999px; padding: 9px 14px; font-weight: 850; white-space: nowrap; }
            .alert { display: inline-flex; align-items: center; border-radius: 999px; color: #fff; font-size: 12px; font-weight: 800; padding: 5px 10px; }
            .cards-grid { display: grid; grid-template-columns: repeat(4, minmax(210px, 1fr)); gap: 16px; }
            .hebdo-home-grid { grid-template-columns: repeat(5, minmax(170px, 1fr)); }
            .single-indicator-grid { grid-template-columns: minmax(240px, 360px); }
            .dashboard-kpi-row { display: grid; grid-template-columns: minmax(260px, 360px) minmax(0, 1fr); gap: 18px; align-items: start; margin-bottom: 22px; }
            .dashboard-kpi-row.no-alerts { grid-template-columns: minmax(260px, 360px); }
            .dashboard-kpi-row .indicator-grid { margin-bottom: 0; }
            .alert-side-panel { background: white; border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06); }
            .dashboard-alert-grid { grid-template-columns: repeat(3, minmax(170px, 1fr)); }
            .dashboard-alert-grid .kpi-card { min-height: 138px; }
            .alert-section { display: grid; gap: 14px; margin-bottom: 22px; }
            .alert-grid { grid-template-columns: repeat(3, minmax(210px, 1fr)); }
            .monthly-sections { display: grid; gap: 24px; }
            .monthly-group { display: grid; gap: 10px; }
            .kpi-card { background: white; border: 1px solid var(--line); border-top: 5px solid #17663a; border-radius: 8px; padding: 16px; min-height: 154px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05); transition: transform 160ms ease, box-shadow 160ms ease; }
            button.kpi-card { width: 100%; text-align: left; font: inherit; color: inherit; cursor: pointer; }
            button.kpi-card:focus-visible { outline: 3px solid rgba(15, 118, 110, 0.28); outline-offset: 2px; }
            .kpi-card:hover { transform: translateY(-3px); box-shadow: 0 18px 38px rgba(15, 23, 42, 0.12); }
            .card-top { min-height: 26px; }
            .big-value { font-size: 27px; font-weight: 850; letter-spacing: 0; margin-top: 12px; overflow-wrap: anywhere; }
            .indicator-grid { margin-bottom: 22px; }
            .indicator-summary { margin: 0 0 20px; display: grid; grid-template-columns: minmax(260px, 0.75fr) minmax(360px, 1fr); gap: 18px; }
            .summary-main, .summary-details, .chart-panel { background: white; border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06); }
            .summary-main { min-height: 190px; padding: 20px; display: flex; flex-direction: column; justify-content: space-between; }
            .hero-value { font-size: 44px; font-weight: 900; letter-spacing: 0; overflow-wrap: anywhere; line-height: 1.05; }
            .summary-details { padding: 6px 18px; display: grid; }
            .summary-details > div { min-height: 45px; display: flex; align-items: center; justify-content: space-between; gap: 14px; border-bottom: 1px solid var(--line); }
            .summary-details > div:last-child { border-bottom: 0; }
            .summary-details span { color: var(--muted); font-size: 13px; font-weight: 700; }
            .summary-details strong { text-align: right; font-size: 14px; }
            .chart-panel { padding: 18px; margin-bottom: 20px; }
            .involved-panel { scroll-margin-top: 24px; }
            .chart-copy { display: grid; gap: 6px; margin-bottom: 8px; }
            .table-scroll { max-height: 520px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; }
            .table-scroll .cause-table th { position: sticky; top: 0; z-index: 1; }
            .cause-table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .cause-table th, .cause-table td { text-align: left; padding: 11px 10px; border-bottom: 1px solid var(--line); }
            .cause-table th { color: #334155; background: #f8fafc; font-weight: 850; }
            .cause-table td { color: #111827; font-weight: 650; }
            .report-panel { display: grid; gap: 18px; }
            .report-title-row { margin-bottom: 0; }
            .report-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; }
            .report-filters { background: white; border: 1px solid var(--line); border-radius: 8px; padding: 16px; display: grid; grid-template-columns: minmax(260px, 1fr) minmax(260px, 1fr); gap: 16px; box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06); }
            .report-frequency { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
            .report-detail { display: grid; gap: 18px; }
            .report-summary-grid { grid-template-columns: repeat(3, minmax(180px, 1fr)); }
            .empty-state { background: white; border: 1px dashed var(--line); border-radius: 8px; padding: 22px; color: var(--muted); font-weight: 800; }
            .muted { font-size: 13px; }
            .Select-control { border-color: var(--line) !important; border-radius: 7px !important; min-height: 40px; }
            .Select-placeholder, .Select-value-label { font-weight: 750; color: #334155 !important; }
            @media (max-width: 1080px) {
                .shell { grid-template-columns: 1fr; }
                .sidebar { position: static; }
                .cards-grid, .hebdo-home-grid, .alert-grid, .dashboard-alert-grid, .report-summary-grid { grid-template-columns: repeat(2, minmax(220px, 1fr)); }
                .dashboard-kpi-row { grid-template-columns: 1fr; }
                .indicator-summary { grid-template-columns: 1fr; }
                .report-filters { grid-template-columns: 1fr; }
            }
            @media (max-width: 680px) {
                .app-header { padding: 18px; align-items: start; flex-direction: column; }
                .header-actions { justify-content: flex-start; }
                .shell { padding: 16px; }
                .cards-grid, .hebdo-home-grid, .alert-grid, .dashboard-alert-grid, .report-summary-grid { grid-template-columns: 1fr; }
                .dashboard-title-row { flex-direction: column; }
                .report-actions { justify-content: flex-start; }
                .period-pill { white-space: normal; }
                .hero-value { font-size: 34px; }
            }
            @media print {
                body { background: white; }
                .app-header, .report-actions, .report-filters, .upload-status { display: none !important; }
                .shell, .shell.home-shell { max-width: none; padding: 0; display: block; }
                .chart-panel, .kpi-card, .report-filters { box-shadow: none !important; }
                .table-scroll { max-height: none; overflow: visible; }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>{%config%}{%scripts%}{%renderer%}</footer>
        <script>
            document.addEventListener("click", function(event) {
                if (event.target && event.target.id === "print-report-button") {
                    window.print();
                }
            });
        </script>
    </body>
</html>
"""


if __name__ == "__main__":
    url = "http://127.0.0.1:8060"
    print(f"Ouvrir le dashboard: {url}")
    threading.Timer(1.0, lambda: webbrowser.open_new(url)).start()
    app.run(
        debug=False,
        host="127.0.0.1",
        port=8060,
        use_reloader=False,
        dev_tools_ui=False,
        dev_tools_props_check=False,
        dev_tools_hot_reload=False,
    )
