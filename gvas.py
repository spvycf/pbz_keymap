"""GVAS 存档最小解析/序列化器。

仅面向本项目的 PBZInputUserSettings.sav 结构：
- UE5 GVAS 头 + PBZInputUserSettings 属性流 + 尾部 EnhancedInput 对象
- 属性标签布局与标准 FPropertyTag 略有差异（Size 在路径字段之后、数组值带元素计数）

所有数值与字符串都保留原始字节，序列化时按原布局重建并重算 Size，
因此对未修改的输入可以做到字节级完全一致。
"""

import struct
from dataclasses import dataclass, field
from typing import Optional, List

MAGIC = b"GVAS"
CLASS_PATH = b"/Script/ProjectPBZ.PBZInputUserSettings"

SCALAR_TYPES = {
    "IntProperty",
    "Int8Property",
    "Int16Property",
    "Int64Property",
    "UInt16Property",
    "UInt32Property",
    "UInt64Property",
    "FloatProperty",
    "DoubleProperty",
    "StrProperty",
    "NameProperty",
    "BoolProperty",
    "TextProperty",
    "ObjectProperty",
    "ClassProperty",
    "SoftObjectProperty",
    "InterfaceProperty",
}
KNOWN_TYPES = SCALAR_TYPES | {"StructProperty", "ArrayProperty", "EnumProperty", "ByteProperty", "MapProperty", "SetProperty"}


class FormatError(Exception):
    """文件结构与预期不符时抛出。"""


def _i32(v: int) -> bytes:
    return struct.pack("<i", v)


class Reader:
    def __init__(self, data: bytes, offset: int = 0):
        self.d = data
        self.o = offset

    def take(self, n: int) -> bytes:
        if n < 0 or self.o + n > len(self.d):
            raise FormatError(f"读取越界：offset={hex(self.o)} n={n} file={hex(len(self.d))}")
        b = self.d[self.o:self.o + n]
        self.o += n
        return b

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def u8(self) -> int:
        return self.take(1)[0]

    def fstr(self) -> str:
        n = self.i32()
        if n == 0:
            return ""
        if n < 0:
            n = -n
            raw = self.take(2 * n)
            return raw.decode("utf-16-le", "replace").rstrip("\x00")
        raw = self.take(n)
        return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")


@dataclass
class Tag:
    name: str
    type: str
    A: int = 0
    struct: Optional[str] = None
    B: Optional[int] = None
    struct_path: Optional[str] = None
    C: Optional[int] = None
    inner: Optional[str] = None
    D: Optional[int] = None
    inner_struct: Optional[str] = None
    inner_struct_path: Optional[str] = None
    enum: Optional[str] = None
    enum_path: Optional[str] = None
    has_guid: int = 0
    guid: Optional[bytes] = None
    value: bytes = b""
    children: List["Tag"] = field(default_factory=list)
    elements: List[List["Tag"]] = field(default_factory=list)
    count: int = 0
    enum_value: Optional["Tag"] = None


def _read_guid(r: Reader, t: Tag) -> None:
    t.has_guid = r.u8()
    if t.has_guid:
        t.guid = r.take(16)


def parse_tag(r: Reader):
    name = r.fstr()
    if name in ("None", "ObjectEnd"):
        return None
    typ = r.fstr()
    if typ not in KNOWN_TYPES:
        raise FormatError(f"未知属性类型 {typ!r}（属性 {name!r}，offset={hex(r.o)}）")
    A = r.i32()
    t = Tag(name=name, type=typ, A=A)

    if typ == "StructProperty":
        t.struct = r.fstr()
        t.B = r.i32()
        t.struct_path = r.fstr()
        t.C = r.i32()
        size = r.i32()
        _read_guid(r, t)
        vs = r.o
        ve = vs + size
        sub = Reader(r.d, vs)
        t.children = parse_taglist(sub, ve)
        r.o = ve
    elif typ == "ArrayProperty":
        t.inner = r.fstr()
        t.B = r.i32()
        if t.inner == "StructProperty":
            t.inner_struct = r.fstr()
            t.C = r.i32()
            t.inner_struct_path = r.fstr()
            t.D = r.i32()
        size = r.i32()
        _read_guid(r, t)
        vs = r.o
        ve = vs + size
        sub = Reader(r.d, vs)
        t.count = sub.i32()
        for _ in range(t.count):
            t.elements.append(parse_taglist(sub, ve))
        r.o = ve
    elif typ == "EnumProperty":
        t.enum = r.fstr()
        t.B = r.i32()
        t.enum_path = r.fstr()
        nested = parse_tag(r)
        if nested is None:
            raise FormatError(f"枚举 {name!r} 缺少内层字节属性")
        t.enum_value = nested
    elif typ == "ByteProperty":
        size = r.i32()
        _read_guid(r, t)
        t.value = r.take(size)
    else:
        size = r.i32()
        _read_guid(r, t)
        t.value = r.take(size)
    return t


