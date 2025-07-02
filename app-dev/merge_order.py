import html
import io
from collections.abc import Generator
from itertools import product

import pandas as pd
from _templates import merge_preview_template
from excel_helpers import export_excel, load_excel
from js import URL, File, Uint8Array
from order_file_io import load_order_file
from order_settings import (
    PLATFORM_NAME_COLUMN_NAME,
    PlatformHeaderVariableMap,
    find_matching_variable_map,
    load_order_variables_from_local_storage,
)
from pyscript import document, window


def translate_df(
    target_df: pd.DataFrame, variable_map: PlatformHeaderVariableMap
) -> pd.DataFrame:
    translated_df = pd.DataFrame()
    relevant_mappings = {
        key: value
        for key, value in variable_map.variable_mapping.items()
        if len(value) > 0
    }
    # Note that pd.concat is not suitable here
    # since it does not allow duplicating values.
    # some platforms might use one column for multiple unified variables.
    # or they can simply have the same values.
    # i.e. (reciepient_phone_number, buyer_phone_number) could be the smae.
    for unified_header, platform_header in relevant_mappings.items():
        translated_df[unified_header] = target_df[platform_header]
    translated_df[PLATFORM_NAME_COLUMN_NAME] = variable_map.platform
    return translated_df


def translated_first_rows() -> Generator[tuple[str, pd.DataFrame]]:
    from order_file_io import _order_files

    variable_mapping = load_order_variables_from_local_storage()
    for file_name in _order_files:
        try:
            file_bytes = load_order_file(file_name)
            variable_map = find_matching_variable_map(
                file_bytes, variable_mapping.platform_header_variable_maps
            )
            if variable_map is None:
                window.console.log("Could not find the matching platform.")
            else:
                original_df = load_excel(
                    file_bytes, header_row=variable_map.header, nrows=1
                )
                yield file_name, translate_df(original_df, variable_map)
        except KeyError:  # noqa: PERF203
            # Skip the encrypted file with invalid password.
            ...


def render_merge_preview() -> str:
    variable_mapping = load_order_variables_from_local_storage()
    rows = []
    for file_name, translated in translated_first_rows():
        row = [file_name]
        for i_row, col in product(
            range(len(translated)),
            (PLATFORM_NAME_COLUMN_NAME, *variable_mapping.unified_header),
        ):
            if col not in translated.columns:
                row.append('')
            else:
                cell = translated.at[i_row, col]
                if (item_length := len(cell)) > 2:
                    hidden_part = '-' * (item_length - 2)
                    row.append(html.escape(cell[:2] + hidden_part))
                else:
                    row.append(html.escape(cell))
        rows.append(row)

    return merge_preview_template.render(
        header_items=[
            '통합변수',
            PLATFORM_NAME_COLUMN_NAME,
            *variable_mapping.unified_header,
        ],
        rows=rows,
    )


def refresh_merge_file_preview() -> None:
    preview = document.getElementById("order-render-preview-box")
    table = document.createElement("table")
    table.innerHTML = render_merge_preview()
    for child in preview.children:
        child.remove()
    preview.appendChild(table)


def _make_merged_file_name() -> str:
    today_as_str = pd.Timestamp.now().strftime("%Y-%m-%d")
    return f"merged-orders-{today_as_str}.xlsx"


def merge_orders() -> pd.DataFrame:
    from order_file_io import _order_files

    variable_mapping = load_order_variables_from_local_storage()
    # Starts with an empty DataFrame.
    dfs = [pd.DataFrame(columns=variable_mapping.unified_header)]
    for file_name in _order_files:
        try:
            file_bytes = load_order_file(file_name)
            variable_map = find_matching_variable_map(
                file_bytes, variable_mapping.platform_header_variable_maps
            )
            if variable_map is None:
                window.console.log("Could not find the matching platform.")
            else:
                original_df = load_excel(file_bytes, variable_map.header)
                translated = translate_df(original_df, variable_map)
                dfs.append(translated)
        except KeyError:  # noqa: PERF203
            # Skip the encrypted file with invalid password.
            ...
    # Fill empty string for nan values.
    return pd.concat(dfs, ignore_index=True).fillna('')


def download_merged_orders(_):
    window.console.log("Merging the order files.")
    merged = merge_orders()
    # Download the merged file.
    bytes = io.BytesIO()
    export_excel(merged, bytes)
    bytes_buffer = bytes.getbuffer()
    js_array = Uint8Array.new(bytes_buffer.nbytes)
    js_array.assign(bytes_buffer)

    file_name = _make_merged_file_name()
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
