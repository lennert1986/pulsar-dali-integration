# Pulsar DALI for Home Assistant

Custom Home Assistant integration for the **Pulsar DALI Control** App.

It exposes Pulsar DALI control gear and DALI-2 devices as native Home Assistant entities, including lights, switches, groups, scenes, PIR sensors, light sensors and button events.

## Install from Home Assistant Marketplace

1. Open **Settings → Marketplace**.
2. Select **Add from link**.
3. Enter:

   `https://github.com/lennert1986/pulsar-dali-integration`

4. Install **Pulsar DALI**.
5. Add the integration under **Settings → Devices & services**.

The integration supports both:

- a local Pulsar DALI App on the same Home Assistant instance
- a secured remote Pulsar DALI server using HTTPS, bearer token and certificate fingerprint pinning

## Requirements

- Home Assistant 2026.11 or newer
- Pulsar DALI Control App v0.12.0 or newer recommended

## Hardware

The hardware access is handled by the Pulsar DALI App. This integration does not access UART or GPIO directly.
