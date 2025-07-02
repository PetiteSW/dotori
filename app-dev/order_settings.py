import io
import json
import pathlib
from dataclasses import dataclass

import pandas as pd
from excel_helpers import export_excel, load_excel
from js import URL, File, Uint8Array, alert, confirm
from pyscript import document, window

PLATFORM_NAME_COLUMN_NAME = "PlatformName"
HEADER_ROW_COLUMN_NAME = "HeaderRow"


@dataclass
class PlatformHeaderVariableMap:
    """Platform header variable mapping."""

    platform: str
    header: int
    variable_mapping: dict[str, str]


LATEST_ORDER_VARIABLE_CONFIG_FILE_PATH = pathlib.Path(
    "_resources/krbiz_order_unified_row_names.xlsx"
)
DEFAULT_ORDER_VARIABLE_CONFIG_FILE_PATH = pathlib.Path(
    "_resources/default_krbiz_order_unified_row_names.xlsx"
)

_ORDER_VARIABLE_SETTING_LOCAL_STORAGE_KEY = "ORDER-HEADER-VARIABLES"
"""DO NOT CHANGE this without supporting background compatibility."""


def _update_order_variables_in_local_storage(new_df: pd.DataFrame) -> None:
    """Update the order variable in local storage."""
    local_storage = window.localStorage
    if local_storage.getItem(_ORDER_VARIABLE_SETTING_LOCAL_STORAGE_KEY) is not None:
        window.console.log("Overwriting the existing order header variable settings.")
    order_variables_str = json.dumps(new_df.to_dict(), ensure_ascii=False)
    local_storage.setItem(
        _ORDER_VARIABLE_SETTING_LOCAL_STORAGE_KEY, order_variables_str
    )


def _initialize_order_variables_in_local_storage() -> None:
    """Initialize local storage with order variables.

    This function should be called only when the web application
    is loaded for the first time.
    """
    window.console.log("Initializing order variables from the default file.")
    order_variables = pd.read_excel(
        DEFAULT_ORDER_VARIABLE_CONFIG_FILE_PATH,
        header=0,
        dtype=str,
        sheet_name="variable_mapping",
    )
    _update_order_variables_in_local_storage(order_variables)


@dataclass
class VariableMappings:
    """Variable mapping to delivery information headers from different platforms."""

    platform_header_variable_maps: list[PlatformHeaderVariableMap]

    @property
    def unified_header(self) -> tuple[str, ...]:
        from functools import reduce

        key_set_list = [
            set(mapping.variable_mapping.keys())
            for mapping in self.platform_header_variable_maps
        ]
        return tuple(reduce(lambda x, y: x.union(y), key_set_list))

    @classmethod
    def from_dataframe(cls, mapping_df: pd.DataFrame) -> "VariableMappings":
        mapping_df = mapping_df.fillna("")
        return cls(
            platform_header_variable_maps=[
                PlatformHeaderVariableMap(
                    platform=row[PLATFORM_NAME_COLUMN_NAME],
                    header=int(row[HEADER_ROW_COLUMN_NAME]) - 1,
                    variable_mapping={
                        col: row[col]
                        for col in mapping_df.columns
                        if col
                        not in (PLATFORM_NAME_COLUMN_NAME, HEADER_ROW_COLUMN_NAME)
                    },
                )
                for _, row in mapping_df.iterrows()
            ]
        )


def load_order_variables_as_dataframe_from_local_storage() -> pd.DataFrame:
    local_storage = window.localStorage
    if local_storage.getItem(_ORDER_VARIABLE_SETTING_LOCAL_STORAGE_KEY) is None:
        _initialize_order_variables_in_local_storage()
    else:
        window.console.log("Found the existing order variable settings.")
    try:
        order_variables_dict = json.loads(
            local_storage.getItem(_ORDER_VARIABLE_SETTING_LOCAL_STORAGE_KEY)
        )
        return pd.DataFrame.from_dict(order_variables_dict)
    except Exception:
        window.console.log(
            "Error occurred while loading existing variable settings. "
            "Please reset the settings."
        )


def load_order_variables_from_local_storage() -> VariableMappings:
    try:
        df = load_order_variables_as_dataframe_from_local_storage()
        return VariableMappings.from_dataframe(df)
    except Exception:
        confirm_msg = "주문 통합 열 이름 설정을 불러오는 데에 문제가 생겼습니다.\n"
        confirm_msg += "설정을 초기화 한 뒤 다시 시도하시겠습니까?\n"
        if window.confirm(confirm_msg):
            _initialize_order_variables_in_local_storage()
        df = load_order_variables_as_dataframe_from_local_storage()
        return VariableMappings.from_dataframe(df)


def _make_order_variable_preview_row(row_items: list[str]) -> str:
    return (
        '<tr class="table-header"><td class="index-column">'
        + "</td><td>".join(row_items)
        + "</td></tr>"
    )


def refresh_order_variable_setting_view() -> None:
    variable_mappings = load_order_variables_from_local_storage()
    unified_header = variable_mappings.unified_header
    header_row = _make_order_variable_preview_row(
        ["통합변수", PLATFORM_NAME_COLUMN_NAME, HEADER_ROW_COLUMN_NAME, *unified_header]
    )
    # 통합변수 and PLATFORM_NAME_COLUMN_NAME is repeated just to make sure
    # the user can understand that it is part of the variable.
    rows = [
        _make_order_variable_preview_row(
            [
                platform.platform,
                platform.platform,
                str(platform.header + 1),
                *(
                    platform.variable_mapping[unified_var]
                    for unified_var in unified_header
                ),
            ]
        )
        for platform in variable_mappings.platform_header_variable_maps
    ]
    preview_box = document.getElementById("order-variable-setting-view-box")
    table = document.createElement("table")
    # Clear the box
    for child in preview_box.children:
        child.remove()
    # Append the table
    table.innerHTML = f'<table>{"".join([header_row, *rows])}</table>'
    preview_box.appendChild(table)


