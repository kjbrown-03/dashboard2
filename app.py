from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, State, callback_context, dcc, html, no_update


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
    "risque": "Risque",
    "hebdo": "KPI Hebdo",
    "terrain": "Suivi terrain",
}

INDICATORS = [
    Indicator("taux_remboursement", "Taux de remboursement global", "financier", "Montant total rembourse / Montant total attendu x 100", "both", "%", True, 95, 90),
    Indicator("taux_defaut", "Taux de defaut", "financier", "Montant en defaut / Montant total finance x 100", "monthly", "%", False, 5, 10),
    Indicator("par7", "PAR 7 jours", "financier", "Encours en retard > 7 jours / Encours total x 100", "weekly", "%", False, 5, 10),
    Indicator("taux_paiement_temps", "Taux de paiement a temps", "financier", "Nombre paiements effectues a temps / Nombre paiements attendus x 100", "weekly", "%", True, 95, 90),
    Indicator("montant_moyen", "Montant moyen paye par beneficiaire", "financier", "Total collecte / Nombre de beneficiaires", "monthly", "FCFA", True),
    Indicator("recovery_rate", "Taux de recuperation du portefeuille", "financier", "Montant recupere / Montant total prete x 100", "monthly", "%", True, 85, 70),
    Indicator("taux_motos_actives", "Taux de motos actives", "operationnel", "Nombre motos actives / Nombre total motos x 100", "both", "%", True, 95, 90),
    Indicator("taux_utilisation", "Taux d'utilisation", "operationnel", "Jours actifs / Jours totaux x 100", "weekly", "%", True, 85, 75),
    Indicator("moyenne_courses", "Nombre moyen de courses/jour", "operationnel", "Courses totales / Jours de la periode", "daily", "", True, 8, 6),
    Indicator("temps_inactivite", "Temps d'inactivite", "operationnel", "Nombre de jours sans activite", "weekly", "jours", False, 1, 3),
    Indicator("taux_pannes", "Taux de pannes", "operationnel", "Nombre motos en panne / Total motos x 100", "weekly", "%", False, 3, 7),
    Indicator("revenu_moyen_social", "Revenu moyen par beneficiaire", "social", "Total revenus estimes / Nombre beneficiaires", "monthly", "FCFA", True),
    Indicator("taux_maintien", "Taux de maintien dans le programme", "social", "Nombre beneficiaires actifs / Nombre initial x 100", "monthly", "%", True, 98, 95),
    Indicator("emplois_crees", "Nombre d'emplois crees", "social", "Emplois directs + emplois indirects", "monthly", "", True),
    Indicator("amelioration_revenus", "Taux d'amelioration des revenus", "social", "Revenus apres projet vs revenus avant projet", "monthly", "%", True, 20, 15),
    Indicator("taux_digitalisation", "Taux de digitalisation des paiements", "fintech", "Paiements digitaux / Paiements totaux x 100", "weekly", "%", True, 100, 80),
    Indicator("volume_transactions", "Volume de transactions", "fintech", "Total mensuel via Yunus Pay", "monthly", "FCFA", True),
    Indicator("revenus_fintech", "Revenu de commission", "fintech", "Somme des commissions sur transactions", "monthly", "FCFA", True),
    Indicator("nb_utilisateurs_actifs", "Nombre d'utilisateurs actifs", "fintech", "Utilisateurs ayant realise au moins une transaction", "monthly", "", True),
    Indicator("freq_utilisation", "Frequence d'utilisation par beneficiaire", "fintech", "Transactions / Nombre de beneficiaires", "monthly", "", True),
    Indicator("taux_visites", "Taux de visites effectuees", "terrain", "Visites realisees / Visites prevues x 100", "weekly", "%", True, 95, 85),
    Indicator("delai_reaction", "Delai moyen de reaction", "terrain", "Temps entre defaut et intervention", "weekly", "jours", False, 1, 2),
    Indicator("visites_par_benef", "Nombre de visites par beneficiaire", "terrain", "Total visites / Nombre beneficiaires", "weekly", "", True, 1, 0.5),
    Indicator("taux_resolution", "Taux de resolution des incidents", "terrain", "Incidents resolus / Incidents detectes x 100", "weekly", "%", True, 95, 80),
    Indicator("nb_beneficiaires_retard", "Nombre de beneficiaires en retard", "risque", "Nombre de beneficiaires avec retard", "weekly", "", False, 5, 15),
    Indicator("retard_moyen", "Retard moyen", "risque", "Moyenne des jours de retard", "weekly", "jours", False, 2, 5),
    Indicator("recovery_apres_defaut", "Taux de recuperation apres defaut", "risque", "Montant recupere apres defaut / Montant en defaut x 100", "monthly", "%", True, 80, 60),
    Indicator("motos_recuperees", "Nombre de motos recuperees", "risque", "Motos recuperees apres defaut critique", "monthly", "", False, 1, 3),
    Indicator("hebdo_remboursement", "Taux de remboursement", "hebdo", "Repris du KPI financier", "weekly", "%", True, 95, 90),
    Indicator("hebdo_nb_retards", "Nombre de retards / 7 jours", "hebdo", "Repris du KPI risque", "weekly", "", False, 5, 15),
    Indicator("hebdo_par7", "PAR 7 jours", "hebdo", "Repris du KPI financier", "weekly", "%", False, 5, 10),
    Indicator("hebdo_motos_actives", "Motos actives", "hebdo", "Repris du KPI operationnel", "weekly", "%", True, 95, 90),
    Indicator("hebdo_visites", "Visites terrain effectuees", "hebdo", "Repris du KPI suivi terrain", "weekly", "%", True, 95, 85),
]

