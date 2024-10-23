import html
import io
import json
from collections import OrderedDict
from collections.abc import Generator, Hashable
from dataclasses import dataclass
from itertools import product

import pandas as pd
from _templates import delivery_format_preview_template
from excel_helpers import export_excel
from jinja2 import Template
from js import URL, File, Uint8Array
from merge_order import merge_orders, translated_first_rows
from pyscript import document, window

DELIVERY_AGENCY_NAME_COLUMN_NAME = "DeliveryAgency"


def _render_template(
    i_row: Hashable, row: pd.Series, templates: OrderedDict[str, Template]
) -> pd.DataFrame:
    variables = {col: str(row[col]) for col in row.index}
    return pd.DataFrame(
        {col: template.render(variables) for col, template in templates.items()},
        index=[i_row],
    )


@dataclass
class DeliveryFormat:
    """Delivery information schema."""

    delivery_agency: str
    templates: OrderedDict[str, Template]

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "DeliveryFormat":
        """Dataframe should only have one row."""
        delivery_agency = df.at[0, DELIVERY_AGENCY_NAME_COLUMN_NAME]
        templates_df = df.drop(columns=[DELIVERY_AGENCY_NAME_COLUMN_NAME])
        templates = OrderedDict()
        for col in templates_df.columns:
            templates[col] = Template(templates_df.at[0, col])
        return cls(delivery_agency=delivery_agency, templates=templates)


def order_to_delivery_format(
    target_df: pd.DataFrame, delivery_format: DeliveryFormat
) -> pd.DataFrame:
    base_df = pd.DataFrame(columns=tuple(delivery_format.templates.keys()))
    new_rows = [
        _render_template(i_row, order_info_row, delivery_format.templates)
        for i_row, order_info_row in target_df.iterrows()
    ]
    return pd.concat([base_df, *new_rows], verify_integrity=True)


def delivery_format_fisrt_rows() -> Generator[tuple[str, pd.DataFrame]]:
    delivery_format = load_delivery_format_from_local_storage()
    for file_name, translated in translated_first_rows():
        yield file_name, order_to_delivery_format(translated, delivery_format)


def render_delivery_format_preview() -> str:
    delivery_format = load_delivery_format_from_local_storage()

    delivery_format_headers = tuple(delivery_format.templates.keys())
    rows = []
    for file_name, translated in delivery_format_fisrt_rows():
        row = [file_name]
        for i_row, col in product(range(len(translated)), delivery_format_headers):
            if col not in delivery_format_headers:
                row.append('')
            else:
                cell = translated.at[i_row, col]
                if (item_length := len(cell)) > 2:
                    hidden_part = '-' * (item_length - 2)
                    row.append(html.escape(cell[:2] + hidden_part))
                else:
                    row.append(html.escape(cell))
        rows.append(row)

    return delivery_format_preview_template.render(
        header_items=["파일출처", *delivery_format.templates.keys()],
        rows=rows,
    )


def refresh_delivery_format_file_preview() -> None:
    preview = document.getElementById("delivery-format-render-preview-box")
    table = document.createElement("div")
    table.innerHTML = render_delivery_format_preview()
    for child in preview.children:
        child.remove()
    preview.appendChild(table)


def _make_delivery_file_name(agency_name: str = '') -> str:
    today_as_str = pd.Timestamp.now().strftime("%Y-%m-%d")
    return f"merged-{agency_name}-{today_as_str}.xlsx"


def download_orders_in_delivery_format(_):
    window.console.log("Transforming the merged files into delivery format...")
    merged = merge_orders()
    delivery_form = load_delivery_format_from_local_storage()
    delivery_format_merged = order_to_delivery_format(merged, delivery_form)
    # Download the merged file.
    bytes = io.BytesIO()
    export_excel(delivery_format_merged, bytes)
    bytes_buffer = bytes.getbuffer()
    js_array = Uint8Array.new(bytes_buffer.nbytes)
    js_array.assign(bytes_buffer)

    file_name = _make_delivery_file_name(delivery_form.delivery_agency)
    file = File.new([js_array], file_name, {type: "text/plain"})
    url = URL.createObjectURL(file)

    hidden_link = document.createElement("a")
    hidden_link.setAttribute("download", file_name)
    hidden_link.setAttribute("href", url)
    hidden_link.click()
    # Release the object URL and clean up.
    URL.revokeObjectURL(url)
    hidden_link.remove()
    del hidden_link


# Settings related.
_DELIVERY_FORMAT_SETTING_LOCAL_SOTRAGE_KEY = "DELIVERY-FORMAT-SETTINGS"
"""DO NOT CHANGE THIS VALUE. THIS IS A KEY TO THE LOCAL STORAGE."""

DEFAULT_DELIVERY_FORMAT_FILE_PATH = "_resources/default_krbiz_delivery_format.xlsx"


def _update_delivery_format_in_local_storage(new_df: pd.DataFrame) -> None:
    """Update the delivery format in lthe ocal storage."""
    local_storage = window.localStorage
    if local_storage.getItem(_DELIVERY_FORMAT_SETTING_LOCAL_SOTRAGE_KEY) is not None:
        window.console.log("Overwriting the existing order header variable settings.")
    delivery_format_str = json.dumps(new_df.to_dict(), ensure_ascii=False)
    local_storage.setItem(
        _DELIVERY_FORMAT_SETTING_LOCAL_SOTRAGE_KEY, delivery_format_str
    )


def _initialize_delivery_format_in_local_storage() -> None:
    window.console.log("Initializing delivery format from the default file.")
    delivery_format_df = pd.read_excel(
        DEFAULT_DELIVERY_FORMAT_FILE_PATH,
        header=0,
        dtype=str,
        sheet_name="delivery_schema",
    )
    _update_delivery_format_in_local_storage(delivery_format_df)


def load_delivery_format_as_dataframe_from_local_storage() -> pd.DataFrame:
    local_storage = window.localStorage
    if local_storage.getItem(_DELIVERY_FORMAT_SETTING_LOCAL_SOTRAGE_KEY) is None:
        _initialize_delivery_format_in_local_storage()
    else:
        window.console.log("Found the existing delivery format.")
    try:
        delivery_format_dict = json.loads(
            local_storage.getItem(_DELIVERY_FORMAT_SETTING_LOCAL_SOTRAGE_KEY)
        )
        return pd.DataFrame.from_dict(delivery_format_dict).set_index(pd.Series([0]))
        # The row index is saved as string in the local storage.
        # So it should be converted to integer so that other methods can easily use it.
    except Exception as e:
        # TODO: Ask the user to reset the settings as well.
        window.console.log(
            "Error occurred while loading existing delivery formats. "
            "Please reset the settings."
        )
        raise e


def load_delivery_format_from_local_storage() -> DeliveryFormat:
    try:
        df = load_delivery_format_as_dataframe_from_local_storage()
        return DeliveryFormat.from_dataframe(df)
    except Exception:
        confirm_msg = "배송양식 설정을 불러오는 데에 문제가 생겼습니다.\n"
        confirm_msg += "설정을 초기화 한 뒤 다시 시도하시겠습니까?\n"
        if window.confirm(confirm_msg):
            _initialize_delivery_format_in_local_storage()
        df = load_delivery_format_as_dataframe_from_local_storage()
        return DeliveryFormat.from_dataframe(df)
