import json, random, re, sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

# -------------------------
# Dice & utility
# -------------------------
def d(n=20) -> int:
    return random.randint(1, n)

def check(mod: int = 0, dc: int = 12) -> Dict[str, int]:
    roll = d(20)
    total = roll + mod
    return {"roll": roll, "total": total, "dc": dc, "success": total >= dc}

def pick(seq): return random.choice(seq)

# -------------------------
# Data models
# -------------------------
STATS = ["STR", "DEX", "INT", "CHA"]

@dataclass
class Character:
    name: str
    stats: Dict[str, int]  # modifiers, e.g., {"STR":2, "DEX":1, "INT":0, "CHA":1}
    hp: int = 12
    inventory: List[str] = field(default_factory=list)

@dataclass
class NPC:
    name: str
    role: str
    mood: str
    helpful: int = 0  # -2..+2
    alive: bool = True

@dataclass
class Location:
    name: str
    tags: List[str]
    discovered: bool = True
    npcs: List[NPC] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    exits: Dict[str, str] = field(default_factory=dict)  # direction -> location name
    description: str = ""

@dataclass
class Quest:
    title: str
    giver: str
    target: str
    place: str
    completed: bool = False
    reward: str = "50 gold"

@dataclass
class GameState:
    hero: Character
    locations: Dict[str, Location]
    world_time: int = 0
    current: str = "Town Square"
    quest: Optional[Quest] = None
    log: List[str] = field(default_factory=list)

# -------------------------
# Procedural content
# -------------------------
TOWN_NAMES = ["Town Square", "Old Docks", "Market Row", "Temple Yard", "Guild Alley"]
WILD_NAMES = ["Whispering Woods", "Sunless Grotto", "Riven Fields", "Ashen Ruins"]

ROLES = ["merchant", "guard", "priest", "thief", "scholar", "ranger"]
MOODS = ["wary", "cheerful", "stern", "anxious", "curious", "gruff"]
ITEMS = ["rope", "lockpick", "healing herb", "torch", "rusty dagger", "ancient coin"]

def gen_npc() -> NPC:
    return NPC(
        name=pick(["Ayla","Brann","Caro","Deka","Eldin","Faye","Garron","Hale","Iris","Jaro"]),
        role=pick(ROLES),
        mood=pick(MOODS),
        helpful=random.randint(-1,1)
    )

def gen_location(name: str, is_town=True) -> Location:
    tags = ["town"] if is_town else ["wild"]
    npcs = [gen_npc() for _ in range(random.randint(1, 2 if is_town else 1))]
    items = [pick(ITEMS)] if random.random() < 0.5 else []
    desc = f"{name}: a {'bustling' if is_town else 'lonely'} place with {pick(['murmurs','shadows','footsteps','distant bells','rustling leaves'])}."
    return Location(name=name, tags=tags, npcs=npcs, items=items, description=desc)

def gen_world() -> Dict[str, Location]:
    locs = {}
    for n in TOWN_NAMES: locs[n] = gen_location(n, is_town=True)
    for n in WILD_NAMES: locs[n] = gen_location(n, is_town=False)
    # Simple network
    locs["Town Square"].exits = {"north":"Market Row","east":"Guild Alley","south":"Old Docks","west":"Temple Yard"}
    locs["Market Row"].exits = {"south":"Town Square","east":"Riven Fields"}
    locs["Guild Alley"].exits = {"west":"Town Square","north":"Temple Yard","east":"Whispering Woods"}
    locs["Old Docks"].exits = {"north":"Town Square","east":"Sunless Grotto"}
    locs["Temple Yard"].exits = {"east":"Town Square","north":"Ashen Ruins"}
    # Ensure target wilds are reachable
    for wild in ["Whispering Woods","Sunless Grotto","Riven Fields","Ashen Ruins"]:
        locs[wild].exits.setdefault("back","Town Square")
    return locs

