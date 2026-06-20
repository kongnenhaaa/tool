from __future__ import annotations

import pandas as pd
from utils import format_phone_number


def read_input_excel(path: str) -> list[dict]:
	df = pd.read_excel(path, engine="openpyxl")
	df = df.rename(columns={"id": "id", "phone": "phone", "serial": "serial"})

	required = {"id", "phone", "serial"}
	missing = required - set(df.columns)
	if missing:
		raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

	# Fill NaN with empty string across all columns
	df = df.fillna("")

	records: list[dict] = []
	for _, row in df.iterrows():
		record_id = str(row["id"]).strip()
		phone = format_phone_number(row["phone"])
		serial = str(row["serial"]).strip()
		if not record_id or not phone or not serial:
			continue
			
		# Lấy ngày cấp, nơi cấp nếu có
		ngay_cap_val = row.get("ngay_cap", "")
		if pd.isna(ngay_cap_val) or str(ngay_cap_val).strip() == "":
			ngay_cap = ""
		elif isinstance(ngay_cap_val, pd.Timestamp):
			ngay_cap = ngay_cap_val.strftime("%d/%m/%Y")
		else:
			ngay_cap = str(ngay_cap_val).strip()
			
		noi_cap_val = row.get("noi_cap", "")
		noi_cap = "" if pd.isna(noi_cap_val) else str(noi_cap_val).strip()
			
		records.append({
			"id": record_id, 
			"phone": phone, 
			"serial": serial,
			"ngay_cap": ngay_cap,
			"noi_cap": noi_cap
		})
	return records
