FAMILIES: dict[str, str] = {}


def get_family(material: str) -> str:
    return FAMILIES.get(material, material)