def gen_quest(state: GameState) -> Quest:
    giver_loc = state.current
    giver = pick([npc.name for npc in state.locations[giver_loc].npcs]) if state.locations[giver_loc].npcs else "A stranger"
    target = pick(["a stolen reliquary","the bandit chief","a lost child","a cursed idol","a map fragment"])
    place = pick(WILD_NAMES)
    reward = pick(["50 gold","a silver ring","a minor spell","local favors","a healing draught"])
    title = f"{pick(['Shadows of','Echoes of','Whispers in','Trouble at'])} {place}"
    return Quest(title=title, giver=giver, target=target, place=place, completed=False, reward=reward)

# -------------------------
# DM text (replaceable with LLM)
# -------------------------
def dm_narrate(state: GameState, prompt: str) -> str:
    """
    CURRENT: lightweight, deterministic-ish narration using simple rules.
    FUTURE: plug your LLM call here (see bottom).
    """
    loc = state.locations[state.current]
    base = f"\n[{state.current}] {loc.description}\n"
    npcs = ", ".join([f"{n.name} ({n.role}, {n.mood})" for n in loc.npcs]) or "no one obvious"
    items = ", ".join(loc.items) if loc.items else "nothing of note"
    exits = ", ".join([f"{d}->{name}" for d, name in loc.exits.items()]) or "nowhere"
    flavor = pick([
        "A gull cries overhead.",
        "You smell damp stone.",
        "A breeze carries hushed voices.",
        "Bootsteps fade into an alley.",
        "Lantern light flickers."
    ])
    return base + f"Here you notice {items}. You can go: {exits}. You see {npcs}. {flavor}"

def dm_outcome(text: str) -> None:
    print(text)

# -------------------------
# Command parsing
# -------------------------
INTENTS = {
    "move": r"\b(go|walk|run|move|head)\b\s*(north|south|east|west|back)?",
    "talk": r"\b(talk|speak|chat)\b\s*(to|with)?\s*(?P<name>\w+)?",
    "attack": r"\b(attack|fight|strike|hit)\b\s*(?P<name>\w+)?",
    "look": r"\b(look|observe|inspect|examine)\b",
    "take": r"\b(take|grab|pick)\b\s*(?P<item>[\w\s]+)?",
    "use": r"\b(use|apply)\b\s*(?P<item>[\w\s]+)?",
    "inventory": r"\b(inv|inventory|bag|pack)\b",
    "quest": r"\b(quest|mission|task)\b",
    "save": r"\b(save)\b(\s+(?P<slot>\w+))?",
    "load": r"\b(load)\b(\s+(?P<slot>\w+))?",
    "help": r"\b(help|\?)\b",
}

def parse_intent(text: str):
    t = text.strip().lower()
    for intent, pattern in INTENTS.items():
        m = re.search(pattern, t)
        if m: return intent, {k:v for k,v in m.groupdict().items() if v}
    # Fallback simple verbs
    if t in ["n","s","e","w","north","south","east","west","back"]:
        return "move", {"direction":t}
    return "unknown", {"raw": text}

# -------------------------
# Engine actions
# -------------------------
def do_move(state: GameState, args):
    dir_ = args.get("direction") or (args.get(0) if isinstance(args.get(0), str) else None)
    if not dir_:
        m = re.search(INTENTS["move"], args.get("raw",""))
        dir_ = (m.group(2) if m else None)
    if not dir_:
        return "Where do you go? (north/south/east/west/back)"

    dir_ = {"n":"north","s":"south","e":"east","w":"west"}.get(dir_, dir_)
    here = state.locations[state.current]
    if dir_ not in here.exits:
        return f"You can't go {dir_} from here."
    state.current = here.exits[dir_]
    state.world_time += 1
    return dm_narrate(state, "arrive")

