import io
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from _templates import (
    delivery_left_over_table_template,
    delivery_split_row_template,
    delivery_split_table_template,
)
from excel_helpers import export_excel, load_excel
from js import URL, File, Uint8Array
from order_file_io import get_bytes_from_file, load_order_file
from order_settings import (
    PlatformHeaderVariableMap,
    find_matching_variable_map,
    load_order_variables_from_local_storage,
)
from pyscript import document, when, window
from split_delivery_settings import (
    _delivery_report_registry,
    load_delivery_info_keys_from_local_storage,
    DeliveryInfoKey,
)

_delivery_confirmation = {}

_DELIVERY_SPLIT_RESULT_CONTAINER_ID = "delivery-split-result-container"
_DELIVERY_SPLIT_RESULT_TABLE_ID = "delivery-split-result-table"


class DeliveryConfirmationFileSpec:
    _data_frame: pd.DataFrame
    _file_name: str

    @property
    def data_frame(self) -> pd.DataFrame:
        return self._data_frame

    @property
    def file_name(self) -> str:
        return self._file_name

    def __init__(self, file_name: str, df: pd.DataFrame) -> None:
        self._data_frame = df
        self._file_name = file_name


@dataclass
class ValidOrderFileSpec:
    file_name: str
    data_frame: pd.DataFrame
    variable_mapping: PlatformHeaderVariableMap


@dataclass
class DeliveryInfoUpdatedFileSpec:
    platform: str
    data_frame: pd.DataFrame
    export_sheet_name: str | None = None
    startrow: int = 0


def clear_delivery_result_container() -> None:
    container = document.getElementById(_DELIVERY_SPLIT_RESULT_CONTAINER_ID)
    window.console.log(f"Removing {len(container.children)} children")
    container.replaceChildren()


def collect_valid_orders() -> dict[str, ValidOrderFileSpec]:
    from order_file_io import _order_files

    variable_mappings = load_order_variables_from_local_storage()
    variable_maps = variable_mappings.platform_header_variable_maps
    # Filter encrypted files
    files = {}
    for file_name in _order_files:
        try:
            file_bytes = load_order_file(file_name)
            files[file_name] = file_bytes
        except KeyError:  # noqa: PERF203
            ...  # Skip the invalid password file.

    return {
        file_name: ValidOrderFileSpec(
            file_name=file_name,
            data_frame=load_excel(file_bytes, var_map.header),
            variable_mapping=var_map,
        )
        for file_name, file_bytes in files.items()
        if (var_map := find_matching_variable_map(file_bytes, variable_maps))
        is not None
    }


def _get_download_button_id(platform_name: str) -> str:
    return f"{platform_name}-delivery-split-result-download-button"


def _render_delivery_download_button(file_spec: ValidOrderFileSpec) -> str:
    button_id = _get_download_button_id(file_spec.variable_mapping.platform)
    return f'<button class="small-button" id="{button_id}">💾</button>'


def _make_split_file_name(file_spec: DeliveryInfoUpdatedFileSpec) -> str:
    today_as_str = pd.Timestamp.now().strftime("%Y-%m-%d")
    return f"{file_spec.platform}-delivered-{today_as_str}.xlsx"


def _generate_download_event_handler(
    file_spec: DeliveryInfoUpdatedFileSpec,
) -> Callable:
    def download_delivery_split(_):
        window.console.log("Downloading split files.")
        # Download the split file.
        bytes = io.BytesIO()
        export_excel(
            file_spec.data_frame,
            bytes,
            export_sheet_name=file_spec.export_sheet_name,
            startrow=file_spec.startrow,
        )
        bytes_buffer = bytes.getbuffer()
        js_array = Uint8Array.new(bytes_buffer.nbytes)
        js_array.assign(bytes_buffer)

        file_name = _make_split_file_name(file_spec)
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

    return download_delivery_split


@dataclass
class MatchedOrderDeliveryPair:
    platform: str
    original_order_row: pd.DataFrame | pd.Series
    delivery_confirmation_row: pd.DataFrame | pd.Series | None