def parse_taglist(r: Reader, end: int) -> List[Tag]:
    out: List[Tag] = []
    while r.o < end:
        t = parse_tag(r)
        if t is None:
            break
        out.append(t)
    return out


@dataclass
class GvasDoc:
    prefix: bytes
    tags: List[Tag]
    suffix: bytes
    header: dict


def parse_document(data: bytes) -> GvasDoc:
    if not data.startswith(MAGIC):
        raise FormatError("不是 GVAS 文件（缺少 GVAS 魔数）")
    idx = data.find(CLASS_PATH)
    if idx < 0:
        raise FormatError("未找到 /Script/ProjectPBZ.PBZInputUserSettings，可能不是本游戏的输入设置文件")
    r = Reader(data, idx - 4)
    class_name = r.fstr()
    class_end = r.o
    if class_end >= len(data) or data[class_end] != 0:
        raise FormatError("存档类名后缺少分隔字节")
    first_tag = class_end + 1

    hr = Reader(data, 4)
    save_ver = hr.i32()
    pkg4 = hr.i32()
    pkg5 = hr.i32()
    eng_major = struct.unpack("<H", hr.take(2))[0]
    eng_minor = struct.unpack("<H", hr.take(2))[0]
    eng_patch = struct.unpack("<H", hr.take(2))[0]
    eng_build = struct.unpack("<I", hr.take(4))[0]
    branch = hr.fstr()
    header = {
        "save_version": save_ver,
        "pkg_ue4": pkg4,
        "pkg_ue5": pkg5,
        "engine": f"{eng_major}.{eng_minor}.{eng_patch}",
        "changelist": eng_build,
        "branch": branch,
        "class": class_name,
    }

    tr = Reader(data, first_tag)
    tags = parse_taglist(tr, len(data))
    suffix = data[tr.o:]
    return GvasDoc(prefix=data[:first_tag], tags=tags, suffix=suffix, header=header)


def write_fstr(out: bytearray, s: Optional[str]) -> None:
    s = s or ""
    if s == "":
        out += _i32(0)
        return
    b = s.encode("utf-8")
    out += _i32(len(b) + 1)
    out += b
    out += b"\x00"


def write_taglist(out: bytearray, tags: List[Tag]) -> None:
    for t in tags:
        write_tag(out, t)
    write_fstr(out, "None")


def write_tag(out: bytearray, t: Tag) -> None:
    write_fstr(out, t.name)
    write_fstr(out, t.type)
    out += _i32(t.A)

    if t.type == "StructProperty":
        write_fstr(out, t.struct)
        out += _i32(t.B or 0)
        write_fstr(out, t.struct_path)
        out += _i32(t.C or 0)
        val = bytearray()
        write_taglist(val, t.children)
        out += _i32(len(val))
        out.append(t.has_guid)
        if t.has_guid and t.guid:
            out += t.guid
        out += val
    elif t.type == "ArrayProperty":
        write_fstr(out, t.inner)
        out += _i32(t.B or 0)
        if t.inner == "StructProperty":
            write_fstr(out, t.inner_struct)
            out += _i32(t.C or 0)
            write_fstr(out, t.inner_struct_path)
            out += _i32(t.D or 0)
        val = bytearray()
        val += _i32(t.count)
        for el in t.elements:
            write_taglist(val, el)
        out += _i32(len(val))
        out.append(t.has_guid)
        if t.has_guid and t.guid:
            out += t.guid
        out += val
    elif t.type == "EnumProperty":
        write_fstr(out, t.enum)
        out += _i32(t.B or 0)
        write_fstr(out, t.enum_path)
        if t.enum_value is None:
            raise FormatError(f"枚举 {t.name!r} 缺少内层属性")
        write_tag(out, t.enum_value)
    else:
        out += _i32(len(t.value))
        out.append(t.has_guid)
        if t.has_guid and t.guid:
            out += t.guid
        out += t.value


def serialize_document(doc: GvasDoc) -> bytes:
    out = bytearray()
    out += doc.prefix
    write_taglist(out, doc.tags)
    out += doc.suffix
    return bytes(out)


def fstr_bytes(s: str) -> bytes:
    b = s.encode("utf-8")
    return _i32(len(b) + 1) + b + b"\x00"


def decode_fstr(raw: bytes) -> str:
    if len(raw) < 4:
        return ""
    n = struct.unpack("<i", raw[:4])[0]
    if n == 0:
        return ""
    if n < 0:
        n = -n
        return raw[4:4 + 2 * n].decode("utf-16-le", "replace").rstrip("\x00")
    return raw[4:4 + n].split(b"\x00", 1)[0].decode("utf-8", "replace")