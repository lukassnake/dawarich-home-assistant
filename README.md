# Dawarich Home Assistant Integration

A custom version of the Dawarich integration for Home Assistant, based on the original project by [AlbinLind](https://github.com/AlbinLind/dawarich-home-assistant).

This fork includes personal enhancements and additional filtering logic designed to improve GPS tracking efficiency, particularly when using the Home Assistant Companion App on Samsung Galaxy devices.

## Features

- Integration with [Dawarich](https://github.com/Freika/dawarich).
- GPS location tracking through Home Assistant.
- Custom location filtering to reduce unnecessary GPS updates.
- Zone-aware tracking logic for Home and Work locations.
- Support for Home Assistant Companion App High Accuracy mode.
- Dynamic High Accuracy update interval based on Bluetooth connections.

## Custom Enhancements

### Zone-aware location filtering

The integration uses different filtering behavior depending on the tracked device's location:

- **Home and Work:** Sends all location points during the first 5 minutes after entering a zone, then reduces updates to approximately once per hour.
- **Outside configured zones:** Uses stop-based filtering to avoid sending unnecessary GPS updates caused by short movements or GPS fluctuations.

### Dynamic High Accuracy interval

The integration can dynamically adjust the Home Assistant Companion App High Accuracy update interval based on connected Bluetooth devices.

Bluetooth connection status is determined using the connected devices reported by the Home Assistant Companion App.

## Requirements

- Home Assistant
- Dawarich server
- Home Assistant Companion App
- A configured device tracker

## Installation via HACS

1. Open HACS in Home Assistant.
2. Open the three-dot menu and select **Custom repositories**.
3. Add this repository:

   `https://github.com/lukassnake/dawarich-home-assistant`

4. Select **Integration** as the category.
5. Find and install **Dawarich**.
6. Restart Home Assistant if required.

## Configuration

Follow the integration configuration flow in Home Assistant.

Additional options and behavior depend on the installed integration version.

## Credits

This project is based on the original integration:

- [AlbinLind/dawarich-home-assistant](https://github.com/AlbinLind/dawarich-home-assistant)
- [Freika/dawarich](https://github.com/Freika/dawarich)

All custom modifications in this fork are maintained independently.

## Disclaimer

This is a personal fork and is not officially affiliated with or maintained by the original project authors.

Use at your own risk. Always keep backups of your Home Assistant configuration before upgrading.
