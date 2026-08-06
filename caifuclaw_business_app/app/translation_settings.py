# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .credential_manager import get_credential_manager
from .models import TranslationProviderSetting
from .translation_service import (
    BAIDU_TRANSLATE_BATCH_CHARS,
    BAIDU_TRANSLATE_BATCH_SIZE,
    BAIDU_TRANSLATE_ENDPOINT,
    BaiduTranslationClient,
    DisabledTranslationClient,
    TranslationUnavailable,
)


DEFAULT_TRANSLATION_PROVIDER = "baidu"
TRANSLATION_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "baidu": {
        "code": "baidu",
        "name": "百度翻译",
        "endpoint": BAIDU_TRANSLATE_ENDPOINT,
    },
}
TRANSLATION_LANGUAGE_PRESETS: tuple[dict[str, str], ...] = (
    {"code": "ru", "label": "俄语（ru）"},
    {"code": "es-419", "label": "西班牙语（拉丁美洲，es-419）"},
    {"code": "es-MX", "label": "西班牙语（墨西哥，es-MX）"},
    {"code": "pt-BR", "label": "葡萄牙语（巴西，pt-BR）"},
    {"code": "pl", "label": "波兰语（pl）"},
    {"code": "en", "label": "英语（en）"},
    {"code": "zh", "label": "中文（zh）"},
)

