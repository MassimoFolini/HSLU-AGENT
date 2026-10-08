import sys
from main import weekly_job

# Optional: python run_weeks.py "KW 41 (08.10.2026)" - ohne Argument wird die aktuelle Woche verwendet
weekly_job(force_week_str=sys.argv[1] if len(sys.argv) > 1 else None)
print("Manueller Lauf abgeschlossen!")
