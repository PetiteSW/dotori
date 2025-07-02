import io

import msoffcrypto
import pandas as pd
import xlrd
from _templates import file_item_row_template, file_list_table_template
from order_settings import (
    find_matching_variable_map,
    load_order_variables_from_local_storage,
    PlatformHeaderVariableMap,
)
from excel_helpers import load_excel
from pyscript import document, when, window

# We are using ``when`` instead of ``create_proxy`` so that we don't have to handle
# garbagae collections of proxies.
# See https://docs.pyscript.net/2024.10.1/user-guide/ffi/#create_proxy for details.

_order_files = {}  # Dictionary that carries uploaded files as bytes.
# Reasons why files are stored as bytes here.
# - Files carry personal information hence should not be saved in local storage
#   or indexeddb or session storage.
# - In-memory is also not the most secure way but it is not so much less secure than
#   having the files in the file-system, which is inevitable for users.
# - Virtual file system could also be an option but it is also just in-memory anyways.
#   Dictionary is easier to use than the virtual file system and easier to clear.
# Important aspects of using dictionary to carry files.
# - The keys are name of the files so when a new file with a same name comes, it will
#   overwrite the existing one, but that is what we want.
#   TODO: Alert the user when this happens.


def clear_order_table_container() -> None:
    container = document.getElementById("order-file-list-table-container")
    for child in container.children:
        container.removeChild(child)


def initialize_order_list_table():
    clear_order_table_container()
    table = document.createElement('table')
    table.id = "order-file-list-table"
    table.innerHTML = file_list_table_template.render(
        file_items=[
            file_item_row_template.render()  # Empty row
        ]
    )
    container = document.getElementById("order-file-list-table-container")
    container.appendChild(table)


async def get_bytes_from_file(file):
    array_buf = await file.arrayBuffer()
    return io.BytesIO(array_buf.to_bytes())


def _make_row_id(file_name: str) -> str:
    return f"order-{file_name}-row"


def _make_button_id(file_name: str) -> str:
    return f"order-{file_name}-delete-button"


def _make_delete_button(file_name: str) -> str:
    button_id = _make_button_id(file_name)
    button_tag = (
        '<div class="little-button-box"><button type="button" class="delete-button" '
        + f'id="{button_id}" value="{file_name}">'
    )
    trash_icon = '<img src="trash_icon.png" alt="🗑️" height=1em>'
    return f'{button_tag}{trash_icon}</button></div>'


def delete_file(e) -> None:
    _file_name = e.currentTarget.value
    window.console.log(f"Deleting the order file: {_file_name}")
    row = document.getElementById(_make_row_id(_file_name))
    row.remove()
    _order_files.pop(_file_name, None)
    left_files = '\n'.join(_order_files.keys())
    window.console.log(f"Left order files: \n{left_files}")


def _is_file_encrypted(file_name: str) -> bool:
    file_bytes = _order_files.get(file_name, None)
    if file_bytes is None:
        window.console.log(f"{file_name} not found to check if it is encrypted.")
        return False
    try:
        load_excel(file_bytes, nrows=1)  # Just first row to see if it succeeds.
        return False
    except xlrd.biffh.XLRDError:
        return True


def _make_password_id(file_name: str) -> str:
    return f"{file_name}-password"


def _make_password_input(file_name: str) -> str:
    return f"<input type='password' id='{_make_password_id(file_name)}' value='1111'>"


ORDER_FILE_VALIDITY_CLASS_MAP = {
    True: "valid-order-file",
    False: "invalid-order-file",
    None: "uncertain-order-file",
}


def _get_order_numbers(
    file_bytes: io.BytesIO, variable_map: PlatformHeaderVariableMap | None
) -> str:
    if variable_map is None:
        return ""
    else:
        return str(len(load_excel(file_bytes, header_row=variable_map.header)))


def get_file_item_row(file_name: str) -> str:
    variable_mappings = load_order_variables_from_local_storage()
    if encrypted := _is_file_encrypted(file_name):
        validity = None
        num_orders = '?'
        platform_name = '?'
    else:
        variable_map = find_matching_variable_map(
            _order_files[file_name], variable_mappings.platform_header_variable_maps
        )
        validity = variable_map is not None
        num_orders = _get_order_numbers(_order_files[file_name], variable_map)
        platform_name = variable_map.platform if variable_map is not None else ''
    return file_item_row_template.render(
        validity_class=ORDER_FILE_VALIDITY_CLASS_MAP[validity],
        file_name=file_name,
        platform_name=platform_name,
        num_orders=num_orders,
        delete_button=_make_delete_button(file_name),
        encrypted="Y" if encrypted else "N",
        password_input="-" if not encrypted else _make_password_input(file_name),
    )


def refresh_table_from_order_files() -> None:
    new_rows = [get_file_item_row(file_name) for file_name in _order_files]
    clear_order_table_container()
    table = document.createElement('table')
    table.id = "order-file-list-table"
    table.innerHTML = file_list_table_template.render(file_items=new_rows)
    container = document.getElementById("order-file-list-table-container")
    container.appendChild(table)
    # Add event listener to the delete button
    for file_name in _order_files:
        button = document.getElementById(_make_button_id(file_name))
        when("click", button)(delete_file)


async def upload_order_file(e):
    file_list = e.target.files
    names = [f.name for f in file_list]
    window.console.log("Files uploaded: " + ','.join(names))
    _order_files.update({f.name: await get_bytes_from_file(f) for f in file_list})
    refresh_table_from_order_files()


def _decrypt_bytes(file_name: str) -> io.BytesIO:
    """Decrypt the bytes by the password.
    Returns ``None`` if password is not valid.
    """
    password_input = document.getElementById(_make_password_id(file_name))
    file = msoffcrypto.OfficeFile(_order_files[file_name])
    try:
        file.load_key(password=password_input.value or "")
        decrypted = io.BytesIO()
        file.decrypt(decrypted)
        return decrypted
    except Exception as e:
        window.alert(f"{file_name} 비밀번호를 다시 한 번 확인해주세요.")
        raise KeyError(f"Password for {file_name} is not valid.") from e


def load_order_file(file_name: str) -> io.BytesIO:
    """Load the bytes from the file and decrypt it if necessary."""
    if _is_file_encrypted(file_name):
        return _decrypt_bytes(file_name)
    else:
        return _order_files[file_name]