INDICATOR_BY_KEY = {indicator.key: indicator for indicator in INDICATORS}

REQUIRED_COLUMNS = [
    "date",
    "montant_total_attendu",
    "montant_total_rembourse",
    "montant_total_finance",
    "montant_en_defaut",
    "encours_total",
    "encours_retard_7",
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
    "revenus_avant",
    "revenus_apres",
    "paiements_digitaux",
    "paiements_totaux",
    "volume_transactions",
    "commissions",
    "utilisateurs_actifs",
    "transactions",
    "visites_realisees",
    "visites_prevues",
    "delai_reaction",
    "incidents_resolus",
    "incidents_detectes",
    "beneficiaires_retard",
    "retard_total_jours",
    "montant_recupere_apres_defaut",
    "motos_recuperees",
    "cout_total_projet",
    "beneficiaires_finances",
]


def safe_ratio(num: float, den: float) -> float:
    return 0 if den in (0, None) else num / den


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
                "revenus_avant": revenues_before,
                "revenus_apres": revenues_estimated,
                "paiements_digitaux": digital_payments,
                "paiements_totaux": payments_expected,
                "volume_transactions": transaction_volume,
                "commissions": transaction_volume * 0.02,
                "utilisateurs_actifs": int(beneficiaires * np.clip(0.78 + i * 0.0007, 0.72, 0.95)),
                "transactions": digital_payments,
                "visites_realisees": visits_done,
                "visites_prevues": visits_planned,
                "delai_reaction": np.clip(1.5 + rng.normal(0, 0.45), 0.4, 4.8),
                "incidents_resolus": incidents_resolus,
                "incidents_detectes": incidents,
                "beneficiaires_retard": late_count,
                "retard_total_jours": late_count * np.clip(2.8 + rng.normal(0, 1.1), 0.5, 9),
                "montant_recupere_apres_defaut": amount_default * np.clip(0.72 + rng.normal(0, 0.08), 0.35, 0.95),
                "motos_recuperees": 1 if rng.random() > 0.965 else 0,
                "cout_total_projet": 170_000 + rng.normal(0, 10_000),
                "beneficiaires_finances": beneficiaires,
            }
        )
    return pd.DataFrame(rows)


