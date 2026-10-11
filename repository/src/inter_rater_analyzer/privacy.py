"""Fail-closed checks of public report text, document archives and image metadata."""

import json
import re
from importlib import import_module
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile


def check_text(text: str, identities: tuple[str, ...]) -> None:
    public = text.casefold()
    for identity in identities:
        value = identity.strip().casefold()
        if value and re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", public):
            raise ValueError("A public output contains a protected rater identity.")


def check_artifact(name: str, payload: bytes, identities: tuple[str, ...], depth: int = 0) -> None:
    check_text(name, identities)
    if depth > 4:
        raise ValueError("Unexpected nested report archive")
    extension = PurePosixPath(name).suffix.casefold()
    if extension in (".zip", ".docx"):
        with ZipFile(BytesIO(payload)) as archive:
            for member in archive.namelist():
                check_artifact(member, archive.read(member), identities, depth + 1)
    elif extension == ".pdf":
        reader = import_module("pypdf").PdfReader(BytesIO(payload))
        check_text(str(reader.metadata), identities)
        for page in reader.pages:
            check_text(page.extract_text(), identities)
    elif extension == ".png":
        with import_module("PIL.Image").open(BytesIO(payload)) as image:
            check_text(json.dumps(image.info, default=str), identities)
    elif extension == ".xml":
        check_text(payload.decode("utf-8", errors="replace"), identities)
        check_text("".join(ElementTree.fromstring(payload).itertext()), identities)
    else:
        check_text(payload.decode("utf-8", errors="replace"), identities)
