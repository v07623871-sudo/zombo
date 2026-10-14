"""Balanced ZOMBO workshop equipment and exclusive case loot tables.

All values are authorable and tested. Case-exclusive weapons are deliberately
absent from NEW_RECIPES; existing prices for Stars and VIP are unchanged.
"""
NEW_GEAR = {
  "pipe_rifle": {
    "name": "Самодельная винтовка",
    "icon": "🔩",
    "slot": "weapon",
    "power": 19,
    "defense": 0,
    "material": "metal"
  },
  "nailgun": {
    "name": "Гвоздомёт",
    "icon": "📌",
    "slot": "weapon",
    "power": 16,
    "defense": 0,
    "material": "metal"
  },
  "flare_gun": {
    "name": "Сигнальный пистолет",
    "icon": "🔥",
    "slot": "weapon",
    "power": 12,
    "defense": 0,
    "material": "metal"
  },
  "coil_pistol": {
    "name": "Катушечный пистолет",
    "icon": "⚡",
    "slot": "weapon",
    "power": 23,
    "defense": 0,
    "material": "wire"
  },
  "harpoon_gun": {
    "name": "Гарпунная пушка",
    "icon": "🔱",
    "slot": "weapon",
    "power": 25,
    "defense": 0,
    "material": "metal"
  },
  "lever_rifle": {
    "name": "Рычажная винтовка",
    "icon": "🎯",
    "slot": "weapon",
    "power": 30,
    "defense": 0,
    "material": "metal"
  },
  "sawed_shotgun": {
    "name": "Обрез",
    "icon": "🔫",
    "slot": "weapon",
    "power": 24,
    "defense": 0,
    "material": "metal"
  },
  "compound_bow": {
    "name": "Композитный лук",
    "icon": "🏹",
    "slot": "weapon",
    "power": 28,
    "defense": 0,
    "material": "wood"
  },
  "breacher": {
    "name": "Штурмовой дробовик",
    "icon": "💥",
    "slot": "weapon",
    "power": 34,
    "defense": 0,
    "material": "metal"
  },
  "battle_rifle": {
    "name": "Боевая винтовка",
    "icon": "🔫",
    "slot": "weapon",
    "power": 37,
    "defense": 0,
    "material": "metal"
  },
  "patrol_coat": {
    "name": "Патрульный плащ",
    "icon": "🧥",
    "slot": "armor",
    "power": 0,
    "defense": 4,
    "material": "cloth"
  },
  "road_armor": {
    "name": "Броня дорожника",
    "icon": "🛡️",
    "slot": "armor",
    "power": 0,
    "defense": 7,
    "material": "metal"
  },
  "plated_jacket": {
    "name": "Пластинчатая куртка",
    "icon": "🧥",
    "slot": "armor",
    "power": 0,
    "defense": 9,
    "material": "metal"
  },
  "kevlar_mesh": {
    "name": "Кевларовая сетка",
    "icon": "🛡️",
    "slot": "armor",
    "power": 0,
    "defense": 11,
    "material": "cloth"
  },
  "reactive_armor": {
    "name": "Реактивный панцирь",
    "icon": "⚙️",
    "slot": "armor",
    "power": 0,
    "defense": 13,
    "material": "metal"
  },
  "scout_armor": {
    "name": "Лёгкая броня разведчика",
    "icon": "🥷",
    "slot": "armor",
    "power": 0,
    "defense": 6,
    "material": "cloth"
  },
  "viper": {
    "name": "Гадюка-М",
    "icon": "🐍",
    "slot": "weapon",
    "power": 23,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "field_case"
  },
  "ember": {
    "name": "Жар-пистолет",
    "icon": "🔥",
    "slot": "weapon",
    "power": 26,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "field_case"
  },
  "thorn": {
    "name": "Шипомёт",
    "icon": "🌵",
    "slot": "weapon",
    "power": 28,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "field_case"
  },
  "hunter_zero": {
    "name": "Охотник-0",
    "icon": "🎯",
    "slot": "weapon",
    "power": 30,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "field_case"
  },
  "aegis": {
    "name": "Эгида-12",
    "icon": "🛡️",
    "slot": "weapon",
    "power": 31,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "military_case"
  },
  "thunder": {
    "name": "Гром-9",
    "icon": "⚡",
    "slot": "weapon",
    "power": 34,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "military_case"
  },
  "widow": {
    "name": "Чёрная вдова",
    "icon": "🕷️",
    "slot": "weapon",
    "power": 36,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "military_case"
  },
  "phantom": {
    "name": "Фантом-СВД",
    "icon": "👻",
    "slot": "weapon",
    "power": 38,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "military_case"
  },
  "eclipse": {
    "name": "Затмение",
    "icon": "🌘",
    "slot": "weapon",
    "power": 39,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "relic_case"
  },
  "black_sun": {
    "name": "Чёрное солнце",
    "icon": "☀️",
    "slot": "weapon",
    "power": 41,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "relic_case"
  },
  "leviathan": {
    "name": "Левиафан-МК2",
    "icon": "🐉",
    "slot": "weapon",
    "power": 43,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "relic_case"
  },
  "last_word": {
    "name": "Последнее слово",
    "icon": "💀",
    "slot": "weapon",
    "power": 44,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "relic_case"
  }
}
NEW_RECIPES = {
  "pipe_rifle": {
    "qty": 1,
    "cost": {
      "metal": 15,
      "wood": 8,
      "wire": 4
    }
  },
  "nailgun": {
    "qty": 1,
    "cost": {
      "metal": 9,
      "wood": 5,
      "wire": 6
    }
  },
  "flare_gun": {
    "qty": 1,
    "cost": {
      "metal": 7,
      "rubber": 2,
      "wire": 3
    }
  },
  "coil_pistol": {
    "qty": 1,
    "cost": {
      "metal": 18,
      "wire": 16,
      "rubber": 6,
      "rare": 1
    }
  },
  "harpoon_gun": {
    "qty": 1,
    "cost": {
      "metal": 23,
      "wood": 10,
      "wire": 10,
      "rubber": 5
    }
  },
  "lever_rifle": {
    "qty": 1,
    "cost": {
      "metal": 30,
      "wood": 12,
      "wire": 9,
      "rubber": 5,
      "rare": 1
    }
  },
  "sawed_shotgun": {
    "qty": 1,
    "cost": {
      "metal": 17,
      "wood": 8,
      "rubber": 6
    }
  },
  "compound_bow": {
    "qty": 1,
    "cost": {
      "wood": 19,
      "wire": 14,
      "rubber": 8,
      "cloth": 8,
      "rare": 1
    }
  },
  "breacher": {
    "qty": 1,
    "cost": {
      "metal": 36,
      "wire": 16,
      "rubber": 13,
      "rare": 3
    }
  },
  "battle_rifle": {
    "qty": 1,
    "cost": {
      "metal": 43,
      "wire": 20,
      "rubber": 16,
      "rare": 4
    }
  },
  "patrol_coat": {
    "qty": 1,
    "cost": {
      "cloth": 12,
      "metal": 3,
      "rubber": 3
    }
  },
  "road_armor": {
    "qty": 1,
    "cost": {
      "cloth": 12,
      "metal": 16,
      "rubber": 7
    }
  },
  "plated_jacket": {
    "qty": 1,
    "cost": {
      "metal": 25,
      "cloth": 15,
      "rubber": 8
    }
  },
  "kevlar_mesh": {
    "qty": 1,
    "cost": {
      "cloth": 27,
      "metal": 20,
      "rubber": 13,
      "rare": 2
    }
  },
  "reactive_armor": {
    "qty": 1,
    "cost": {
      "metal": 42,
      "wire": 25,
      "rubber": 19,
      "rare": 4
    }
  },
  "scout_armor": {
    "qty": 1,
    "cost": {
      "cloth": 14,
      "wood": 4,
      "rubber": 11,
      "wire": 6
    }
  }
}
NEW_ITEM_DESCRIPTIONS = {
  "pipe_rifle": {
    "name": "Самодельная винтовка",
    "icon": "🔩",
    "type": "weapon",
    "power": 19,
    "desc": "Оружие: +19 урона"
  },
  "nailgun": {
    "name": "Гвоздомёт",
    "icon": "📌",
    "type": "weapon",
    "power": 16,
    "desc": "Оружие: +16 урона"
  },
  "flare_gun": {
    "name": "Сигнальный пистолет",
    "icon": "🔥",
    "type": "weapon",
    "power": 12,
    "desc": "Оружие: +12 урона"
  },
  "coil_pistol": {
    "name": "Катушечный пистолет",
    "icon": "⚡",
    "type": "weapon",
    "power": 23,
    "desc": "Оружие: +23 урона"
  },
  "harpoon_gun": {
    "name": "Гарпунная пушка",
    "icon": "🔱",
    "type": "weapon",
    "power": 25,
    "desc": "Оружие: +25 урона"
  },
  "lever_rifle": {
    "name": "Рычажная винтовка",
    "icon": "🎯",
    "type": "weapon",
    "power": 30,
    "desc": "Оружие: +30 урона"
  },
  "sawed_shotgun": {
    "name": "Обрез",
    "icon": "🔫",
    "type": "weapon",
    "power": 24,
    "desc": "Оружие: +24 урона"
  },
  "compound_bow": {
    "name": "Композитный лук",
    "icon": "🏹",
    "type": "weapon",
    "power": 28,
    "desc": "Оружие: +28 урона"
  },
  "breacher": {
    "name": "Штурмовой дробовик",
    "icon": "💥",
    "type": "weapon",
    "power": 34,
    "desc": "Оружие: +34 урона"
  },
  "battle_rifle": {
    "name": "Боевая винтовка",
    "icon": "🔫",
    "type": "weapon",
    "power": 37,
    "desc": "Оружие: +37 урона"
  },
  "patrol_coat": {
    "name": "Патрульный плащ",
    "icon": "🧥",
    "type": "armor",
    "power": 4,
    "desc": "Броня: +4 защиты"
  },
  "road_armor": {
    "name": "Броня дорожника",
    "icon": "🛡️",
    "type": "armor",
    "power": 7,
    "desc": "Броня: +7 защиты"
  },
  "plated_jacket": {
    "name": "Пластинчатая куртка",
    "icon": "🧥",
    "type": "armor",
    "power": 9,
    "desc": "Броня: +9 защиты"
  },
  "kevlar_mesh": {
    "name": "Кевларовая сетка",
    "icon": "🛡️",
    "type": "armor",
    "power": 11,
    "desc": "Броня: +11 защиты"
  },
  "reactive_armor": {
    "name": "Реактивный панцирь",
    "icon": "⚙️",
    "type": "armor",
    "power": 13,
    "desc": "Броня: +13 защиты"
  },
  "scout_armor": {
    "name": "Лёгкая броня разведчика",
    "icon": "🥷",
    "type": "armor",
    "power": 6,
    "desc": "Броня: +6 защиты"
  },
  "viper": {
    "name": "Гадюка-М",
    "icon": "🐍",
    "type": "weapon",
    "power": 23,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "ember": {
    "name": "Жар-пистолет",
    "icon": "🔥",
    "type": "weapon",
    "power": 26,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "thorn": {
    "name": "Шипомёт",
    "icon": "🌵",
    "type": "weapon",
    "power": 28,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "hunter_zero": {
    "name": "Охотник-0",
    "icon": "🎯",
    "type": "weapon",
    "power": 30,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "aegis": {
    "name": "Эгида-12",
    "icon": "🛡️",
    "type": "weapon",
    "power": 31,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "thunder": {
    "name": "Гром-9",
    "icon": "⚡",
    "type": "weapon",
    "power": 34,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "widow": {
    "name": "Чёрная вдова",
    "icon": "🕷️",
    "type": "weapon",
    "power": 36,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "phantom": {
    "name": "Фантом-СВД",
    "icon": "👻",
    "type": "weapon",
    "power": 38,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "eclipse": {
    "name": "Затмение",
    "icon": "🌘",
    "type": "weapon",
    "power": 39,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "black_sun": {
    "name": "Чёрное солнце",
    "icon": "☀️",
    "type": "weapon",
    "power": 41,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "leviathan": {
    "name": "Левиафан-МК2",
    "icon": "🐉",
    "type": "weapon",
    "power": 43,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  },
  "last_word": {
    "name": "Последнее слово",
    "icon": "💀",
    "type": "weapon",
    "power": 44,
    "desc": "Коллекционная пушка из кейса. Крафт недоступен."
  }
}
CASES = {
  "field_case": {
    "name": "Кейс разведчика",
    "icon": "📦",
    "tier": 1,
    "desc": "Одна из четырёх пушек серии разведчика. Не крафтится.",
    "rarity_weights": {
      "uncommon": 70,
      "rare": 27,
      "epic": 3
    }
  },
  "military_case": {
    "name": "Военный кейс",
    "icon": "🗃️",
    "tier": 3,
    "desc": "Одна из четырёх особых военных пушек. Не крафтится.",
    "rarity_weights": {
      "rare": 70,
      "epic": 27,
      "legendary": 3
    }
  },
  "relic_case": {
    "name": "Реликтовый кейс",
    "icon": "🔒",
    "tier": 5,
    "desc": "Одна из четырёх реликтовых пушек. Не крафтится.",
    "rarity_weights": {
      "epic": 85,
      "legendary": 15
    }
  }
}
# ZOMBO 0.34: four extra unique cases and 16 exclusive guns.
# These are deliberately absent from NEW_RECIPES; opening is the only normal source.
NEW_GEAR.update({
  "scrap_biter": {
    "name": "Байтер",
    "icon": "🔩",
    "slot": "weapon",
    "power": 20,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "scrap_case"
  },
  "scrap_fang": {
    "name": "Клык",
    "icon": "🪓",
    "slot": "weapon",
    "power": 22,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "scrap_case"
  },
  "scrap_grinder": {
    "name": "Гриндер",
    "icon": "⚙️",
    "slot": "weapon",
    "power": 24,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "scrap_case"
  },
  "scrap_howler": {
    "name": "Хаулер",
    "icon": "🔧",
    "slot": "weapon",
    "power": 25,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "scrap_case"
  },
  "hunter_foxeye": {
    "name": "Лисий глаз",
    "icon": "🎯",
    "slot": "weapon",
    "power": 26,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "hunter_case"
  },
  "hunter_nomad": {
    "name": "Номад",
    "icon": "🏹",
    "slot": "weapon",
    "power": 28,
    "defense": 0,
    "material": "wood",
    "exclusive": True,
    "case": "hunter_case"
  },
  "hunter_needle": {
    "name": "Игла",
    "icon": "📍",
    "slot": "weapon",
    "power": 29,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "hunter_case"
  },
  "hunter_trailbreaker": {
    "name": "Трейлбрейкер",
    "icon": "🦴",
    "slot": "weapon",
    "power": 31,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "hunter_case"
  },
  "assault_warden": {
    "name": "Варден",
    "icon": "🛡️",
    "slot": "weapon",
    "power": 35,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "assault_case"
  },
  "assault_crusher": {
    "name": "Крашер",
    "icon": "💥",
    "slot": "weapon",
    "power": 37,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "assault_case"
  },
  "assault_marauder": {
    "name": "Мародёр",
    "icon": "🔫",
    "slot": "weapon",
    "power": 39,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "assault_case"
  },
  "assault_bulldog": {
    "name": "Бульдог-X",
    "icon": "🐶",
    "slot": "weapon",
    "power": 41,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "assault_case"
  },
  "shadow_specter": {
    "name": "Спектер",
    "icon": "👁️",
    "slot": "weapon",
    "power": 40,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "shadow_case"
  },
  "shadow_nightfall": {
    "name": "Найтфолл",
    "icon": "🌒",
    "slot": "weapon",
    "power": 42,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "shadow_case"
  },
  "shadow_omen": {
    "name": "Омен",
    "icon": "☠️",
    "slot": "weapon",
    "power": 44,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "shadow_case"
  },
  "shadow_apex": {
    "name": "Апекс-0",
    "icon": "🦂",
    "slot": "weapon",
    "power": 46,
    "defense": 0,
    "material": "metal",
    "exclusive": True,
    "case": "shadow_case"
  }
})
NEW_ITEM_DESCRIPTIONS.update({
  "scrap_biter": {
    "name": "Байтер",
    "icon": "🔩",
    "type": "weapon",
    "power": 20,
    "desc": "Эксклюзивная пушка из кейса «Кейс мусорщика». Крафт невозможен."
  },
  "scrap_fang": {
    "name": "Клык",
    "icon": "🪓",
    "type": "weapon",
    "power": 22,
    "desc": "Эксклюзивная пушка из кейса «Кейс мусорщика». Крафт невозможен."
  },
  "scrap_grinder": {
    "name": "Гриндер",
    "icon": "⚙️",
    "type": "weapon",
    "power": 24,
    "desc": "Эксклюзивная пушка из кейса «Кейс мусорщика». Крафт невозможен."
  },
  "scrap_howler": {
    "name": "Хаулер",
    "icon": "🔧",
    "type": "weapon",
    "power": 25,
    "desc": "Эксклюзивная пушка из кейса «Кейс мусорщика». Крафт невозможен."
  },
  "hunter_foxeye": {
    "name": "Лисий глаз",
    "icon": "🎯",
    "type": "weapon",
    "power": 26,
    "desc": "Эксклюзивная пушка из кейса «Кейс следопыта». Крафт невозможен."
  },
  "hunter_nomad": {
    "name": "Номад",
    "icon": "🏹",
    "type": "weapon",
    "power": 28,
    "desc": "Эксклюзивная пушка из кейса «Кейс следопыта». Крафт невозможен."
  },
  "hunter_needle": {
    "name": "Игла",
    "icon": "📍",
    "type": "weapon",
    "power": 29,
    "desc": "Эксклюзивная пушка из кейса «Кейс следопыта». Крафт невозможен."
  },
  "hunter_trailbreaker": {
    "name": "Трейлбрейкер",
    "icon": "🦴",
    "type": "weapon",
    "power": 31,
    "desc": "Эксклюзивная пушка из кейса «Кейс следопыта». Крафт невозможен."
  },
  "assault_warden": {
    "name": "Варден",
    "icon": "🛡️",
    "type": "weapon",
    "power": 35,
    "desc": "Эксклюзивная пушка из кейса «Штурмовой кейс». Крафт невозможен."
  },
  "assault_crusher": {
    "name": "Крашер",
    "icon": "💥",
    "type": "weapon",
    "power": 37,
    "desc": "Эксклюзивная пушка из кейса «Штурмовой кейс». Крафт невозможен."
  },
  "assault_marauder": {
    "name": "Мародёр",
    "icon": "🔫",
    "type": "weapon",
    "power": 39,
    "desc": "Эксклюзивная пушка из кейса «Штурмовой кейс». Крафт невозможен."
  },
  "assault_bulldog": {
    "name": "Бульдог-X",
    "icon": "🐶",
    "type": "weapon",
    "power": 41,
    "desc": "Эксклюзивная пушка из кейса «Штурмовой кейс». Крафт невозможен."
  },
  "shadow_specter": {
    "name": "Спектер",
    "icon": "👁️",
    "type": "weapon",
    "power": 40,
    "desc": "Эксклюзивная пушка из кейса «Теневой кейс». Крафт невозможен."
  },
  "shadow_nightfall": {
    "name": "Найтфолл",
    "icon": "🌒",
    "type": "weapon",
    "power": 42,
    "desc": "Эксклюзивная пушка из кейса «Теневой кейс». Крафт невозможен."
  },
  "shadow_omen": {
    "name": "Омен",
    "icon": "☠️",
    "type": "weapon",
    "power": 44,
    "desc": "Эксклюзивная пушка из кейса «Теневой кейс». Крафт невозможен."
  },
  "shadow_apex": {
    "name": "Апекс-0",
    "icon": "🦂",
    "type": "weapon",
    "power": 46,
    "desc": "Эксклюзивная пушка из кейса «Теневой кейс». Крафт невозможен."
  }
})
CASES.update({
  "scrap_case": {
    "name": "Кейс мусорщика",
    "icon": "🧰",
    "tier": 1,
    "desc": "4 эксклюзивные самодельные пушки. Обычная 50% · необычная 40% · редкая 10%.",
    "rarity_weights": {
      "common": 50,
      "uncommon": 40,
      "rare": 10
    }
  },
  "hunter_case": {
    "name": "Кейс следопыта",
    "icon": "🎒",
    "tier": 2,
    "desc": "4 эксклюзивные пушки. Необычная 65% · редкая 30% · эпическая 5%.",
    "rarity_weights": {
      "uncommon": 65,
      "rare": 30,
      "epic": 5
    }
  },
  "assault_case": {
    "name": "Штурмовой кейс",
    "icon": "💣",
    "tier": 4,
    "desc": "4 эксклюзивные пушки. Редкая 82% · эпическая 17% · легендарная 1%.",
    "rarity_weights": {
      "rare": 82,
      "epic": 17,
      "legendary": 1
    }
  },
  "shadow_case": {
    "name": "Теневой кейс",
    "icon": "🌑",
    "tier": 6,
    "desc": "Эндгейм: 4 эксклюзивные пушки. Эпическая 90% · легендарная 10%.",
    "rarity_weights": {
      "epic": 90,
      "legendary": 10
    }
  }
})

# Balance older cases together with the four new ones. Every rarity pool sums
# to 100%; top-end cases remain earned in-game, never sold for caps.
CASES['field_case']['rarity_weights']={'uncommon':72,'rare':25,'epic':3}
CASES['military_case']['rarity_weights']={'rare':78,'epic':20,'legendary':2}
CASES['relic_case']['rarity_weights']={'epic':90,'legendary':10}

CASE_SHOP_PRICES = {
    'scrap_case':480,
    'field_case':650,
    'hunter_case':1750,
    'military_case':3000,
    'assault_case':5200,
}
# Deliberately no shop price for relic_case and shadow_case.

CASE_POOLS = {
    key:tuple(item_key for item_key,entry in NEW_GEAR.items()
              if entry.get('exclusive') and entry.get('case')==key)
    for key in CASES
}

# Percent chance per PvE victory, in order threat 1..5. Total is below 2%.
PVE_CASE_DROP = {
    'field_case':(.30,.42,.55,.65,.70),
    'scrap_case':(.15,.22,.25,.25,.28),
    'hunter_case':(0,.06,.14,.20,.24),
    'military_case':(0,0,.10,.23,.35),
    'assault_case':(0,0,0,.05,.15),
    'relic_case':(0,0,0,.02,.06),
    'shadow_case':(0,0,0,0,.02),
}

def case_drop_weights(threat):
    """No paid loot in free fights. Kept for legacy callers/tests."""
    return {key:0.0 for key in CASES}


RAID_CASE_CHANCE = {'outpost':.25,'vault':.45,'citadel':.65}
# Relative weights conditional on receiving a case at all.
RAID_CASE_WEIGHTS = {
    'outpost':{'field_case':50,'scrap_case':35,'hunter_case':15},
    'vault':{'hunter_case':35,'military_case':40,'assault_case':20,'relic_case':5},
    'citadel':{'military_case':15,'assault_case':25,
               'relic_case':35,'shadow_case':25},
}


def raid_case_drop(scenario,rng=None):
    """Paid cases are unavailable in raids as requested."""
    if scenario not in RAID_CASE_CHANCE:raise ValueError('Неизвестный рейд')
    return None


def validate_case_balance():
    """Fail fast on invalid content and probabilities before release."""
    if len(CASES)!=7 or len(CASE_POOLS)!=7:
        raise ValueError('Нужно ровно семь кейсов')
    if len({item for pool in CASE_POOLS.values() for item in pool})!=28:
        raise ValueError('28 уникальных пушек должны принадлежать одному кейсу')
    if any(len(pool)!=4 for pool in CASE_POOLS.values()):
        raise ValueError('В каждом кейсе должно быть четыре пушки')
    for key,meta in CASES.items():
        if sum(meta['rarity_weights'].values())!=100:
            raise ValueError(f'{key}: сумма редкостей не равна 100%')
        if key in NEW_RECIPES:
            raise ValueError('Кейс не должен крафтиться')
        for weapon in CASE_POOLS[key]:
            if weapon in NEW_RECIPES or not NEW_GEAR[weapon].get('exclusive'):
                raise ValueError(f'{weapon}: эксклюзив нельзя крафтить')
    for threat in range(1,6):
        odds=case_drop_weights(threat)
        if sum(odds.values())!=0:
            raise ValueError(f'Платные кейсы не должны выпадать в PvE ({threat})')
    for scenario,odds in RAID_CASE_WEIGHTS.items():
        if sum(odds.values())!=100 or any(key not in CASES for key in odds):
            raise ValueError(f'{scenario}: неверные веса кейсов')


validate_case_balance()