@dataclass
class OrderDeliveryMatchingResults:
    matched: dict[str, list[MatchedOrderDeliveryPair]]
    cannot_be_matched: pd.DataFrame

    @property
    def file_specs(self) -> dict[str, DeliveryInfoUpdatedFileSpec]:
        file_specs = {}
        for platform, matched_pairs in self.matched.items():
            if (report_setting := _delivery_report_registry.get(platform)) is not None:
                if len(matched_pairs) > 0:
                    rendered = [
                        report_setting.render(
                            order_row=matched_pair.original_order_row,
                            delivery_row=matched_pair.delivery_confirmation_row,
                        )
                        for matched_pair in matched_pairs
                    ]
                    data_frame = pd.concat(rendered)
                else:  # If there is 0 orders.
                    data_frame = pd.DataFrame(
                        {col: [""] for col in report_setting.headers}
                    )  # Leave empty row so that headers are rendered.
                    # If it is completely empty, headers are not rendered in the file.

                file_specs[platform] = DeliveryInfoUpdatedFileSpec(
                    platform=platform,
                    data_frame=data_frame,
                    export_sheet_name=report_setting.export_sheet_name,
                    startrow=report_setting.startrow,
                )
            else:
                ...  # Skip if report setting is not found.
        return file_specs


@dataclass
class _DeliveryInfoKeyPlatformVer(DeliveryInfoKey):
    unified_variable_name: str
    """Unified variable name. i.e. receipients_name"""
    delivery_info_header: str
    """Header of the delivery information. i.e. 수하인명"""
    platform_header: str
    """Header of the platform specific name. i.e. 수령인명"""


def _match_orderrow_deliveryrow(
    order_row: pd.Series,
    delivery_row: pd.Series,
    matching_keys: tuple[_DeliveryInfoKeyPlatformVer, ...],
) -> bool:
    return all(
        order_row[key.platform_header] == delivery_row[key.delivery_info_header]
        or order_row[key.platform_header].strip()
        == delivery_row[key.delivery_info_header].strip()
        for key in matching_keys
    )


def _find_matching_delivery_confirmation(
    order_row: pd.DataFrame | pd.Series,
    delivery_confirmation_df: pd.DataFrame,
    matching_keys: tuple[_DeliveryInfoKeyPlatformVer, ...],
) -> pd.Series | None:
    matches = [
        delivery_row
        for _, delivery_row in delivery_confirmation_df.iterrows()
        if _match_orderrow_deliveryrow(
            order_row=order_row, delivery_row=delivery_row, matching_keys=matching_keys
        )
    ]
    # Only return unique match
    return next(iter(matches)) if len(matches) == 1 else None


def _delivery_info_key_registry_to_platform_header_ver() -> dict[
    str, tuple[_DeliveryInfoKeyPlatformVer, ...]
]:
    registry = load_delivery_info_keys_from_local_storage()
    unified_var_settings = load_order_variables_from_local_storage()
    var_mappings = unified_var_settings.platform_header_variable_maps
    return {
        var_mapping.platform: tuple(
            _DeliveryInfoKeyPlatformVer(
                unified_variable_name=key.unified_variable_name,
                delivery_info_header=key.delivery_info_header,
                platform_header=var_mapping.variable_mapping[key.unified_variable_name],
            )
            for key in registry.keys
        )
        for var_mapping in var_mappings
    }