# Baidu Translate full language list, source: https://baidufanyi.apifox.cn/doc-1006685, updated 2026-07-23.
BAIDU_LANGUAGE_PRESETS: tuple[dict[str, str], ...] = (
    {"code": "ara", "label": "阿拉伯语（ara）"},
    {"code": "gle", "label": "爱尔兰语（gle）"},
    {"code": "oci", "label": "奥克语（oci）"},
    {"code": "alb", "label": "阿尔巴尼亚语（alb）"},
    {"code": "arq", "label": "阿尔及利亚阿拉伯语（arq）"},
    {"code": "aka", "label": "阿肯语（aka）"},
    {"code": "arg", "label": "阿拉贡语（arg）"},
    {"code": "amh", "label": "阿姆哈拉语（amh）"},
    {"code": "asm", "label": "阿萨姆语（asm）"},
    {"code": "aym", "label": "艾马拉语（aym）"},
    {"code": "aze", "label": "阿塞拜疆语（aze）"},
    {"code": "ast", "label": "阿斯图里亚斯语（ast）"},
    {"code": "oss", "label": "奥塞梯语（oss）"},
    {"code": "est", "label": "爱沙尼亚语（est）"},
    {"code": "oji", "label": "奥杰布瓦语（oji）"},
    {"code": "ori", "label": "奥里亚语（ori）"},
    {"code": "orm", "label": "奥罗莫语（orm）"},
    {"code": "pl", "label": "波兰语（pl）"},
    {"code": "per", "label": "波斯语（per）"},
    {"code": "bre", "label": "布列塔尼语（bre）"},
    {"code": "bak", "label": "巴什基尔语（bak）"},
    {"code": "baq", "label": "巴斯克语（baq）"},
    {"code": "pot", "label": "巴西葡萄牙语（pot）"},
    {"code": "bel", "label": "白俄罗斯语（bel）"},
    {"code": "ber", "label": "柏柏尔语（ber）"},
    {"code": "pam", "label": "邦板牙语（pam）"},
    {"code": "bul", "label": "保加利亚语（bul）"},
    {"code": "sme", "label": "北方萨米语（sme）"},
    {"code": "ped", "label": "北索托语（ped）"},
    {"code": "bem", "label": "本巴语（bem）"},
    {"code": "bli", "label": "比林语（bli）"},
    {"code": "bis", "label": "比斯拉马语（bis）"},
    {"code": "bal", "label": "俾路支语（bal）"},
    {"code": "ice", "label": "冰岛语（ice）"},
    {"code": "bos", "label": "波斯尼亚语（bos）"},
    {"code": "bho", "label": "博杰普尔语（bho）"},
    {"code": "chv", "label": "楚瓦什语（chv）"},
    {"code": "tso", "label": "聪加语（tso）"},
    {"code": "dan", "label": "丹麦语（dan）"},
    {"code": "de", "label": "德语（de）"},
    {"code": "tat", "label": "鞑靼语（tat）"},
    {"code": "sha", "label": "掸语（sha）"},
    {"code": "tet", "label": "德顿语（tet）"},
    {"code": "div", "label": "迪维希语（div）"},
    {"code": "log", "label": "低地德语（log）"},
    {"code": "ru", "label": "俄语（ru）"},
    {"code": "fra", "label": "法语（fra）"},
    {"code": "fil", "label": "菲律宾语（fil）"},
    {"code": "fin", "label": "芬兰语（fin）"},
    {"code": "san", "label": "梵语（san）"},
    {"code": "fri", "label": "弗留利语（fri）"},
    {"code": "ful", "label": "富拉尼语（ful）"},
    {"code": "fao", "label": "法罗语（fao）"},
    {"code": "gla", "label": "盖尔语（gla）"},
    {"code": "kon", "label": "刚果语（kon）"},
    {"code": "ups", "label": "高地索布语（ups）"},
    {"code": "hkm", "label": "高棉语（hkm）"},
    {"code": "kal", "label": "格陵兰语（kal）"},
    {"code": "geo", "label": "格鲁吉亚语（geo）"},
    {"code": "guj", "label": "古吉拉特语（guj）"},
    {"code": "gra", "label": "古希腊语（gra）"},
    {"code": "eno", "label": "古英语（eno）"},
    {"code": "grn", "label": "瓜拉尼语（grn）"},
    {"code": "kor", "label": "韩语（kor）"},
    {"code": "nl", "label": "荷兰语（nl）"},
    {"code": "hup", "label": "胡帕语（hup）"},
    {"code": "hak", "label": "哈卡钦语（hak）"},
    {"code": "ht", "label": "海地语（ht）"},
    {"code": "mot", "label": "黑山语（mot）"},
    {"code": "hau", "label": "豪萨语（hau）"},
    {"code": "kir", "label": "吉尔吉斯语（kir）"},
    {"code": "glg", "label": "加利西亚语（glg）"},
    {"code": "frn", "label": "加拿大法语（frn）"},
    {"code": "cat", "label": "加泰罗尼亚语（cat）"},
    {"code": "cs", "label": "捷克语（cs）"},
    {"code": "kab", "label": "卡拜尔语（kab）"},
    {"code": "kan", "label": "卡纳达语（kan）"},
    {"code": "kau", "label": "卡努里语（kau）"},
    {"code": "kah", "label": "卡舒比语（kah）"},
    {"code": "cor", "label": "康瓦尔语（cor）"},
    {"code": "xho", "label": "科萨语（xho）"},
    {"code": "cos", "label": "科西嘉语（cos）"},
    {"code": "cre", "label": "克里克语（cre）"},
    {"code": "cri", "label": "克里米亚鞑靼语（cri）"},
    {"code": "kli", "label": "克林贡语（kli）"},
    {"code": "hrv", "label": "克罗地亚语（hrv）"},
    {"code": "que", "label": "克丘亚语（que）"},
    {"code": "kas", "label": "克什米尔语（kas）"},
    {"code": "kok", "label": "孔卡尼语（kok）"},
    {"code": "kur", "label": "库尔德语（kur）"},
    {"code": "lat", "label": "拉丁语（lat）"},
    {"code": "lao", "label": "老挝语（lao）"},
    {"code": "rom", "label": "罗马尼亚语（rom）"},
    {"code": "lag", "label": "拉特加莱语（lag）"},
    {"code": "lav", "label": "拉脱维亚语（lav）"},
    {"code": "lim", "label": "林堡语（lim）"},
    {"code": "lin", "label": "林加拉语（lin）"},
    {"code": "lug", "label": "卢干达语（lug）"},
    {"code": "ltz", "label": "卢森堡语（ltz）"},
    {"code": "ruy", "label": "卢森尼亚语（ruy）"},
    {"code": "kin", "label": "卢旺达语（kin）"},
    {"code": "lit", "label": "立陶宛语（lit）"},
    {"code": "roh", "label": "罗曼什语（roh）"},
    {"code": "ro", "label": "罗姆语（ro）"},
    {"code": "loj", "label": "逻辑语（loj）"},
    {"code": "may", "label": "马来语（may）"},
    {"code": "bur", "label": "缅甸语（bur）"},
    {"code": "mar", "label": "马拉地语（mar）"},
    {"code": "mg", "label": "马拉加斯语（mg）"},
    {"code": "mal", "label": "马拉雅拉姆语（mal）"},
    {"code": "mac", "label": "马其顿语（mac）"},
    {"code": "mah", "label": "马绍尔语（mah）"},
    {"code": "mai", "label": "迈蒂利语（mai）"},
    {"code": "glv", "label": "曼克斯语（glv）"},
    {"code": "mau", "label": "毛里求斯克里奥尔语（mau）"},
    {"code": "mao", "label": "毛利语（mao）"},
    {"code": "ben", "label": "孟加拉语（ben）"},
    {"code": "mlt", "label": "马耳他语（mlt）"},
    {"code": "hmn", "label": "苗语（hmn）"},
    {"code": "nor", "label": "挪威语（nor）"},
    {"code": "nea", "label": "那不勒斯语（nea）"},
    {"code": "nbl", "label": "南恩德贝莱语（nbl）"},
    {"code": "afr", "label": "南非荷兰语（afr）"},
    {"code": "sot", "label": "南索托语（sot）"},
    {"code": "nep", "label": "尼泊尔语（nep）"},
    {"code": "pt", "label": "葡萄牙语（pt）"},
    {"code": "pan", "label": "旁遮普语（pan）"},
    {"code": "pap", "label": "帕皮阿门托语（pap）"},
    {"code": "pus", "label": "普什图语（pus）"},
    {"code": "nya", "label": "齐切瓦语（nya）"},
    {"code": "twi", "label": "契维语（twi）"},
    {"code": "chr", "label": "切罗基语（chr）"},
    {"code": "jp", "label": "日语（jp）"},
    {"code": "swe", "label": "瑞典语（swe）"},
    {"code": "srd", "label": "萨丁尼亚语（srd）"},
    {"code": "sm", "label": "萨摩亚语（sm）"},
    {"code": "sec", "label": "塞尔维亚-克罗地亚语（sec）"},
    {"code": "srp", "label": "塞尔维亚语（srp）"},
    {"code": "sol", "label": "桑海语（sol）"},
    {"code": "sin", "label": "僧伽罗语（sin）"},
    {"code": "epo", "label": "世界语（epo）"},
    {"code": "nob", "label": "书面挪威语（nob）"},
    {"code": "sk", "label": "斯洛伐克语（sk）"},
    {"code": "slo", "label": "斯洛文尼亚语（slo）"},
    {"code": "swa", "label": "斯瓦希里语（swa）"},
    {"code": "src", "label": "塞尔维亚语（西里尔）（src）"},
    {"code": "som", "label": "索马里语（som）"},
    {"code": "th", "label": "泰语（th）"},
    {"code": "tr", "label": "土耳其语（tr）"},
    {"code": "tgk", "label": "塔吉克语（tgk）"},
    {"code": "tam", "label": "泰米尔语（tam）"},
    {"code": "tgl", "label": "他加禄语（tgl）"},
    {"code": "tir", "label": "提格利尼亚语（tir）"},
    {"code": "tel", "label": "泰卢固语（tel）"},
    {"code": "tua", "label": "突尼斯阿拉伯语（tua）"},
    {"code": "tuk", "label": "土库曼语（tuk）"},
    {"code": "ukr", "label": "乌克兰语（ukr）"},
    {"code": "wln", "label": "瓦隆语（wln）"},
    {"code": "wel", "label": "威尔士语（wel）"},
    {"code": "ven", "label": "文达语（ven）"},
    {"code": "wol", "label": "沃洛夫语（wol）"},
    {"code": "urd", "label": "乌尔都语（urd）"},
    {"code": "spa", "label": "西班牙语（spa）"},
    {"code": "heb", "label": "希伯来语（heb）"},
    {"code": "el", "label": "希腊语（el）"},
    {"code": "hu", "label": "匈牙利语（hu）"},
    {"code": "fry", "label": "西弗里斯语（fry）"},
    {"code": "sil", "label": "西里西亚语（sil）"},
    {"code": "hil", "label": "希利盖农语（hil）"},
    {"code": "los", "label": "下索布语（los）"},
    {"code": "haw", "label": "夏威夷语（haw）"},
    {"code": "nno", "label": "新挪威语（nno）"},
    {"code": "nqo", "label": "西非书面语（nqo）"},
    {"code": "snd", "label": "信德语（snd）"},
    {"code": "sna", "label": "修纳语（sna）"},
    {"code": "ceb", "label": "宿务语（ceb）"},
    {"code": "syr", "label": "叙利亚语（syr）"},
    {"code": "sun", "label": "巽他语（sun）"},
    {"code": "en", "label": "英语（en）"},
    {"code": "hi", "label": "印地语（hi）"},
    {"code": "id", "label": "印尼语（id）"},
    {"code": "it", "label": "意大利语（it）"},
    {"code": "vie", "label": "越南语（vie）"},
    {"code": "yid", "label": "意第绪语（yid）"},
    {"code": "ina", "label": "因特语（ina）"},
    {"code": "ach", "label": "亚齐语（ach）"},
    {"code": "ing", "label": "印古什语（ing）"},
    {"code": "ibo", "label": "伊博语（ibo）"},
    {"code": "ido", "label": "伊多语（ido）"},
    {"code": "yor", "label": "约鲁巴语（yor）"},
    {"code": "arm", "label": "亚美尼亚语（arm）"},
    {"code": "iku", "label": "伊努克提图特语（iku）"},
    {"code": "ir", "label": "伊朗语（ir）"},
    {"code": "zh", "label": "中文(简体)（zh）"},
    {"code": "cht", "label": "中文(繁体)（cht）"},
    {"code": "wyw", "label": "中文(文言文)（wyw）"},
    {"code": "yue", "label": "中文(粤语)（yue）"},
    {"code": "zaz", "label": "扎扎其语（zaz）"},
    {"code": "frm", "label": "中古法语（frm）"},
    {"code": "zul", "label": "祖鲁语（zul）"},
    {"code": "jav", "label": "爪哇语（jav）"},
)


