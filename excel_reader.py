from __future__ import annotations

import pandas as pd


def read_input_excel(path: str) -> list[dict]:
	df = pd.read_excel(path, engine="openpyxl")
	df = df.rename(columns={"id": "id", "phone": "phone", "serial": "serial"})

	required = {"id", "phone", "serial"}
	missing = required - set(df.columns)
	if missing:
		raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

	df = df[list(required)].fillna("")

	records: list[dict] = []
	for _, row in df.iterrows():
		record_id = str(row["id"]).strip()
		phone = str(row["phone"]).strip()
		serial = str(row["serial"]).strip()
		if not record_id or not phone or not serial:
			continue
		records.append({"id": record_id, "phone": phone, "serial": serial})
	return records