def split_delivery_info_per_platform(
    orders: dict[str, ValidOrderFileSpec],
    delivery_confirmation: DeliveryConfirmationFileSpec,
) -> OrderDeliveryMatchingResults:
    #  Load matching settings.
    matching_keys = _delivery_info_key_registry_to_platform_header_ver()
    #  Initialize the result.
    matched: dict[str, list[MatchedOrderDeliveryPair]] = {
        file_spec.variable_mapping.platform: [] for file_spec in orders.values()
    }

    delivery_df = delivery_confirmation.data_frame.copy(deep=True)
    for order_file_spec in orders.values():
        platform = order_file_spec.variable_mapping.platform
        # Using platform from here since we do not have to keep file name
        # For example, if there are 2 files for Naver, we can simply merge them.
        for _, order_row in order_file_spec.data_frame.iterrows():
            # We handle ``platform not in _delivery_report_registry`` here
            # So that we skip the platform if there is no delivery report format.
            unique_match = _find_matching_delivery_confirmation(
                order_row, delivery_df, matching_keys[platform]
            )
            if (
                unique_match is not None and platform in _delivery_report_registry
            ):  # Matched!
                # Remove matched row so that only cannot-be-matched rows are left
                # And other rows can be matched faster
                delivery_df.drop(unique_match.name, axis=0, inplace=True)

            # Original order row should be appended no matter what
            # so that the cannot-be-matched part can be manually inserted.
            matched[platform].append(
                MatchedOrderDeliveryPair(
                    platform=platform,
                    original_order_row=order_row,
                    delivery_confirmation_row=unique_match
                    if platform in _delivery_report_registry
                    else None,
                )
            )

    return OrderDeliveryMatchingResults(matched=matched, cannot_be_matched=delivery_df)


def render_leftover_delivery_info(container, left_over_df: pd.DataFrame) -> None:
    table = document.createElement("div")
    table.innerHTML = delivery_left_over_table_template.render(
        headers=left_over_df.columns,
        rows=[
            [row[col] for col in left_over_df.columns]
            for _, row in left_over_df.iterrows()
        ],
    )
    container.appendChild(table)


def refresh_delivery_split_result() -> None:
    if not _delivery_confirmation:
        window.alert("배송내역 파일을 먼저 올려주세요.")
        return

    orders = collect_valid_orders()
    new_rows = [
        delivery_split_row_template.render(
            file_name=file_name,
            platform_name=file_spec.variable_mapping.platform,
            download_button=_render_delivery_download_button(file_spec),
        )
        for file_name, file_spec in orders.items()
        if file_spec.variable_mapping.platform in _delivery_report_registry
        # Skip the impossible one
    ]
    clear_delivery_result_container()
    table = document.createElement("table")
    table.id = _DELIVERY_SPLIT_RESULT_TABLE_ID
    table.innerHTML = delivery_split_table_template.render(file_items=new_rows)
    container = document.getElementById(_DELIVERY_SPLIT_RESULT_CONTAINER_ID)
    container.appendChild(table)

    matching_results = split_delivery_info_per_platform(
        orders=orders, delivery_confirmation=_delivery_confirmation["latest"]
    )
    if len(matching_results.cannot_be_matched) > 0:
        window.alert(
            f"총 {len(matching_results.cannot_be_matched)}개의 운송장 정보를 입력할 수 없었습니다: \n"
            + ",".join(matching_results.cannot_be_matched["운송장번호"])
        )

    # Add event listener to the download button
    for platform, file_spec in matching_results.file_specs.items():
        if platform in _delivery_report_registry:  # If possible
            # TODO: Improve this logic to only include possible ones.
            button = document.getElementById(_get_download_button_id(platform))
            when("click", button)(_generate_download_event_handler(file_spec))

    # Render left over ones if needed
    render_leftover_delivery_info(container, matching_results.cannot_be_matched)


async def save_delivery_confirmation_file(file_obj) -> None:
    new_delivery_confirmation = load_excel(await get_bytes_from_file(file_obj))
    _delivery_confirmation.update(
        {
            "latest": DeliveryConfirmationFileSpec(
                file_name=file_obj.name, df=new_delivery_confirmation
            )
        }
    )
    file_name_display = document.getElementById("delivery_confirmation_file_name")
    file_name_display.textContent = f"최근 업로드 된 파일: {file_obj.name}"


async def upload_delivery_confirmation(e):
    file_list = e.target.files
    try:
        new_file = next(iter(file_list))
    except StopIteration:
        window.console.log("No file selected.")
        return
    else:
        window.console.log("Delivery confirmation uploaded: " + new_file.name)

    try:
        await save_delivery_confirmation_file(new_file)
    except Exception as e:
        window.alert("배송 파일 업로드에 실패했습니다.")
    else:
        refresh_delivery_split_result()
