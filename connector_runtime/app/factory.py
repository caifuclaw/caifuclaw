from .adapters.allegro import AllegroConnector
from .adapters.aliexpress import AliExpressConnector
from .adapters.amazon import AmazonConnector
from .adapters.coupang import CoupangConnector
from .adapters.dmsmatrix import DMSMatrixConnector
from .adapters.ebay import EbayConnector
from .adapters.joom import JoomLogisticsConnector
from .adapters.lazada import LazadaConnector
from .adapters.mercado import MercadoGlobalConnector
from .adapters.ozon import OzonConnector
from .adapters.shopee import ShopeeConnector
from .adapters.shein import SheinConnector
from .adapters.shopify import ShopifyConnector
from .adapters.temu import TemuConnector
from .adapters.tiktok_shop import TikTokShopConnector
from .adapters.walmart import WalmartConnector
from .adapters.wayfair import WayfairConnector
from .adapters.wildberries import WildberriesConnector


def canonical_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    return {
        "joomlogistics": "joom_logistics",
        "mercado": "mercadolibre",
        "mercado_global": "mercadolibre",
        "mercadoglobal": "mercadolibre",
        "mercado_libre": "mercadolibre",
        "wildberrie": "wildberries",
        "tiktok": "tiktok_shop",
        "tiktokshop": "tiktok_shop",
        "tiktok_shop": "tiktok_shop",
        "ali_express": "aliexpress",
        "amazon_spapi": "amazon",
        "shopify_admin": "shopify",
        "ebay_sell": "ebay",
        "walmart_marketplace": "walmart",
        "shein_open": "shein",
        "coupang_openapi": "coupang",
        "wayfair_partner": "wayfair",
        "dms_matrix": "dmsmatrix",
        "dms-matrix": "dmsmatrix",
        "dms_matrix_erp": "dmsmatrix",
        "dmsmatrix_erp": "dmsmatrix",
    }.get(normalized, normalized)


def connector_for(platform: str, credentials: dict, settings: dict):
    platform = canonical_platform(platform)
    if platform == "ozon":
        return OzonConnector(credentials, settings)
    if platform == "allegro":
        return AllegroConnector(credentials, settings)
    if platform == "joom_logistics":
        return JoomLogisticsConnector(credentials, settings)
    if platform == "mercadolibre":
        return MercadoGlobalConnector(credentials, settings)
    if platform == "wildberries":
        return WildberriesConnector(credentials, settings)
    if platform == "amazon":
        return AmazonConnector(credentials, settings)
    if platform == "shopee":
        return ShopeeConnector(credentials, settings)
    if platform == "tiktok_shop":
        return TikTokShopConnector(credentials, settings)
    if platform == "aliexpress":
        return AliExpressConnector(credentials, settings)
    if platform == "lazada":
        return LazadaConnector(credentials, settings)
    if platform == "shopify":
        return ShopifyConnector(credentials, settings)
    if platform == "ebay":
        return EbayConnector(credentials, settings)
    if platform == "walmart":
        return WalmartConnector(credentials, settings)
    if platform == "temu":
        return TemuConnector(credentials, settings)
    if platform == "shein":
        return SheinConnector(credentials, settings)
    if platform == "coupang":
        return CoupangConnector(credentials, settings)
    if platform == "wayfair":
        return WayfairConnector(credentials, settings)
    if platform == "dmsmatrix":
        return DMSMatrixConnector(credentials, settings)
    raise ValueError(f"Unsupported platform: {platform}")
