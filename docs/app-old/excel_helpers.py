import io
import pathlib

import pandas as pd


def load_excel(
    file_path: pathlib.Path | io.BytesIO, header_row: int = 0, nrows: int | None = None
) -> pd.DataFrame:
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Workbook contains no default style, apply openpyxl's default",
            category=UserWarning,
        )  # Filter warning about style.
        return (
            pd.read_excel(
                file_path,
                header=header_row,
                dtype=str,
                nrows=nrows,
            )
            .dropna(how='all')
            .fillna("")
        )


def _adjust_column_width(sheet, ref_df: pd.DataFrame) -> None:
    for i_col, col in enumerate(ref_df.columns):
        max_length = max(
            int(ref_df[col].astype(str).map(len).max()) if len(ref_df) > 0 else 0,
            len(col),
        )
        sheet.set_column(i_col, i_col, min(max_length * 2 + 1, 50))


def export_excel(
    df: pd.DataFrame,
    output_file_path: pathlib.Path | io.BytesIO,
    pretty: bool = True,
    export_sheet_name: str | None = "Sheet1",
    startrow: int = 0,
) -> None:
    export_sheet_name = export_sheet_name or "Sheet1"
    with pd.ExcelWriter(output_file_path, engine="xlsxwriter") as writer:
        df.to_excel(excel_writer=writer, index=False, sheet_name=export_sheet_name, startrow=startrow)
        if pretty:
            for sheet in writer.sheets.values():
                _adjust_column_width(sheet, df)
