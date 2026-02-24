from prediction_mirror.platforms import register_adapter
from prediction_mirror.platforms.polymarket.adapter import PolymarketAdapter

register_adapter("polymarket", PolymarketAdapter)

__all__ = ["PolymarketAdapter"]