def do_talk(state: GameState, args):
    name = args.get("name")
    loc = state.locations[state.current]
    if not loc.npcs:
        return "No one seems keen to chat."
    target = None
    if name:
        for n in loc.npcs:
            if n.name.lower().startswith(name.lower()):
                target = n; break
    target = target or pick(loc.npcs)
    # Dialogue check
    mod = state.hero.stats.get("CHA",0) + target.helpful
    result = check(mod=mod, dc=12)
    if result["success"]:
        if state.quest is None and random.random() < 0.6:
            state.quest = gen_quest(state)
            return (f"{target.name} leans in and shares a lead: **{state.quest.title}**.\n"
                    f"Find {state.quest.target} in **{state.quest.place}**. Reward: {state.quest.reward}.")
        return f"{target.name} ({target.role}) chats warmly about local rumors. (CHA check {result['total']} vs DC {result['dc']})"
    else:
        return f"{target.name} seems {target.mood} and gives curt replies. (CHA check {result['total']} vs DC {result['dc']})"

def do_look(state: GameState, _):
    return dm_narrate(state, "look")

def do_take(state: GameState, args):
    item = args.get("item")
    loc = state.locations[state.current]
    if not item:
        if not loc.items: return "There’s nothing to take."
        item = loc.items[0]
    # fuzzy match
    cand = None
    for it in list(loc.items):
        if it.lower().startswith(item.lower()):
            cand = it; break
    if not cand: return f"You don't see '{item}'."
    state.hero.inventory.append(cand)
    loc.items.remove(cand)
    return f"You take the {cand}."

def do_use(state: GameState, args):
    item = args.get("item")
    if not item: return "Use what?"
    # fuzzy in inventory
    inv = state.hero.inventory
    cand = None
    for it in inv:
        if it.lower().startswith(item.lower()):
            cand = it; break
    if not cand: return f"You don’t have '{item}'."
    if "herb" in cand:
        healed = random.randint(3,6)
        state.hero.hp = min(state.hero.hp + healed, 12)
        inv.remove(cand)
        return f"You chew the healing herb and recover {healed} HP. (HP={state.hero.hp})"
    return f"You fiddle with the {cand}. Nothing dramatic happens."

def do_attack(state: GameState, args):
    name = args.get("name")
    loc = state.locations[state.current]
    if not loc.npcs: return "There’s no one to attack."
    target = None
    if name:
        for n in loc.npcs:
            if n.name.lower().startswith(name.lower()):
                target = n; break
    target = target or pick(loc.npcs)
    if not target.alive: return f"{target.name} is already down."
    atk = check(mod=state.hero.stats.get("STR",0), dc=12)
    if not atk["success"]:
        return f"You swing at {target.name} and miss! (Roll {atk['total']} vs DC {atk['dc']})"
    dmg = random.randint(2,6) + max(0, state.hero.stats.get("STR",0))
    # Simplified: one good hit downs an NPC
    target.alive = False
    # Quest resolution hook
    quest_text = ""
    if state.quest and state.quest.place == state.current and target.name in state.quest.title:
        state.quest.completed = True
        quest_text = f"\nThis finishes **{state.quest.title}**! Claim {state.quest.reward} in town."
    loc.npcs = [n for n in loc.npcs if n.alive]
    return f"You strike {target.name} for {dmg}. They fall.{quest_text}"

def do_inventory(state: GameState, _):
    inv = ", ".join(state.hero.inventory) if state.hero.inventory else "(empty)"
    return f"HP: {state.hero.hp}\nInventory: {inv}\nStats: {state.hero.stats}"

def do_quest(state: GameState, _):
    if not state.quest:
        return "No active quest. Talk to folks for leads."
    q = state.quest
    status = "COMPLETED" if q.completed else "ACTIVE"
    return f"[{status}] {q.title}\nFind {q.target} in {q.place}. Reward: {q.reward}."

def do_save(state: GameState, args):
    slot = args.get("slot","slot1")
    with open(f"{slot}.json","w",encoding="utf-8") as f:
        json.dump(serialize_state(state), f, indent=2)
    return f"Saved game to {slot}.json"

