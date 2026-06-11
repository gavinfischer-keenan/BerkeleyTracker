"""Static MMSI lookup — derive flag and type from Maritime Identification Digits.

MMSI format (9 digits):
  - MIDxxxxxx  → Ship station (MID = 3-digit country code)
  - 0MIDxxxxx  → Group of ships
  - 00MIDxxxx  → Coast station
  - 111MIDxxx  → SAR aircraft
  - 98MIDxxxx  → Craft associated with parent ship
  - 970xxyyyy  → AIS SART (Search and Rescue Transmitter)
  - 972xxxxxx  → MOB (Man Overboard)
  - 974xxxxxx  → EPIRB AIS

Reference: ITU-R M.585, https://www.itu.int/en/ITU-R/terrestrial/fmd/Pages/mid.aspx
"""
from __future__ import annotations

# Maritime Identification Digits → Country
# Source: ITU MID database (common entries for SF Bay area traffic)
MID_TABLE: dict[str, str] = {
    # North America
    "303": "US", "338": "US", "366": "US", "367": "US", "368": "US", "369": "US",
    "316": "CA",  # Canada
    "345": "MX",  # Mexico

    # Central America & Caribbean
    "304": "AG", "305": "AG",  # Antigua
    "309": "BS",  # Bahamas
    "311": "BM",  # Bermuda
    "312": "BZ",  # Belize
    "314": "BB",  # Barbados
    "319": "KY",  # Cayman Islands
    "325": "JM",  # Jamaica
    "341": "KN",  # St. Kitts
    "351": "PA",  # Panama (extremely common — flag of convenience)

    # Europe
    "201": "AL", "202": "AD", "203": "AT", "205": "BE",
    "209": "CY", "210": "CY", "211": "DE", "212": "CY",
    "214": "DE", "215": "MT", "218": "DE",
    "219": "DK", "220": "DK",
    "224": "ES", "225": "ES", "226": "FR", "227": "FR", "228": "FR",
    "229": "MT",  # Malta (flag of convenience)
    "230": "FI", "231": "FO",
    "232": "GB", "233": "GB", "234": "GB", "235": "GB",
    "236": "GI", "237": "GR", "238": "HR", "239": "GR",
    "240": "GR", "241": "GR", "242": "MA",
    "244": "NL", "245": "NL", "246": "NL",
    "247": "IT", "248": "MT", "249": "MT",
    "250": "IE", "251": "IS",
    "255": "PT", "256": "MT",
    "257": "NO", "258": "NO", "259": "NO",
    "261": "PL", "263": "PT",
    "265": "SE", "266": "SE",

    # Asia
    "401": "AF", "403": "SA",
    "412": "CN", "413": "CN", "414": "CN",
    "416": "TW",
    "417": "LK",
    "419": "IN",
    "422": "IR",
    "431": "JP", "432": "JP",
    "440": "KR", "441": "KR",
    "447": "KW",

    # Oceania
    "503": "AU",
    "512": "NZ",

    # Africa
    "601": "ZA",
    "603": "AO",

    # Flags of convenience (very common in shipping)
    "354": "PA", "355": "PA", "356": "PA", "357": "PA",
    "370": "PA", "371": "PA", "372": "PA", "373": "PA",
    "374": "PA", "375": "PA", "376": "PA", "377": "PA",
}


def mmsi_to_flag(mmsi: str) -> str | None:
    """Derive flag country from MMSI Maritime Identification Digits."""
    if not mmsi or len(mmsi) < 9:
        return None

    # Standard ship station: first 3 digits are MID
    mid3 = mmsi[:3]
    if mid3 in MID_TABLE:
        return MID_TABLE[mid3]

    return None


def mmsi_to_type_hint(mmsi: str) -> str | None:
    """Derive station type from MMSI prefix pattern."""
    if not mmsi or len(mmsi) < 9:
        return None

    if mmsi.startswith("00"):
        return "coast_station"
    elif mmsi.startswith("0") and not mmsi.startswith("00"):
        return "ship_group"
    elif mmsi.startswith("111"):
        return "sar_aircraft"
    elif mmsi.startswith("98"):
        return "auxiliary_craft"
    elif mmsi.startswith("970"):
        return "ais_sart"
    elif mmsi.startswith("972"):
        return "mob_device"
    elif mmsi.startswith("974"):
        return "epirb"

    return "ship_station"