def prepare_data(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    aliases = {
        "Periode": "date",
        "Date": "date",
        "beneficiaires": "nombre_beneficiaires",
        "Total collecté": "total_collecte",
        "Montant total remboursé": "montant_total_rembourse",
        "Montant total attendu": "montant_total_attendu",
    }
    prepared = prepared.rename(columns={k: v for k, v in aliases.items() if k in prepared.columns})
    missing = [column for column in REQUIRED_COLUMNS if column not in prepared.columns]
    if missing:
        raise ValueError("Colonnes manquantes: " + ", ".join(missing))
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["date"])
    for column in REQUIRED_COLUMNS:
        if column != "date":
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0)
    prepared["month"] = prepared["date"].dt.to_period("M").dt.to_timestamp()
    prepared["week_start"] = prepared["date"] - pd.to_timedelta(prepared["date"].dt.weekday, unit="D")
    return prepared.sort_values("date").reset_index(drop=True)


SAMPLE_DATA = prepare_data(make_sample_data())


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
        "taux_remboursement": safe_ratio(sums["montant_total_rembourse"], sums["montant_total_attendu"]) * 100,
        "taux_defaut": safe_ratio(avgs["montant_en_defaut"], avgs["montant_total_finance"]) * 100,
        "par7": safe_ratio(avgs["encours_retard_7"], avgs["encours_total"]) * 100,
        "taux_paiement_temps": safe_ratio(sums["paiements_temps"], sums["paiements_attendus"]) * 100,
        "montant_moyen": safe_ratio(sums["total_collecte"], last["nombre_beneficiaires"]),
        "recovery_rate": safe_ratio(sums["montant_recupere"], sums["montant_total_prete"]) * 100,
        "taux_motos_actives": safe_ratio(avgs["motos_actives"], avgs["total_motos"]) * 100,
        "taux_utilisation": safe_ratio(sums["jours_actifs"], sums["jours_totaux"]) * 100,
        "moyenne_courses": safe_ratio(sums["courses"], days),
        "temps_inactivite": safe_ratio(sums["jours_sans_activite"], days),
        "taux_pannes": safe_ratio(avgs["motos_panne"], avgs["total_motos"]) * 100,
        "revenu_moyen_social": safe_ratio(sums["revenus_estimes"], sums["nombre_beneficiaires"]),
        "taux_maintien": safe_ratio(last["beneficiaires_actifs"], first["beneficiaires_initial"]) * 100,
        "emplois_crees": last["emplois_directs"] + last["emplois_indirects"],
        "amelioration_revenus": (safe_ratio(sums["revenus_apres"], sums["revenus_avant"]) - 1) * 100,
        "taux_digitalisation": safe_ratio(sums["paiements_digitaux"], sums["paiements_totaux"]) * 100,
        "volume_transactions": sums["volume_transactions"],
        "revenus_fintech": sums["commissions"],
        "nb_utilisateurs_actifs": last["utilisateurs_actifs"],
        "freq_utilisation": safe_ratio(sums["transactions"], last["nombre_beneficiaires"]),
        "taux_visites": safe_ratio(sums["visites_realisees"], sums["visites_prevues"]) * 100,
        "delai_reaction": avgs["delai_reaction"],
        "visites_par_benef": safe_ratio(sums["visites_realisees"], last["nombre_beneficiaires"]),
        "taux_resolution": safe_ratio(sums["incidents_resolus"], sums["incidents_detectes"]) * 100,
        "nb_beneficiaires_retard": sums["beneficiaires_retard"] if mode == "weekly" else last["beneficiaires_retard"],
        "retard_moyen": safe_ratio(sums["retard_total_jours"], sums["beneficiaires_retard"]),
        "recovery_apres_defaut": safe_ratio(sums["montant_recupere_apres_defaut"], sums["montant_en_defaut"]) * 100,
        "motos_recuperees": sums["motos_recuperees"],
        "rentabilite": sums["montant_total_rembourse"] + sums["commissions"] - sums["cout_total_projet"],
        "cout_par_benef": safe_ratio(sums["cout_total_projet"], last["nombre_beneficiaires"]),
        "taux_croissance": (safe_ratio(last["beneficiaires_finances"], first["beneficiaires_finances"]) - 1) * 100,
    }
    values["hebdo_remboursement"] = values["taux_remboursement"]
    values["hebdo_nb_retards"] = sums["beneficiaires_retard"]
    values["hebdo_par7"] = values["par7"]
    values["hebdo_motos_actives"] = values["taux_motos_actives"]
    values["hebdo_visites"] = values["taux_visites"]
    return values


