#pragma once

// ── Select active board ────────────────────────────────────────────────────
#define BOARD_LILYGO_A7670G_S3_STANDARD
// #define BOARD_WAVESHARE_A7670E_S3

// ── LILYGO T-A7670G-S3-Standard ───────────────────────────────────────────
// Source: github.com/Xinyuan-LilyGO/LilyGO-T-A76XX utilities.h (LILYGO_A7670X_S3_STAN)
#ifdef BOARD_LILYGO_A7670G_S3_STANDARD

  #define MODEM_BAUD         115200
  #define MODEM_TX               4   // ESP32-S3 → A7670G
  #define MODEM_RX               5   // A7670G → ESP32-S3
  #define MODEM_DTR              7
  #define MODEM_RING             6
  #define MODEM_PWRKEY          46
  #define MODEM_POWER_SAVE      42
  #define MODEM_RST             -1   // not broken out on Standard variant

  // GPS is on a separate UART — read raw NMEA, no AT commands needed
  #define GPS_RX                48
  #define GPS_TX                45
  #define GPS_PPS               17
  #define GPS_ENABLE             1   // drive HIGH to power GPS

  #define BOARD_BAT_ADC          8
  #define BOARD_SOLAR_ADC       18
  #define BOARD_SDA              3
  #define BOARD_SCL              2
  #define BOARD_SD_MISO         13
  #define BOARD_SD_MOSI         11
  #define BOARD_SD_SCK          12
  #define BOARD_SD_CS           10

  #define TINY_GSM_MODEM_A7670

#endif

// ── WVS ESP32-S3-A7670E (Communica) ───────────────────────────────────────
#ifdef BOARD_WAVESHARE_A7670E_S3

  #define MODEM_BAUD         115200
  #define MODEM_TX              17
  #define MODEM_RX              18
  #define MODEM_DTR             -1
  #define MODEM_RING            -1
  #define MODEM_PWRKEY           5
  #define MODEM_RST             -1
  #define MODEM_POWER_SAVE      -1

  // GPS via AT commands on same modem UART (no separate GPS UART)
  #define GPS_RX                -1
  #define GPS_TX                -1
  #define GPS_PPS               -1
  #define GPS_ENABLE            -1

  #define BOARD_BAT_ADC         -1
  #define BOARD_SOLAR_ADC       -1
  #define BOARD_SDA              1
  #define BOARD_SCL              2
  #define BOARD_SD_MISO         47
  #define BOARD_SD_MOSI         14
  #define BOARD_SD_SCK          21
  #define BOARD_SD_CS           13

  #define TINY_GSM_MODEM_A7670

#endif
