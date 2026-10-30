"""按键模型：读取 PBZInputUserSettings 的配置档、校验键位、应用修改。"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import gvas

DEFAULT_PROFILE = "PBZ.KeyProfile.Custom1"

ACTION_LABELS = {
    "IA_Jump": "跳跃",
    "IA_Interact": "交互",
    "IA_LightAttack": "轻攻击",
    "IA_HeavyAttack": "重攻击",
    "IA_Dodge": "闪避",
    "IA_MoveFast": "冲刺",
    "IA_Execute": "处决",
    "IA_Guard": "防御",
    "IA_LockTarget": "锁定目标",
    "IA_Crouch": "下蹲",
    "IA_UltimateSkill": "终极技能",
    "IA_ShadowArm": "影臂",
    "IA_ShadowArm_LongPress": "影臂长按",
    "IA_SwitchWeapon": "切换武器",
    "IA_SwitchShadowArm": "切换影臂",
    "IA_UseTopItem": "使用上方道具",
    "IA_UseBottomItem": "使用下方道具",
    "IA_OpenCharacterMenu": "角色菜单",
    "IA_OpenMapMenu": "地图菜单",
    "IA_Sense_Default": "感知",
}

SLOT_LABELS = {
    "EPlayerMappableKeySlot::First": "槽位 1",
    "EPlayerMappableKeySlot::Second": "槽位 2",
    "EPlayerMappableKeySlot::Third": "槽位 3",
    "EPlayerMappableKeySlot::Fourth": "槽位 4",
    "EPlayerMappableKeySlot::Fifth": "槽位 5",
    "EPlayerMappableKeySlot::Sixth": "槽位 6",
}

# (内部键名, 显示名, 分组)
KEY_CATALOG: List[Tuple[str, str, str]] = [
    ("Gamepad_FaceButton_Bottom", "A（下）", "面键"),
    ("Gamepad_FaceButton_Right", "B（右）", "面键"),
    ("Gamepad_FaceButton_Left", "X（左）", "面键"),
    ("Gamepad_FaceButton_Top", "Y（上）", "面键"),
    ("Gamepad_LeftShoulder", "LB", "肩键"),
    ("Gamepad_RightShoulder", "RB", "肩键"),
    ("Gamepad_LeftTrigger", "LT", "扳机"),
    ("Gamepad_LeftTriggerAxis", "LT（轴）", "扳机"),
    ("Gamepad_RightTrigger", "RT", "扳机"),
    ("Gamepad_RightTriggerAxis", "RT（轴）", "扳机"),
    ("Gamepad_LeftThumbstick", "LS（按下左摇杆）", "摇杆"),
    ("Gamepad_RightThumbstick", "RS（按下右摇杆）", "摇杆"),
    ("Gamepad_DPad_Up", "十字键 上", "十字键"),
    ("Gamepad_DPad_Down", "十字键 下", "十字键"),
    ("Gamepad_DPad_Left", "十字键 左", "十字键"),
    ("Gamepad_DPad_Right", "十字键 右", "十字键"),
    ("Gamepad_Special_Left", "View / Back", "系统键"),
    ("Gamepad_Special_Right", "Menu / Start", "系统键"),
]

KNOWN_KEYS = {k for k, _, _ in KEY_CATALOG}
KEY_LABELS = {k: label for k, label, _ in KEY_CATALOG}
KEY_GROUPS = [g for g in dict.fromkeys(g for _, _, g in KEY_CATALOG)]


class KeymapError(Exception):
    pass


@dataclass
class Binding:
    action: str
    slot: str
    default_key: str
    key: str
    key_tag: gvas.Tag


@dataclass
class Profile:
    profile_id: str
    family: str
    keys_tag: gvas.Tag
    bindings: List[Binding]


def _find(tags: List[gvas.Tag], name: str) -> gvas.Tag:
    for t in tags:
        if t.name == name:
            return t
    raise KeymapError(f"缺少属性 {name!r}")


def _find_optional(tags: List[gvas.Tag], name: str):
    for t in tags:
        if t.name == name:
            return t
    return None


def _key_name(struct_tag: gvas.Tag) -> gvas.Tag:
    for c in struct_tag.children:
        if c.name == "KeyName" and c.type == "NameProperty":
            return c
    raise KeymapError(f"结构 {struct_tag.name!r} 缺少 KeyName")


def current_profile_id(doc: gvas.GvasDoc) -> str:
    for t in doc.tags:
        if t.name == "CurrentProfileIdentifierString" and t.type == "StrProperty":
            return gvas.decode_fstr(t.value)
    raise KeymapError("缺少 CurrentProfileIdentifierString")


def _read_profiles(doc: gvas.GvasDoc) -> List[Profile]:
    arr = None
    for t in doc.tags:
        if t.name == "GamepadFamilyProfiles" and t.type == "ArrayProperty":
            arr = t
            break
    if arr is None:
        raise KeymapError("缺少 GamepadFamilyProfiles 数组")

    profiles: List[Profile] = []
    for el in arr.elements:
        pid = gvas.decode_fstr(_find(el, "ProfileId").value)
        fam = gvas.decode_fstr(_find(el, "Family").value)
        keys_tag = _find(el, "Keys")
        bindings: List[Binding] = []
        for kel in keys_tag.elements:
            mapping = _find(kel, "MappingName")
            slot = _find(kel, "Slot")
            default_key = _find(kel, "DefaultKey")
            key = _find(kel, "Key")
            if slot.enum_value is None:
                raise KeymapError(f"{pid} 的 {mapping} 槽位缺少枚举值")
            bindings.append(
                Binding(
                    action=gvas.decode_fstr(mapping.value),
                    slot=gvas.decode_fstr(slot.enum_value.value),
                    default_key=gvas.decode_fstr(_key_name(default_key).value),
                    key=gvas.decode_fstr(_key_name(key).value),
                    key_tag=_key_name(key),
                )
            )
        profiles.append(Profile(profile_id=pid, family=fam, keys_tag=keys_tag, bindings=bindings))
    return profiles


def get_profiles(doc: gvas.GvasDoc) -> List[Profile]:
    return _read_profiles(doc)


def get_profile(doc: gvas.GvasDoc, profile_id: str) -> Profile:
    for p in _read_profiles(doc):
        if p.profile_id == profile_id:
            return p
    raise KeymapError(f"找不到配置档 {profile_id!r}")


def _extra_keys(profiles: List[Profile]) -> List[str]:
    out = []
    for p in profiles:
        for b in p.bindings:
            if b.key not in KNOWN_KEYS and b.key not in out:
                out.append(b.key)
    return out


def build_model(doc: gvas.GvasDoc) -> dict:
    profiles = _read_profiles(doc)
    extra = _extra_keys(profiles)
    keys = [
        {"id": k, "label": label, "group": group}
        for k, label, group in KEY_CATALOG
    ]
    for k in extra:
        keys.append({"id": k, "label": f"{k}（非标准手柄键）", "group": "其他"})

    out_profiles = []
    for p in profiles:
        rows = []
        for b in p.bindings:
            rows.append(
                {
                    "action": b.action,
                    "action_label": ACTION_LABELS.get(b.action, b.action),
                    "slot": b.slot,
                    "slot_label": SLOT_LABELS.get(b.slot, b.slot),
                    "default_key": b.default_key,
                    "key": b.key,
                    "key_label": KEY_LABELS.get(b.key, b.key),
                }
            )
        out_profiles.append(
            {
                "id": p.profile_id,
                "family": p.family,
                "bindings": rows,
            }
        )

    return {
        "header": doc.header,
        "current_profile": current_profile_id(doc),
        "default_profile": DEFAULT_PROFILE,
        "profiles": out_profiles,
        "keys": keys,
        "key_groups": KEY_GROUPS + (["其他"] if extra else []),
        "action_labels": ACTION_LABELS,
    }


def apply_edits(
    doc: gvas.GvasDoc,
    profile_id: str,
    bindings: List[dict],
    set_current: bool,
) -> List[str]:
    """就地修改文档，返回校验警告。bindings 形如 {action, slot, key}。"""
    warnings: List[str] = []
    profile = get_profile(doc, profile_id)
    index: Dict[Tuple[str, str], Binding] = {(b.action, b.slot): b for b in profile.bindings}

    for item in bindings:
        action = item.get("action")
        slot = item.get("slot")
        key = item.get("key")
        if not action or not slot or not key:
            raise KeymapError("修改项缺少 action/slot/key")
        if key not in KNOWN_KEYS and key not in {b.key for b in profile.bindings}:
            raise KeymapError(f"不支持的按键 {key!r}")
        target = index.get((action, slot))
        if target is None:
            raise KeymapError(f"配置档 {profile_id} 中不存在 {action} / {slot}")
        target.key_tag.value = gvas.fstr_bytes(key)
        target.key = key

    if set_current:
        for t in doc.tags:
            if t.name == "CurrentProfileIdentifierString" and t.type == "StrProperty":
                t.value = gvas.fstr_bytes(profile_id)
                break
        else:
            raise KeymapError("缺少 CurrentProfileIdentifierString")

    # 冲突检测：同一按键绑定到多个不同动作才算冲突（同动作多槽位是正常备用绑定）
    seen: Dict[str, List[str]] = {}
    for b in profile.bindings:
        label = ACTION_LABELS.get(b.action, b.action)
        bucket = seen.setdefault(b.key, [])
        if label not in bucket:
            bucket.append(label)
    for key, actions in seen.items():
        if len(actions) > 1:
            warnings.append(f"{KEY_LABELS.get(key, key)} 同时绑定到 {len(actions)} 个动作：{'、'.join(actions)}")

    return warnings


def binding_signature(doc: gvas.GvasDoc) -> dict:
    """用于校验其他档位未被改动的快照。"""
    return {
        p.profile_id: sorted((b.action, b.slot, b.default_key, b.key) for b in p.bindings)
        for p in _read_profiles(doc)
    }