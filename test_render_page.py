import sys
import os

# Add the workspace directory to path
sys.path.append(r"c:\Users\USER\Desktop\dashboard2")

import pandas as pd
from app import render_page, default_periods, INDICATORS, GROUPS

print("Imported app successfully.")

month, week, day = default_periods()
print(f"Default periods: month={month}, week={week}, day={day}")

pages = ["accueil", "previous-month", "hebdo-home", "group-overview", "dashboard"]

for page in pages:
    print(f"\n================ PAGE: {page} ================")
    if page == "group-overview":
        for group in list(GROUPS.keys()) + ["risque", "terrain"]:
            try:
                res = render_page(
                    selected_page=page,
                    group=group,
                    indicator_key="performance_mensuelle",
                    selected_month=month,
                    selected_week=week,
                    selected_day=day,
                    mode="monthly",
                    refresh=0,
                    requested_indicator=None
                )
                print(f"group-overview [{group}]: success")
            except Exception as e:
                import traceback
                print(f"group-overview [{group}]: FAILED!")
                traceback.print_exc()
    elif page == "dashboard":
        for indicator in INDICATORS:
            for mode in ["daily", "weekly", "monthly"]:
                try:
                    res = render_page(
                        selected_page=page,
                        group=indicator.group,
                        indicator_key=indicator.key,
                        selected_month=month,
                        selected_week=week,
                        selected_day=day,
                        mode=mode,
                        refresh=0,
                        requested_indicator=None
                    )
                except Exception as e:
                    import traceback
                    print(f"dashboard [{indicator.key}, group={indicator.group}, mode={mode}]: FAILED!")
                    traceback.print_exc()
    else:
        try:
            res = render_page(
                selected_page=page,
                group="financier",
                indicator_key="performance_mensuelle",
                selected_month=month,
                selected_week=week,
                selected_day=day,
                mode="monthly",
                refresh=0,
                requested_indicator=None
            )
            print(f"{page}: success")
        except Exception as e:
            import traceback
            print(f"{page}: FAILED!")
            traceback.print_exc()

print("\nAll tests completed.")