def do_load(args) -> Optional[GameState]:
    slot = args.get("slot","slot1")
    try:
        with open(f"{slot}.json","r",encoding="utf-8") as f:
            data = json.load(f)
        return deserialize_state(data)
    except FileNotFoundError:
        print("No such save slot.")
        return None

# -------------------------
# Serialization
# -------------------------
def serialize_state(state: GameState) -> Dict:
    def loc_to_dict(l: Location):
        return {
            "name": l.name, "tags": l.tags, "discovered": l.discovered, "items": l.items,
            "exits": l.exits, "description": l.description,
            "npcs": [asdict(n) for n in l.npcs]
        }
    return {
        "hero": asdict(state.hero),
        "locations": {k: loc_to_dict(v) for k,v in state.locations.items()},
        "world_time": state.world_time,
        "current": state.current,
        "quest": asdict(state.quest) if state.quest else None,
        "log": state.log,
    }

def deserialize_state(data: Dict) -> GameState:
    hero = Character(**data["hero"])
    locs = {}
    for k, v in data["locations"].items():
        npcs = [NPC(**n) for n in v["npcs"]]
        locs[k] = Location(
            name=v["name"], tags=v["tags"], discovered=v["discovered"], npcs=npcs,
            items=v["items"], exits=v["exits"], description=v["description"]
        )
    quest = Quest(**data["quest"]) if data["quest"] else None
    return GameState(hero=hero, locations=locs, world_time=data["world_time"],
                     current=data["current"], quest=quest, log=data["log"])

# -------------------------
# Main loop
# -------------------------
ACTIONS = {
    "move": do_move,
    "talk": do_talk,
    "attack": do_attack,
    "look": do_look,
    "take": do_take,
    "use": do_use,
    "inventory": do_inventory,
    "quest": do_quest,
    "save": do_save,
}

HELP = """
Commands:
  look | go <dir> | north/south/east/west/back
  talk [name] | attack [name]
  take [item] | use [item]
  inventory | quest
  save [slot] | load [slot]
  help | quit
"""

def new_game() -> GameState:
    hero = Character(
        name="Hero",
        stats={"STR":2, "DEX":1, "INT":0, "CHA":1},
        hp=12,
        inventory=["torch"]
    )
    locs = gen_world()
    gs = GameState(hero=hero, locations=locs, current="Town Square")
    gs.log.append("You arrive in the Town Square, seeking fortune.")
    return gs

def main():
    random.seed()  # remove or set a number for reproducibility
    state = new_game()
    print("=== AI Dungeon Master (Python) ===")
    print("Type 'help' for commands.\n")
    dm_outcome(dm_narrate(state, "start"))

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye."); break

        if not raw: continue
        if raw.lower() in ["quit","exit"]: print("Farewell."); break
        if raw.lower().startswith("load"):
            _, args = parse_intent(raw)
            new_state = do_load(args)
            if new_state: state = new_state; dm_outcome("Loaded."); dm_outcome(dm_narrate(state,"after load"))
            continue
        if raw.lower() in ["help","?"]:
            print(HELP); continue

        intent, args = parse_intent(raw)
        if intent in ACTIONS:
            out = ACTIONS[intent](state, args)
            dm_outcome(out)
        elif intent == "unknown":
            # Fallback: treat as "talk" or "look" with DM riff
            if len(raw.split()) <= 2:
                dm_outcome(dm_narrate(state, raw))
            else:
                # freeform attempt -> CHA/INT check to glean something
                mod = max(state.hero.stats.get("CHA",0), state.hero.stats.get("INT",0))
                res = check(mod=mod, dc=13)
                if res["success"]:
                    dm_outcome("You read the room and glean a hint: try 'quest' or 'go north/east/etc.'")
                else:
                    dm_outcome("Your words scatter into the noise of the crowd.")
        else:
            dm_outcome("…The DM blinks. (Unknown action)")

if __name__ == "__main__":
    main()
