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
CASE_POOLS = {
    key:tuple(item_key for item_key,entry in NEW_GEAR.items()
              if entry.get('exclusive') and entry.get('case')==key)
    for key in CASES
}

def case_drop_weights(threat):
    """Percentages per won PvE fight: max combined chance at tier 5 < 2%."""
    threat=max(1,min(5,int(threat)))
    return {
        'field_case':(.25,.40,.65,.90,1.20)[threat-1],
        'military_case':(0,0,.15,.30,.50)[threat-1],
        'relic_case':(0,0,0,0,.08)[threat-1],
    }
