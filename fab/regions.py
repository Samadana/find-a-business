"""Rattachement de chaque article à une grande région du monde, pour équilibrer la sélection."""

from __future__ import annotations

REGIONS = ["europe", "amerique-nord", "amerique-latine", "afrique", "moyen-orient", "asie", "oceanie", "monde", "business"]

_ISO = {
    "europe": "FR BE CH LU DE AT ES PT IT NL PL SE NO DK FI IE GB UK UA RU RO GR CZ HU BG HR RS SK SI LT LV EE BY MD",
    "amerique-nord": "US CA",
    "amerique-latine": "MX BR AR CO CL PE VE EC BO UY PY CU DO GT HN SV NI CR PA PR",
    "afrique": "NG ZA KE GH SN CI CM MA DZ TN ET UG TZ RW CD AO ZW ZM MZ ML BF NE BJ TG MG SD",
    "moyen-orient": "EG SA AE IL TR IR IQ JO LB QA KW OM BH SY YE PS",
    "asie": "IN CN JP KR TW HK SG MY ID TH VN PH PK BD LK NP MM KH LA KZ UZ MN",
    "oceanie": "AU NZ FJ PG",
}
ISO_REGION = {code: region for region, codes in _ISO.items() for code in codes.split()}

# Pays au format GDELT (nom anglais) les plus fréquents.
_NAMES = {
    "europe": "France Belgium Switzerland Luxembourg Germany Austria Spain Portugal Italy Netherlands Poland Sweden Norway "
              "Denmark Finland Ireland United Kingdom Ukraine Russia Romania Greece Czech Republic Hungary Bulgaria Croatia Serbia",
    "amerique-nord": "United States Canada",
    "amerique-latine": "Mexico Brazil Argentina Colombia Chile Peru Venezuela Ecuador Bolivia Uruguay Paraguay Cuba",
    "afrique": "Nigeria South Africa Kenya Ghana Senegal Ivory Coast Cameroon Morocco Algeria Tunisia Ethiopia Uganda Tanzania "
               "Rwanda Zimbabwe Zambia Mozambique Mali Madagascar Sudan",
    "moyen-orient": "Egypt Saudi Arabia United Arab Emirates Israel Turkey Iran Iraq Jordan Lebanon Qatar Kuwait Oman Bahrain Syria Yemen",
    "asie": "India China Japan South Korea Taiwan Hong Kong Singapore Malaysia Indonesia Thailand Vietnam Philippines Pakistan "
            "Bangladesh Sri Lanka Nepal Myanmar Cambodia Kazakhstan",
    "oceanie": "Australia New Zealand",
}
NAME_REGION: dict[str, str] = {}
for _region, _names in _NAMES.items():
    for _multi in ("United Kingdom", "Czech Republic", "South Africa", "Ivory Coast", "Saudi Arabia", "United Arab Emirates",
                   "South Korea", "Hong Kong", "Sri Lanka", "New Zealand", "United States"):
        if _multi in _names:
            NAME_REGION[_multi.lower()] = _region
            _names = _names.replace(_multi, "")
    for _n in _names.split():
        NAME_REGION[_n.lower()] = _region

LANG_REGION = {
    "fr": "europe", "de": "europe", "it": "europe", "nl": "europe", "pl": "europe", "sv": "europe", "uk": "europe", "ru": "europe",
    "pt-br": "amerique-latine", "es-419": "amerique-latine",
    "ar": "moyen-orient", "he": "moyen-orient", "tr": "moyen-orient", "fa": "moyen-orient",
    "arabic": "moyen-orient", "turkish": "moyen-orient", "persian": "moyen-orient", "hebrew": "moyen-orient",
    "hi": "asie", "ja": "asie", "ko": "asie", "zh": "asie", "id": "asie", "vi": "asie", "th": "asie",
    "hindi": "asie", "japanese": "asie", "korean": "asie", "chinese": "asie", "indonesian": "asie", "vietnamese": "asie", "thai": "asie",
    "sw": "afrique", "ha": "afrique", "swahili": "afrique", "hausa": "afrique",
    "portuguese": "amerique-latine", "spanish": "amerique-latine",
}


def region_of(country: str = "", lang: str = "", explicit: str = "") -> str:
    """Région d'un article : celle de sa source si elle est connue, sinon d'après son pays, sinon sa langue."""
    if explicit:
        return explicit
    c = (country or "").strip()
    if c:
        if c.upper() in ISO_REGION:
            return ISO_REGION[c.upper()]
        if c.lower() in NAME_REGION:
            return NAME_REGION[c.lower()]
    lang = (lang or "").lower()
    return LANG_REGION.get(lang) or LANG_REGION.get(lang.split("-")[0]) or "monde"