def find_matching_variable_map(
    bytes: io.BytesIO, variable_maps: list[PlatformHeaderVariableMap]
) -> PlatformHeaderVariableMap | None:
    for variable_map in variable_maps:
        try:
            df = load_excel(bytes, variable_map.header)
        except ValueError:  # Header row does not work  # noqa: PERF203
            ...
        else:
            if all(
                platform_header in df.columns
                for platform_header in variable_map.variable_mapping.values()
                if len(platform_header) > 0  # Skip empty cells
            ):
                return variable_map
    return None


def _has_new_order_variable_setting_mandatory_columns(df: pd.DataFrame) -> bool:
    return (
        PLATFORM_NAME_COLUMN_NAME in df.columns and HEADER_ROW_COLUMN_NAME in df.columns
    )


def _is_new_order_variable_setting_header_row_integers(df: pd.DataFrame) -> bool:
    try:
        for item in df.get(HEADER_ROW_COLUMN_NAME, []):
            int(item)
        return True
    except ValueError:
        return False


def _collect_invalid_column_names(df: pd.DataFrame) -> list[str]:
    import re

    python_variable_pattern = re.compile("^[a-zA-Z_][a-zA-Z0-9_]{0,78}$")

    return [
        col_name
        for col_name in df.columns
        if not python_variable_pattern.match(col_name)
    ]


async def upload_new_order_variable_settings(e) -> None:
    if len(files := list(e.target.files)) == 0:
        window.console.log("No file selected.")
        return
    uploaded_file = next(iter(files))  # New setting file should be only 1.
    window.console.log(f"New setting file uploaded: {uploaded_file.name}")
    array_buf = await uploaded_file.arrayBuffer()
    bytes = io.BytesIO(array_buf.to_bytes())
    df = load_excel(bytes)
    window.console.log(df.to_string())
    err_msg = ""
    if not _has_new_order_variable_setting_mandatory_columns(df):
        err_msg = f"필수 항목인 '{PLATFORM_NAME_COLUMN_NAME}' 과 "
        err_msg += f"'{HEADER_ROW_COLUMN_NAME}'를 찾을 수 없습니다.\n"
        err_msg += "파일을 확인 후 다시 등록해주세요.\n\n"
    if not _is_new_order_variable_setting_header_row_integers(df):
        err_msg += f"{HEADER_ROW_COLUMN_NAME} 행은 모두 숫자여야 합니다.\n"
        err_msg += "해당 행은 각 플랫폼 별 파일의 행이름이"
        err_msg += "몇 번 째 열에 위치하는지를 의미합니다.\n"
        err_msg += "파일을 확인 후 다시 시도해주세요.\n\n"
    if invalid_names := _collect_invalid_column_names(df):
        err_msg += "아래 이름은 통합 행 이름으로 적합하지 않습니다.\n"
        err_msg += '\n'.join(invalid_names) + '\n'
        err_msg += "행 이름은 숫자로 시작할 수 없고 "
        err_msg += "영문과 숫자, '_' 기호로만 이루어져야 합니다..\n"
        err_msg += "설정 파일을 수정 후 다시 시도해주세요.\n\n"

    if len(err_msg) > 0:
        # Alert is done once here with all error messages
        # to give all feedbacks at once to the user.
        alert(err_msg)
        return
    # If the file is valid.
    # Save the data frame to the local storage.
    _update_order_variables_in_local_storage(new_df=df)
    # Refresh the settings view.
    refresh_order_variable_setting_view()


def download_current_order_variable_settings(e):
    window.console.log("Preparing the variable setting file.")
    df = load_order_variables_as_dataframe_from_local_storage()
    bytes = io.BytesIO()
    export_excel(df, bytes)
    bytes_buffer = bytes.getbuffer()
    js_array = Uint8Array.new(bytes_buffer.nbytes)
    js_array.assign(bytes_buffer)

    file = File.new(
        [js_array], LATEST_ORDER_VARIABLE_CONFIG_FILE_PATH.name, {type: "text/plain"}
    )
    url = URL.createObjectURL(file)

    hidden_link = document.createElement("a")
    hidden_link.setAttribute("download", LATEST_ORDER_VARIABLE_CONFIG_FILE_PATH.name)
    hidden_link.setAttribute("href", url)
    hidden_link.click()
    # Release the object URL and clean up.
    URL.revokeObjectURL(url)
    hidden_link.remove()
    del hidden_link


def reset_order_variable_settings(_):
    if confirm(
        "설정을 초기화 하시면 이전의 설정사항이 브라우저에서 삭제됩니다. \n"
        "초기화를 진행하시겠습니까?"
    ) and confirm(
        "진짜 지워도 되는거죠?? 🤔"
    ) and confirm(
        "진짜 마지막으로 물어볼게요. 진짜, 진짜로 지웁니다??? 🤨"
    ):
        _initialize_order_variables_in_local_storage()
        refresh_order_variable_setting_view()
        alert("통합 열 ⚙️설정⚙️이 초기화 되었습니다.")