def list_translation_provider_presets() -> list[dict[str, str]]:
    return [dict(item) for item in TRANSLATION_PROVIDER_PRESETS.values()]


def list_translation_language_presets() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in (*TRANSLATION_LANGUAGE_PRESETS, *BAIDU_LANGUAGE_PRESETS):
        code = str(item.get("code") or "").strip()
        label = str(item.get("label") or "").strip()
        if not code or not label or code in seen:
            continue
        seen.add(code)
        items.append({"code": code, "label": label})
    return items


def normalize_translation_provider(provider: object = None) -> str:
    code = str(provider or DEFAULT_TRANSLATION_PROVIDER).strip().lower()
    if not code:
        code = DEFAULT_TRANSLATION_PROVIDER
    if code not in TRANSLATION_PROVIDER_PRESETS:
        raise ValueError(f"Unsupported translation provider: {code}")
    return code


def translation_provider_name(provider: object = None) -> str:
    code = normalize_translation_provider(provider)
    return TRANSLATION_PROVIDER_PRESETS[code]["name"]


def translation_provider_endpoint(provider: object = None) -> str:
    code = normalize_translation_provider(provider)
    return TRANSLATION_PROVIDER_PRESETS[code].get("endpoint") or ""


def encrypt_translation_secret_key(secret_key: str | None) -> bytes | None:
    value = (secret_key or "").strip()
    if not value:
        return None
    return get_credential_manager().encrypt_credentials({"secret_key": value})