def format_value(value: float, unit: str) -> str:
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "FCFA":
        return f"{value:,.0f} FCFA".replace(",", " ")
    if unit == "jours":
        return f"{value:.1f} j"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.1f}"
    return f"{value:,.0f}".replace(",", " ")


def format_delta(value: float, unit: str) -> str:
    if unit == "%":
        return f"{value:+.1f} pts"
    if unit == "FCFA":
        return f"{value:+,.0f} FCFA".replace(",", " ")
    if unit == "jours":
        return f"{value:+.1f} j"
    return f"{value:+.1f}" if isinstance(value, float) and not value.is_integer() else f"{value:+,.0f}".replace(",", " ")


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


def frequency_options(indicator: Indicator) -> list[dict[str, str]]:
    if indicator.frequency == "both":
        return [{"label": "Mensuel", "value": "monthly"}, {"label": "Hebdomadaire", "value": "weekly"}]
    if indicator.frequency == "weekly":
        return [{"label": "Hebdomadaire", "value": "weekly"}]
    if indicator.frequency == "daily":
        return [{"label": "Quotidien", "value": "daily"}]
    return [{"label": "Mensuel", "value": "monthly"}]


def group_options() -> list[dict[str, str]]:
    return [{"label": label, "value": key} for key, label in GROUPS.items()]


def indicators_for_group(group: str) -> list[Indicator]:
    return [indicator for indicator in INDICATORS if indicator.group == group]


def indicator_options(group: str) -> list[dict[str, str]]:
    return [{"label": indicator.name, "value": indicator.key} for indicator in indicators_for_group(group)]


def kpi_card(title: str, value: str, status: str, color: str, button_id: dict | None = None) -> html.Div:
    children = [
        html.Div(html.Span(status, className="alert", style={"backgroundColor": color}), className="card-top"),
        html.H3(title),
    ]
    if value:
        children.append(html.Div(value, className="big-value"))
    if button_id:
        children.append(html.Button("Ouvrir", id=button_id, n_clicks=0, className="open-button"))
    return html.Div(children, className="kpi-card", style={"borderTopColor": color})


def indicator_card(indicator: Indicator, values: dict[str, float]) -> html.Div:
    _, status, color = alert_for(indicator, values.get(indicator.key, 0))
    return kpi_card(
        indicator.name,
        format_value(values.get(indicator.key, 0), indicator.unit),
        status,
        color,
        {"type": "indicator-button", "indicator": indicator.key},
    )


def selected_value_card(indicator: Indicator, value: float) -> html.Div:
    _, status, color = alert_for(indicator, value)
    return kpi_card(indicator.name, format_value(value, indicator.unit), status, color)


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


def indicator_timeseries(indicator: Indicator, mode: str) -> pd.DataFrame:
    rows = []
    if mode == "daily":
        for day, frame in SAMPLE_DATA.groupby("date"):
            rows.append({"periode": day, "value": compute_metrics(frame, "daily")[indicator.key]})
    elif mode == "weekly":
        for week, frame in SAMPLE_DATA.groupby("week_start"):
            rows.append({"periode": week, "value": compute_metrics(frame, "weekly")[indicator.key]})
    else:
        for month, frame in SAMPLE_DATA.groupby("month"):
            rows.append({"periode": month, "value": compute_metrics(frame, "monthly")[indicator.key]})
    return pd.DataFrame(rows)


