{% if prerelease %}

# This is a Beta version!

---

{% endif %}

{% if installed and version_installed != selected_tag %}

# Changes as compared to your installed version:

{% if version_installed.replace(".","") | int < 4  %}

## Breaking Changes

{% if version_installed.replace(".","") | int < 4  %}

- Integration only works with Home Assistant 2021.8.0 and greater
  {% endif %}

{% if version_installed.replace(".","") | int < 4  %}

### Changes

{% if version_installed.replace(".","") | int < 4  %}

- Add support for Energy view
  {% endif %}

## Features

## Bugfixes

# Home Assistant Integration for IoTaWatt

This project provides [IoTaWatt](https://iotawatt.com/) support through a
custom integration for Home Assistant. It creates entites for each input and
output present in IoTaWatt.

The integration is available in HACS.
