# DOTORI TOOLS
Basic static web applications for dotori company

## Developer's Guide.
### Architecture Decision Records 📝
See [ADR Document](ADRs.md) if you have any question on the over-all architecture.

Also, please add ADR in the [ADR Document](ADRs.md) if needed.

### Release

I didn't have any resources to automate the UI tests for now so instead
I have been doing this check manually before releasing.

**This list will be turned into automatic tests later.**

#### Functionality check-list before releases.
- [ ] Order file upload.
    - [ ] When a new order file is uploaded, it should check if it can be merged or not.

- [ ] Order variable settings.
    - [ ] ``tests/order-variable-settings/missing_*.xlsx`` files should alert about
        the wrong configuration and abort the uploading.
        **These files should be warned about missing headers.**
    - [ ] ``tests/order-variable-settings/wrong_*.xlsx`` files should alert about
        the wrong configuration and abort the uploading.
        **These files should be warned about wrong dtype of mandatory columns**
    - [ ] ``tests/wrong_column_name.xlsx`` file should alert an error and abort the uploading.
        **This file should warn about the wrong pattern of the column name**
    - [ ] ``tests/order-variable-settings/additional*.xlsx`` files should change    the settings accordingly.
        - [ ] Preview should be updated
        - [ ] ``현재 설정파일 내려받기`` file is same as the latest one uploaded.
    - [ ] ``초기화`` button should return the settings to the default
        - [ ] Preview should be updated
        - [ ] ``현재 설정파일 내려받기`` file is same as the default file.

- [ ] Header unification(translation)
    - [ ] When the page is loaded/refreshed, it should show the preview
          of the merged files. **Only the first rows of each file**
    - [ ] When user upload a new order-file, it should show in the preview.

- [ ] Delivery Formatting
    - [ ] When ``tests/delivery-format-settings/missing-delivery-agency.xlsx`` is
          registered as a new delivery format, it should show an error and abort.

- [ ] Delivery Splitting
    - [ ] The excel sheet's sheet name and headers settings should be saved in the local storage.
