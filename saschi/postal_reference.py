"""Pinned finite USPS reference policy; all reference bodies remain external."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request,urlopen
from xml.etree import ElementTree as XML
from zipfile import ZipFile
import io

POLICY='usps-zip-locale-20261001-bounded19-v1'
URL='https://postalpro.usps.com/mnt/glusterfs/2026-10/Zip_Locale_Detail.xlsx'
SOURCE_PAGE='https://postalpro.usps.com/ZIP_Locale_Detail'
RAW_BYTES=4380487
RAW_SHA256='6e923786b70a5ab7ed93fd89cf0ffee3633c6daa58c86c6d4c8702dcd860bc07'
MAP_SHA256='47dd0c9d0afcd3eabdc35bddf56f8d496d0017814d50ff9fe77dc6545bb89f2e'
DOMAIN=('01040','19119','19139','19140','19142','19145','27511','33031','33133','33135','33141','33157','33161','33177','90049','91950','92025','92071','92116')
ROOT=Path(__file__).resolve().parents[1]
NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def metadata():
    return {'policy':POLICY,'source_url':URL,'source_page':SOURCE_PAGE,'raw_bytes':RAW_BYTES,'raw_sha256':RAW_SHA256,'mapping_sha256':MAP_SHA256,'n_codes':len(DOMAIN),'evidence':'Bounded pinned USPS reference policy; not live SAS zone-table equivalence or general postal validation.'}


def reference_path(cache=None):
    root=Path(cache if cache is not None else os.environ.get('SASCHI_POSTAL_CACHE',str(Path(tempfile.gettempdir())/'saschi-postal-cache'/'2026-10-01'))).absolute()
    path=root/'Zip_Locale_Detail.xlsx'
    if path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('postal reference data must stay outside Go')
    for item in (path,*path.parents):
        if item.is_symlink():raise ValueError('postal reference path cannot follow symlinks')
        if item==Path(tempfile.gettempdir()).resolve():break
        if (item/'.git').exists():raise ValueError('postal reference data must stay outside Git checkouts')
    return path


def _raw_pin(raw):
    if type(raw) is not bytes or len(raw)!=RAW_BYTES or hashlib.sha256(raw).hexdigest()!=RAW_SHA256:raise ValueError('postal reference bytes differ from the pinned USPS workbook')


def _semantic_pin(mapping):
    if (type(mapping) is not dict or set(mapping)!=set(DOMAIN)
            or any(type(v) is not str or re.fullmatch('[A-Z]{2}',v,re.ASCII) is None for v in mapping.values())
            or hashlib.sha256((json.dumps(mapping,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')).hexdigest()!=MAP_SHA256):raise ValueError('postal reference mapping differs from the qualified finite-domain pin')
    return mapping


@lru_cache(maxsize=1)
def _decode(raw):
    _raw_pin(raw)
    with ZipFile(io.BytesIO(raw)) as archive:
        strings=XML.fromstring(archive.read('xl/sharedStrings.xml'))
        shared=[''.join(node.itertext()) for node in strings.findall('x:si',NS)]
        observations={code:set() for code in DOMAIN}
        def value(cell):
            node=cell.find('x:v',NS)
            if node is None:return ''
            return shared[int(node.text)] if cell.get('t')=='s' else node.text
        for sheet in ('sheet1','sheet2','sheet3'):
            root=XML.fromstring(archive.read('xl/worksheets/'+sheet+'.xml'))
            for row in root.findall('x:sheetData/x:row',NS):
                cells={re.sub('[0-9]','',cell.get('r','')):cell for cell in row.findall('x:c',NS)}
                if 'D' not in cells:continue
                code=value(cells['D'])
                if re.fullmatch('[0-9]{1,5}',code,re.ASCII):code=code.zfill(5)
                if code in observations:
                    if 'K' not in cells:raise ValueError('postal reference state field is absent')
                    observations[code].add(value(cells['K']))
        if any(len(states)!=1 for states in observations.values()):raise ValueError('postal reference requires consistent state for every approved delivery ZIP')
        return _semantic_pin({code:next(iter(states)) for code,states in observations.items()})


def load_reference(cache=None):
    path=reference_path(cache)
    try:
        with path.open('rb') as stream:raw=stream.read(RAW_BYTES+1)
    except OSError as error:raise ValueError('pinned external postal reference is missing; run python tools/prepare_postal_reference.py') from error
    _raw_pin(raw)
    return dict(_decode(raw))


def zip_state(code,mapping):
    if type(code) is not str or re.fullmatch('[0-9]{5}',code,re.ASCII) is None or code not in DOMAIN or code not in mapping:raise ValueError('ZIPSTATE requires an approved five-digit character ZIP; unverified ZIPs refuse')
    return mapping[code]


def prepare(cache=None,*,fetch=None):
    path=reference_path(cache)
    if path.exists():load_reference(cache);return path
    if fetch is None:
        def fetch(url):
            with urlopen(Request(url,headers={'User-Agent':'SASchi-Go-pinned-reference-preparation/1.0'}),timeout=45) as response:
                if response.status!=200:raise ValueError('postal reference download did not return200')
                return response.read(RAW_BYTES+1)
    raw=fetch(URL);_raw_pin(raw);_decode(raw);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)
    load_reference(cache);return path
