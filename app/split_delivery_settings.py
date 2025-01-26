import json
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from js import confirm
from order_settings import load_order_variables_from_local_storage
from pyscript import document, when, window

_DELIVERY_INFO_KEY_SETTING_LOCAL_STORAGE_KEY = "DELIVERY-INFO-KEYS"


@dataclass
class DeliveryInfoKey:
    unified_variable_name: str
    """Unified variable name. i.e. receipients_name"""
    delivery_info_header: str
    """Header of the delivery information. i.e. 수하인명"""


@dataclass
class DeliveryInfoKeysRegistry:
    """Proxy to the local storage."""

    keys: tuple[DeliveryInfoKey, ...]

    def add_key(self, delivery_info_header: str, unified_variable_name: str) -> None:
        new_key = DeliveryInfoKey(
            delivery_info_header=delivery_info_header,
            unified_variable_name=unified_variable_name,
        )
        # Make sure same delivery info header does not exist.
        self.delete_key(delivery_info_header)
        self.keys = (new_key, *self.keys)
        self._save_to_local_storage()
        refresh_delivery_info_keys_table()

    def delete_key(self, delivery_info_header: str) -> None:
        self.keys = tuple(
            key for key in self.keys if key.delivery_info_header != delivery_info_header
        )
        self._save_to_local_storage()

    def _save_to_local_storage(self) -> None:
        self_as_dict = {
            key.delivery_info_header: key.unified_variable_name for key in self.keys
        }
        _update_delivery_info_keys_in_local_storage(self_as_dict)


def initialize_delivery_key_format() -> None:
    unified_variables = load_order_variables_from_local_storage()
    select_input = document.getElementById("unified-variable-key-selection")
    select_input.replaceChildren()
    for var in unified_variables.unified_header:
        new_opt = document.createElement('option')
        new_opt.value = var
        new_opt.innerHTML = var
        select_input.appendChild(new_opt)


def add_delivery_info_key(event=None) -> None:
    if event:
        event.preventDefault()  # Don't know why it is needed,
        # but otherwise it raises error in javascript layer.
        delivery_header_input = document.getElementById("delivery-info-header-key")
        delivery_header_val = delivery_header_input.value
        unified_variable_input = document.getElementById(
            "unified-variable-key-selection"
        )
        unified_variable_val = unified_variable_input.value
        key_registry = load_delivery_info_keys_from_local_storage()
        key_registry.add_key(delivery_header_val, unified_variable_val)
        window.console.log(
            f"New delivery info keys: {delivery_header_val} - {unified_variable_val}"
        )

        # Reset input fields.
        delivery_header_input.value = ""
        if unified_variable_input.children:
            first_child = next(iter(unified_variable_input.children))
            unified_variable_input.value = first_child.value


def _update_delivery_info_keys_in_local_storage(
    new_vars_to_header: dict[str, str],
) -> None:
    window.console.log("Updating delivery info keys in the local storage...")
    local_storage = window.localStorage
    if local_storage.getItem(_DELIVERY_INFO_KEY_SETTING_LOCAL_STORAGE_KEY) is not None:
        window.console.log("Overwriting the existing delivery info keys.")
    delivery_keys_str = json.dumps(new_vars_to_header, ensure_ascii=False)
    local_storage.setItem(
        _DELIVERY_INFO_KEY_SETTING_LOCAL_STORAGE_KEY, delivery_keys_str
    )


def _initialize_delivery_info_keys_in_local_storage() -> None:
    window.console.log("Initializing delivery info keys as defaults.")
    default_vars_to_header = {"고객주문번호": "order_id"}
    _update_delivery_info_keys_in_local_storage(default_vars_to_header)


def load_delivery_info_keys_from_local_storage() -> DeliveryInfoKeysRegistry:
    local_storage = window.localStorage
    if local_storage.getItem(_DELIVERY_INFO_KEY_SETTING_LOCAL_STORAGE_KEY) is None:
        _initialize_delivery_info_keys_in_local_storage()
    else:
        window.console.log("Found the existing delivery keys.")
    try:
        order_variables_dict = json.loads(
            local_storage.getItem(_DELIVERY_INFO_KEY_SETTING_LOCAL_STORAGE_KEY)
        )
        window.console.log(str(order_variables_dict))
        return DeliveryInfoKeysRegistry(
            keys=tuple(
                DeliveryInfoKey(
                    unified_variable_name=unified_var,
                    delivery_info_header=delivery_header,
                )
                for delivery_header, unified_var in order_variables_dict.items()
            )
        )
    except Exception:
        window.console.log(
            "Error occurred while loading existing delivery info keys. "
            "Please reset the settings."
        )


def _make_button_id(delivery_header: str) -> str:
    return f"delivery-key-{delivery_header}-delete-button"


def _make_delete_button(delivery_header: str) -> str:
    button_id = _make_button_id(delivery_header)
    button_tag = (
        '<div class="little-button-box"><button type="button" class="delete-button" '
        + f'id="{button_id}" value="{delivery_header}">'
    )
    trash_icon = '<img src="trash_icon.png" alt="🗑️" height=1em>'
    return f'{button_tag}{trash_icon}</button></div>'


def make_delete_button_event_listener(delivery_header: str) -> Callable:
    def _delete_it(_) -> None:
        if confirm("선택하신 열 이름 짝을 삭제하시겠습니까?") and confirm(
            "진짜 지워요? 🤔"
        ):
            key_registry = load_delivery_info_keys_from_local_storage()
            key_registry.delete_key(delivery_header)
            window.console.log(f"Deleted {delivery_header}")
            refresh_delivery_info_keys_table()
        else:
            window.console.log(f"Canceled deleting {delivery_header}")

    return _delete_it


