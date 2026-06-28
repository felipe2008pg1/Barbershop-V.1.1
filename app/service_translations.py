"""
Service name translations.

Service names are stored in the database in Portuguese (the language
the shop owner uses when registering them via the admin panel). This
module provides English translations for known service names, so the
public-facing API can return a translated name when the client
requests the English locale — without requiring the admin to maintain
two separate names per service in the database.

If a service name isn't found in the dictionary (e.g. a new, custom
service the shop owner just added), the original Portuguese name is
returned unchanged as a safe fallback, rather than showing nothing or
raising an error.
"""

# Maps exact Portuguese service names (case-insensitive) to their
# English translation. Extend this dictionary as new common service
# names come up.
_PT_TO_EN = {
    "corte de cabelo": "Haircut",
    "corte": "Haircut",
    "barba": "Beard trim",
    "corte + barba": "Haircut + Beard trim",
    "corte e barba": "Haircut + Beard trim",
    "sobrancelha": "Eyebrow grooming",
    "hidratação": "Hair treatment",
    "hidratacao": "Hair treatment",
    "pigmentação": "Beard pigmentation",
    "pigmentacao": "Beard pigmentation",
    "platinado": "Bleaching",
    "luzes": "Highlights",
    "alisamento": "Hair straightening",
    "relaxamento": "Hair relaxing",
    "coloração": "Hair coloring",
    "coloracao": "Hair coloring",
    "design de barba": "Beard design",
    "navalha": "Razor shave",
    "barboterapia": "Beard spa treatment",
}


def translate_service_name(name: str, lang: str) -> str:
    """
    Translates a service name to the requested language.

    Args:
        name: the service name as stored in the database (Portuguese).
        lang: the requested language code, "pt" or "en".

    Returns:
        The translated name if a translation is known and lang == "en";
        otherwise, the original name unchanged.
    """
    if lang != "en" or not name:
        return name

    translated = _PT_TO_EN.get(name.strip().lower())
    return translated if translated else name
