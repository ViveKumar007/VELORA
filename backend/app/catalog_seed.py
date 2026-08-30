"""The demo storefront: merchants and what they sell.

Chosen so that one policy can reach every decision path. Against a grocery
authorization (Blinkit + Zepto, groceries, max 500/purchase, auto-approve at
or below 300) the catalog yields an auto-approval, an escalation, a price
block with a recoverable alternative, a merchant block, and a category block.
"""

MERCHANTS = [
    dict(
        slug="blinkit",
        name="Blinkit",
        description="Ten-minute grocery delivery.",
        categories=["groceries"],
    ),
    dict(
        slug="zepto",
        name="Zepto",
        description="Quick-commerce groceries and essentials.",
        categories=["groceries"],
    ),
    dict(
        slug="amazon",
        name="Amazon",
        description="General marketplace. Electronics and more.",
        categories=["electronics"],
    ),
    dict(
        slug="swiggy",
        name="Swiggy",
        description="Restaurant food delivery.",
        categories=["food"],
    ),
    dict(
        slug="demostore",
        name="DemoStore",
        description="Reference merchant used by the built-in demo policy.",
        categories=["electronics", "digital_goods"],
    ),
]

PRODUCTS = [
    # --- Blinkit: groceries ---
    dict(merchant="blinkit", name="Amul Gold Milk 1L", price=68, category="groceries",
         rating=4.5, attributes={"unit": "1 L"},
         description="Full cream milk."),
    dict(merchant="blinkit", name="Britannia Brown Bread", price=45, category="groceries",
         rating=4.1, attributes={"unit": "400 g"},
         description="Whole wheat loaf."),
    dict(merchant="blinkit", name="Farm Eggs (12)", price=89, category="groceries",
         rating=4.3, attributes={"count": 12},
         description="Free-range eggs."),
    dict(merchant="blinkit", name="Weekly Veggie Box", price=420, category="groceries",
         rating=4.4, attributes={"serves": "family of 4"},
         description="Seasonal vegetables for a week."),

    # --- Zepto: groceries ---
    dict(merchant="zepto", name="Amul Butter 500g", price=285, category="groceries",
         rating=4.7, attributes={"unit": "500 g"},
         description="Salted butter."),
    dict(merchant="zepto", name="Fortune Sunflower Oil 1L", price=145, category="groceries",
         rating=4.2, attributes={"unit": "1 L"},
         description="Refined cooking oil."),
    dict(merchant="zepto", name="India Gate Basmati 5kg", price=649, category="groceries",
         rating=4.6, attributes={"unit": "5 kg"},
         description="Aged basmati rice."),

    # --- Amazon: electronics (outside a grocery authorization) ---
    dict(merchant="amazon", name="boAt Airdopes 141", price=1299, category="electronics",
         rating=4.2, attributes={"battery_hours": 42, "wireless": True},
         description="Wireless earbuds, 42h playback."),
    dict(merchant="amazon", name="Espresso Machine", price=14999, category="electronics",
         rating=4.4, attributes={"wattage": 1350},
         description="Pump espresso machine."),

    # --- Swiggy: food ---
    dict(merchant="swiggy", name="Hyderabadi Biryani (serves 2)", price=549, category="food",
         rating=4.5, attributes={"serves": 2},
         description="Dum biryani with raita."),

    # --- DemoStore: the original headphone demo ---
    dict(merchant="demostore", name="SoundBeat Lite", price=1299, category="electronics",
         rating=4.2, attributes={"battery_hours": 30, "wireless": True},
         description="Lightweight wireless headphones, 30h playback."),
    dict(merchant="demostore", name="SoundBeat Pro", price=1799, category="electronics",
         rating=4.6, attributes={"battery_hours": 50, "wireless": True,
                                 "noise_cancellation": True},
         description="Wireless headphones, 50h playback, deep bass."),
    dict(merchant="demostore", name="Premium Audio Max", price=2499, category="electronics",
         rating=4.8, attributes={"battery_hours": 60, "wireless": True,
                                 "noise_cancellation": True},
         description="Flagship over-ear headphones, 60h playback."),
    dict(merchant="demostore", name="Gaming Subscription (3 months)", price=999,
         category="digital_goods", rating=4.1, attributes={"duration_months": 3},
         description="Cloud gaming pass. Digital goods, not electronics."),
]