def decrypt_translation_secret_key(row: TranslationProviderSetting) -> str:
    data = get_credential_manager().decrypt_credentials(row.encrypted_secret_key)
    return str(data.get("secret_key") or "")


def mask_translation_secret_key(secret_key: str) -> str:
    value = (secret_key or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}****{value[-4:]}"


def translation_provider_options_dict(row: TranslationProviderSetting) -> dict:
    value = row.provider_options_json or "{}"
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def dumps_translation_provider_options(value: object) -> str:
    data = value if isinstance(value, dict) else {}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _seed_translation_provider_setting_from_config(row: TranslationProviderSetting) -> None:
    if row.provider != "baidu" or row.app_id or row.encrypted_secret_key:
        return
    client = BaiduTranslationClient.from_config()
    if not client.available:
        return
    row.enabled = True
    row.app_id = client.appid
    row.encrypted_secret_key = encrypt_translation_secret_key(client.secret_key)
    row.endpoint = client.endpoint or BAIDU_TRANSLATE_ENDPOINT


def get_translation_provider_setting(
    db: Session,
    provider: object = DEFAULT_TRANSLATION_PROVIDER,
) -> TranslationProviderSetting:
    code = normalize_translation_provider(provider)
    row = db.scalar(select(TranslationProviderSetting).where(TranslationProviderSetting.provider == code))
    if row is None:
        row = TranslationProviderSetting(
            provider=code,
            provider_name=translation_provider_name(code),
            enabled=False,
            app_id="",
            endpoint=translation_provider_endpoint(code),
            source_language="auto",
            timeout_seconds=30,
            max_retries=2,
            batch_size=BAIDU_TRANSLATE_BATCH_SIZE,
            batch_chars=BAIDU_TRANSLATE_BATCH_CHARS,
            provider_options_json="{}",
        )
        _seed_translation_provider_setting_from_config(row)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def build_translation_client_from_setting(row: TranslationProviderSetting):
    provider = normalize_translation_provider(row.provider)
    name = row.provider_name or translation_provider_name(provider)
    if not row.enabled:
        return DisabledTranslationClient(f"{name}未启用")
    if provider == "baidu":
        return BaiduTranslationClient(
            appid=row.app_id or "",
            secret_key=decrypt_translation_secret_key(row) if row.encrypted_secret_key else "",
            endpoint=row.endpoint or BAIDU_TRANSLATE_ENDPOINT,
            timeout=float(row.timeout_seconds or 30),
            max_retries=int(row.max_retries or 0),
            batch_size=int(row.batch_size or BAIDU_TRANSLATE_BATCH_SIZE),
            batch_chars=int(row.batch_chars or BAIDU_TRANSLATE_BATCH_CHARS),
        )
    raise TranslationUnavailable(f"{name}暂未实现")
