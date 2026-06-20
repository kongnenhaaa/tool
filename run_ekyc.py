import argparse
import os
import pandas as pd
from pathlib import Path

from playwright_runner import PlaywrightRunner
from utils import format_phone_number


def load_input_data(input_path: str) -> pd.DataFrame:
    """Load input data from Excel or CSV.
    Expected columns: phone, serial, passport_path, portrait_path.
    If passport_path or portrait_path are missing, they will be derived
    from a base folder using the row index (e.g., "1a.jpg", "1b.jpg").
    """
    if input_path.lower().endswith('.xlsx'):
        df = pd.read_excel(input_path, engine="openpyxl")
    elif input_path.lower().endswith('.xls'):
        df = pd.read_excel(input_path)
    else:
        df = pd.read_csv(input_path)
    return df


def derive_file_paths(base_folder: str, index: int) -> tuple[str, str]:
    """Derive passport and portrait file paths based on the index.
    The convention follows the user's description: e.g., "1a.jpg" for passport
    and "1b.jpg" for portrait, "2a.jpg" / "2b.jpg", ...
    """
    passport_file = os.path.join(base_folder, f"{index + 1}a.jpg")
    portrait_file = os.path.join(base_folder, f"{index + 1}b.jpg")
    return passport_file, portrait_file


def process_record(runner: PlaywrightRunner, record: dict, passport_path: str, portrait_path: str, log_func=None) -> tuple[str, str]:
    """Run the eKYC flow for a single record and return status, message."""
    try:
        status, message = runner.run(record, passport_path, portrait_path, log=log_func)
        return status, message
    except Exception as e:
        if log_func:
            log_func(f"Unexpected error for {record}: {e}")
        return "FAILED", str(e)


def main():
    parser = argparse.ArgumentParser(description="Bulk VNPT eKYC automation with fake camera.")
    parser.add_argument("--input", required=True, help="Path to input Excel/CSV file containing phone, serial and optional file columns.")
    parser.add_argument("--output", required=True, help="Path to output Excel file that will contain results.")
    parser.add_argument("--folder", required=False, default="", help="Base folder where passport/portrait images are stored if not specified in the input file.")
    parser.add_argument("--license-key", required=False, help="Optional license key for partner integration (currently unused).")
    args = parser.parse_args()

    df = load_input_data(args.input)
    # Ensure required columns exist
    required = ["phone", "serial"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in input file.")

    # Prepare result list
    results = []
    runner = PlaywrightRunner()
    try:
        for idx, row in df.iterrows():
            record = {"phone": format_phone_number(row["phone"]), "serial": str(row["serial"])}
            # Determine file paths
            if "passport_path" in df.columns and pd.notna(row["passport_path"]):
                passport_path = str(row["passport_path"])
            else:
                passport_path, _ = derive_file_paths(args.folder, idx)

            if "portrait_path" in df.columns and pd.notna(row["portrait_path"]):
                portrait_path = str(row["portrait_path"])
            else:
                _, portrait_path = derive_file_paths(args.folder, idx)

            # Simple stdout logger
            def logger(msg: str):
                print(f"[Record {idx+1}] {msg}")

            status, message = process_record(runner, record, passport_path, portrait_path, log_func=logger)
            result_row = row.to_dict()
            result_row.update({"status": status, "message": message})
            results.append(result_row)
    finally:
        runner.close()

    # Write results to Excel
    result_df = pd.DataFrame(results)
    result_df.to_excel(args.output, index=False, engine="openpyxl")
    print(f"Processing completed. Results saved to {args.output}")

if __name__ == "__main__":
    main()