def refresh_delivery_info_keys_table(_=None) -> None:
    key_registry = load_delivery_info_keys_from_local_storage()
    rows = [
        '<tr>'
        f'<td class="short-column">{key.delivery_info_header}</td>'
        f'<td class="short-column">{key.unified_variable_name}</td>'
        f'<td class="short-column">{_make_delete_button(key.delivery_info_header)}</td>'
        '</tr>'
        for key in key_registry.keys
    ]
    table_str = f"""
        <table>
            <tr class="header-row">
                <td> 배송정보 열 이름 </td>
                <td> 통합 열 이름 </td>
                <td> 삭제 </td>
            </tr>
            {'\n'.join(rows)}
        </table>
    """
    viewer_box = document.getElementById("delivery-info-keys-viewer-box")
    viewer_box.replaceChildren()
    new_table = document.createElement('table')
    new_table.innerHTML = table_str
    viewer_box.appendChild(new_table)
    # Add delete button event listeners
    for key in key_registry.keys:
        button_id = _make_button_id(key.delivery_info_header)
        del_button = document.getElementById(button_id)
        when("click", del_button)(
            make_delete_button_event_listener(key.delivery_info_header)
        )


@dataclass
class DeliveryReportMapping:
    target: str  # Target column to be replaced.


@dataclass
class FromDeliveryConfirmation(DeliveryReportMapping):
    column: str  # Column from delivery confirmation that needs to be replaced.


@dataclass
class FromOriginalOrderFile(DeliveryReportMapping):
    column: str  # Column from order file that needs to be replaced with.


@dataclass
class HardcodedColumn(DeliveryReportMapping):
    value: str  # Hardcoded value for a column.


@dataclass
class _PlatformDeliveryReportSetting:
    headers: pd.DataFrame  # pandas data frame that only has column names.
    # The order is very important.
    mappings: dict[str, DeliveryReportMapping]
    export_sheet_name: str | None = None
    """Sheet name is important for some platforms.

    i.e. Naver requires the excel sheet name to be ``발송처리``.
    """

    def render(
        self, order_row: pd.Series, delivery_row: pd.Series | None
    ) -> pd.DataFrame:
        base = self.headers.copy(deep=True)
        for col in base.columns:
            mapping = self.mappings.get(
                col,
                FromOriginalOrderFile(target=col, column=col),  # Always fall back
            )
            window.console.log(str(mapping))
            # Parse the value based on the mapping setting.
            if isinstance(mapping, FromOriginalOrderFile):
                value = order_row.get(
                    mapping.column, default=""
                )  # Leave it empty if not found.
            elif isinstance(mapping, FromDeliveryConfirmation) and (
                delivery_row is not None
            ):
                value = delivery_row.get(mapping.column, default="")
            elif isinstance(mapping, HardcodedColumn):
                value = mapping.value
            else:
                value = ""

            # Render - one row
            base[col] = [value]
        return base


def _load_excel_file_as_platform_report_setting(
    file_name,
) -> _PlatformDeliveryReportSetting:
    from excel_helpers import load_excel

    df = load_excel(file_name, nrows=3)
    mappings = {}
    for i_row, row in df.iterrows():
        # 1st row is rendered from delivery confirmation
        if i_row == 0:
            for col in df.columns:
                setting_value = row[col]
                if setting_value is not None and setting_value != "":
                    mappings[col] = FromDeliveryConfirmation(
                        target=col, column=setting_value
                    )
        # 2nd row is rendered hard-coded
        elif i_row == 1:
            for col in df.columns:
                setting_value = row[col]
                if setting_value is not None and setting_value != "":
                    mappings[col] = HardcodedColumn(target=col, value=setting_value)
        # 3rd row is rendered from original file
        elif i_row == 2:
            for col in df.columns:
                setting_value = row[col]
                if setting_value is not None and setting_value != "":
                    mappings[col] = FromOriginalOrderFile(
                        target=col, column=setting_value
                    )
    for col in df.columns:
        if col not in mappings:
            mappings[col] = FromOriginalOrderFile(target=col, column=col)

    return _PlatformDeliveryReportSetting(
        headers=pd.DataFrame(columns=df.columns),
        mappings=mappings,
        # TODO: Pass the name of the sheet to ``export_sheet_name``
    )


_delivery_report_registry = {
    'Naver': _PlatformDeliveryReportSetting(
        headers=pd.DataFrame(
            columns=['상품주문번호', '배송방법', '택배사', '송장번호', '이름', '주소']
        ),
        mappings={
            '상품주문번호': FromOriginalOrderFile(
                '상품주문번호', column='상품주문번호'
            ),
            '배송방법': HardcodedColumn('배송방법', value='택배'),
            '택배사': HardcodedColumn('택배사', value='롯데택배'),
            '송장번호': FromDeliveryConfirmation('송장번호', column='운송장번호'),
            '이름': FromOriginalOrderFile('이름', column='수취인명'),
            '주소': FromDeliveryConfirmation('주소', column='수하인기본주소'),
        },
        export_sheet_name="발송처리",
    ),
    'Gmarket': _PlatformDeliveryReportSetting(
        headers=pd.DataFrame(
            columns=['계정', '주문번호', '택배사', '송장번호', '수취인명'],
        ),
        mappings={
            '계정': FromOriginalOrderFile(target='계정', column='판매아이디'),
            '주문번호': FromOriginalOrderFile(target='주문번호', column='주문번호'),
            '택배사': HardcodedColumn('택배사', value='롯데택배'),
            '송장번호': FromDeliveryConfirmation('송장번호', column='운송장번호'),
            '수취인명': FromOriginalOrderFile('이름', column='수령인명'),
        },
    ),
    'Coupang': _load_excel_file_as_platform_report_setting(
        '_resources/_default_coupang_delivery_report_form.xlsx'
    ),
}