def build_trend_chart(indicator: Indicator, mode: str) -> go.Figure:
    series = indicator_timeseries(indicator, mode)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=series["periode"],
            y=series["value"],
            mode="lines+markers",
            line={"color": ACCENT, "width": 3},
            marker={"size": 7, "color": ACCENT},
            fill="tozeroy",
            fillcolor="rgba(15, 118, 110, 0.11)",
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
    fig.update_yaxes(title=indicator.unit, gridcolor="#edf2f7", zerolinecolor="#dbe3ea")
    fig.update_xaxes(showgrid=False)
    return fig


def home_block(group: str, values: dict[str, float]) -> html.Div:
    indicators = indicators_for_group(group)
    states = [alert_for(indicator, values.get(indicator.key, 0))[0] for indicator in indicators]
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
    default_indicator = indicators_for_group(default_group)[0]
    return html.Div(
        [
            dcc.Store(id="selected-page", data="accueil"),
            dcc.Store(id="upload-refresh", data=0),
            html.Header(
                [
                    html.Div(
                        [
                            html.H1("Dashboard KPI CAMOTO"),
                            html.P("Accueil, blocs KPI, alertes, comparaisons mensuelles et hebdomadaires."),
                        ]
                    ),
                    html.Div(
                        [
                            dcc.Upload(id="data-upload", children=html.Button("Importer Excel", className="secondary-button"), accept=".xlsx", multiple=False),
                            html.A("Modele Excel", href="/assets/data_template.xlsx", className="template-link"),
                            html.Button("Accueil", id="home-button", n_clicks=0, className="secondary-button"),
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
                            html.Div([html.Label("Bloc KPI"), dcc.Dropdown(group_options(), default_group, id="group-filter", clearable=False)], className="filter-field"),
                            html.Div([html.Label("Indicateur"), dcc.Dropdown(indicator_options(default_group), default_indicator.key, id="indicator-filter", clearable=False)], className="filter-field"),
                            html.Div(
                                [
                                    html.Label("Frequence"),
                                    dcc.RadioItems(
                                        frequency_options(default_indicator),
                                        "monthly",
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
app.title = "Dashboard KPI CAMOTO"
app.config.suppress_callback_exceptions = True
app.layout = layout


@app.callback(
    Output("selected-page", "data"),
    Output("group-filter", "value"),
    Input("home-button", "n_clicks"),
    Input({"type": "group-button", "group": ALL}, "n_clicks"),
    Input({"type": "indicator-button", "indicator": ALL}, "n_clicks"),
    State("selected-page", "data"),
    State("group-filter", "value"),
)
def navigate(home_clicks: int, group_clicks: list[int], indicator_clicks: list[int], selected_page: str, current_group: str):
    triggered = callback_context.triggered_id
    if triggered == "home-button":
        return "accueil", current_group
    if isinstance(triggered, dict) and triggered.get("type") == "group-button":
        group = triggered["group"]
        return ("hebdo-home" if group == "hebdo" else "dashboard"), group
    if isinstance(triggered, dict) and triggered.get("type") == "indicator-button":
        return "dashboard", current_group
    return selected_page, current_group


@app.callback(
    Output("indicator-filter", "options"),
    Output("indicator-filter", "value"),
    Input("group-filter", "value"),
    Input({"type": "indicator-button", "indicator": ALL}, "n_clicks"),
    State("indicator-filter", "value"),
)
def sync_indicator(group: str, indicator_clicks: list[int], selected_indicator: str):
    options = indicator_options(group)
    allowed = {option["value"] for option in options}
    triggered = callback_context.triggered_id
    if isinstance(triggered, dict) and triggered.get("type") == "indicator-button" and triggered["indicator"] in allowed:
        return options, triggered["indicator"]
    if selected_indicator in allowed:
        return options, selected_indicator
    return options, options[0]["value"]


@app.callback(
    Output("period-mode", "options"),
    Output("period-mode", "value"),
    Input("indicator-filter", "value"),
    State("period-mode", "value"),
)
def sync_frequency(indicator_key: str, requested_mode: str):
    indicator = INDICATOR_BY_KEY[indicator_key]
    options = frequency_options(indicator)
    allowed = {option["value"] for option in options}
    return options, requested_mode if requested_mode in allowed else options[0]["value"]


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
    global SAMPLE_DATA
    if not contents:
        return "", refresh
    try:
        _, encoded = contents.split(",", 1)
        decoded = base64.b64decode(encoded)
        sheets = pd.read_excel(io.BytesIO(decoded), sheet_name=None, engine="openpyxl")
        frame = pd.concat(sheets.values(), ignore_index=True)
        SAMPLE_DATA = prepare_data(frame)
        return f"Import reussi: {filename} ({len(SAMPLE_DATA)} lignes).", refresh + 1
    except Exception as exc:
        return f"Import impossible: {exc}", refresh


@app.callback(
    Output("page-content", "children"),
    Output("day-filter", "disabled"),
    Output("week-filter", "disabled"),
    Output("month-filter", "disabled"),
    Output("filter-note", "children"),
    Output("sidebar", "className"),
    Output("main-shell", "className"),
    Input("selected-page", "data"),
    Input("group-filter", "value"),
    Input("indicator-filter", "value"),
    Input("month-filter", "value"),
    Input("week-filter", "value"),
    Input("day-filter", "value"),
    Input("period-mode", "value"),
    Input("upload-refresh", "data"),
)
def render_page(selected_page: str, group: str, indicator_key: str, selected_month: str, selected_week: str, selected_day: str, mode: str, refresh: int):
    if not indicator_key or indicator_key not in INDICATOR_BY_KEY:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update

    if selected_page == "accueil":
        current, _, current_label, _ = filter_period(selected_day, selected_week, selected_month, "monthly")
        values = compute_metrics(current, "monthly")
        return (
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Accueil", className="eyebrow"),
                            html.H2("Vue generale des indicateurs"),
                            html.P(f"Etat general calcule sur le mois selectionne: {current_label}. Cliquez sur un bloc pour ouvrir son dashboard."),
                        ],
                        className="section-title home-title",
                    ),
                    html.Div([home_block(group_key, values) for group_key in GROUPS], className="cards-grid home-grid"),
                ],
                className="home-panel",
            ),
            True,
            True,
            False,
            "Accueil: le mois reste actif pour calculer l'etat general des blocs.",
            "sidebar is-hidden",
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
                            html.P(f"Indicateurs indispensables de la semaine selectionnee: {current_label}. Cliquez sur un indicateur pour ouvrir son dashboard."),
                        ],
                        className="section-title home-title",
                    ),
                    html.Div([indicator_card(indicator, values) for indicator in indicators_for_group("hebdo")], className="cards-grid hebdo-home-grid"),
                ],
                className="home-panel",
            ),
            True,
            False,
            True,
            "KPI Hebdo: accueil des indicateurs hebdomadaires.",
            "sidebar is-hidden",
            "shell home-shell",
        )

    if INDICATOR_BY_KEY[indicator_key].group != group:
        indicator_key = indicators_for_group(group)[0].key

    indicator = INDICATOR_BY_KEY[indicator_key]
    mode_options = frequency_options(indicator)
    allowed_modes = {option["value"] for option in mode_options}
    mode = mode if mode in allowed_modes else mode_options[0]["value"]
    current, previous, current_label, previous_label = filter_period(selected_day, selected_week, selected_month, mode)
    values = compute_metrics(current, mode)
    previous_values = compute_metrics(previous, mode) if not previous.empty else compute_metrics(current, mode)
    value = values[indicator.key]
    previous_value = previous_values[indicator.key]
    delta = value - previous_value
    _, status, color = alert_for(indicator, value)
    delta_text, delta_color = delta_status(indicator, delta)

    frequency_label = {"monthly": "Mensuel", "weekly": "Hebdomadaire", "daily": "Quotidien"}[mode]
    disabled_day = mode != "daily"
    disabled_week = mode != "weekly"
    disabled_month = mode != "monthly"
    note = f"Mode {frequency_label}: le filtre compatible est actif; les autres sont desactives."

    selected_indicator_card = selected_value_card(indicator, value)

    return (
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(GROUPS[group], className="eyebrow"),
                                html.H2(f"Dashboard {GROUPS[group]}"),
                                html.P("La premiere carte affiche la valeur, la carte suivante affiche uniquement l'ecart."),
                            ],
                            className="section-title",
                        ),
                        html.Div(className="period-pill", children=current_label),
                    ],
                    className="dashboard-title-row",
                ),
                html.Div([selected_indicator_card], className="cards-grid single-indicator-grid indicator-grid"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span(delta_text, className="alert", style={"backgroundColor": delta_color}),
                                html.Div(format_delta(delta, indicator.unit), className="hero-value"),
                                html.P(f"vs {previous_label}", className="muted"),
                            ],
                            className="summary-main",
                        ),
                        html.Div(
                            [
                                html.Div([html.Span("Indicateur"), html.Strong(indicator.name)]),
                                html.Div([html.Span("Frequence"), html.Strong(frequency_label)]),
                                html.Div([html.Span("Sens attendu"), html.Strong("Hausse" if indicator.higher_is_better else "Baisse")]),
                            ],
                            className="summary-details",
                        ),
                    ],
                    className="indicator-summary",
                ),
                html.Div(
                    [
                        html.Div([html.H3("Comparaison"), html.P("Mois M vs M-1, semaine choisie vs semaine precedente, ou jour vs J-1.")], className="chart-copy"),
                        dcc.Graph(figure=build_comparison_chart(indicator, value, previous_value, current_label, previous_label), config={"displayModeBar": False}),
                    ],
                    className="chart-panel",
                ),
                html.Div(
                    [
                        html.Div([html.H3("Tendance"), html.P("Evolution historique de l'indicateur selectionne.")], className="chart-copy"),
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
            .open-button { background: #0f766e; margin-top: 14px; }
            .template-link { min-height: 40px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--line); border-radius: 7px; background: #fff; color: #0f766e; font-size: 13px; font-weight: 850; padding: 0 12px; text-decoration: none; }
            .shell { max-width: 1480px; margin: 0 auto; padding: 24px; display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 22px; align-items: start; }
            .shell.home-shell { max-width: 1180px; grid-template-columns: 1fr; }
            .content-stack { display: grid; gap: 14px; min-width: 0; }
            .upload-status { color: #0f766e; font-size: 13px; font-weight: 800; }
            .sidebar { position: sticky; top: 18px; background: white; border: 1px solid var(--line); border-radius: 8px; padding: 18px; display: grid; gap: 16px; box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06); }
            .sidebar.is-hidden { display: none; }
            .sidebar-title { display: grid; gap: 4px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
            .eyebrow { color: #0f766e; font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: 0; }
            .filter-field { display: grid; gap: 7px; }
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
            .kpi-card { background: white; border: 1px solid var(--line); border-top: 5px solid #17663a; border-radius: 8px; padding: 16px; min-height: 154px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05); transition: transform 160ms ease, box-shadow 160ms ease; }
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
            .chart-copy { display: grid; gap: 6px; margin-bottom: 8px; }
            .muted { font-size: 13px; }
            .Select-control { border-color: var(--line) !important; border-radius: 7px !important; min-height: 40px; }
            .Select-placeholder, .Select-value-label { font-weight: 750; color: #334155 !important; }
            @media (max-width: 1080px) {
                .shell { grid-template-columns: 1fr; }
                .sidebar { position: static; }
                .cards-grid, .hebdo-home-grid { grid-template-columns: repeat(2, minmax(220px, 1fr)); }
                .indicator-summary { grid-template-columns: 1fr; }
            }
            @media (max-width: 680px) {
                .app-header { padding: 18px; align-items: start; flex-direction: column; }
                .header-actions { justify-content: flex-start; }
                .shell { padding: 16px; }
                .cards-grid, .hebdo-home-grid { grid-template-columns: 1fr; }
                .dashboard-title-row { flex-direction: column; }
                .period-pill { white-space: normal; }
                .hero-value { font-size: 34px; }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>{%config%}{%scripts%}{%renderer%}</footer>
    </body>
</html>
"""


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060)
