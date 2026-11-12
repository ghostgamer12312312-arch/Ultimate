from __future__ import annotations

from types import SimpleNamespace

import handlers
import game


class FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class FakeUser:
    def __init__(self, uid: int, username: str = "hero") -> None:
        self.id = uid
        self.username = username
        self.first_name = "Hero"
        self.full_name = "Hero User"
        self.is_bot = False


class FakeMessage:
    def __init__(self, chat_id: int, text: str = "") -> None:
        self.chat_id = chat_id
        self.text = text
        self.chat = FakeChat(chat_id)
        self.reply_to_message = None

    async def reply_text(self, text: str, **kwargs):
        self.text = text
        return self

    async def edit_text(self, text: str, **kwargs):
        self.text = text
        return self


class FakeQuery:
    def __init__(self, user: FakeUser, message: FakeMessage, data: str) -> None:
        self.from_user = user
        self.message = message
        self.data = data
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text: str, **kwargs):
        self.message.text = text
        return self.message


class FakeBot:
    def __init__(self) -> None:
        self.messages = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.messages.append((chat_id, text))
        return FakeMessage(chat_id, text)

    async def send_document(self, **kwargs):
        self.messages.append(("document", kwargs))

    async def set_my_commands(self, *args, **kwargs):
        return None


class FakeUpdate:
    def __init__(self, user: FakeUser, chat_id: int | None = None) -> None:
        self.effective_user = user
        self.effective_chat = FakeChat(chat_id or user.id)
        self.effective_message = FakeMessage(chat_id or user.id)
        self.message = self.effective_message
        self.callback_query = None

    @classmethod
    def callback(cls, user: FakeUser, data: str):
        update = cls(user)
        update.callback_query = FakeQuery(user, update.effective_message, data)
        return update


class FakeContext:
    def __init__(self, db) -> None:
        self.bot_data = {"db": db}
        self.user_data = {}
        self.args = []
        self.bot = FakeBot()


async def test_start_and_register_flow(db):
    user = FakeUser(5001, "new_hero")
    ctx = FakeContext(db)
    update = FakeUpdate(user)
    await handlers.start(update, ctx)
    assert "Welcome" in update.effective_message.text

    await handlers.register_command(update, ctx)
    assert "Choose your race" in update.effective_message.text

    cb = FakeUpdate.callback(user, "reg:race:orc")
    await handlers.callback_router(cb, ctx)
    assert "Choose your class" in cb.effective_message.text

    cb2 = FakeUpdate.callback(user, "reg:class:berserker")
    await handlers.callback_router(cb2, ctx)
    player = await db.get_player(5001)
    assert player is not None
    assert player["race"] == "orc" and player["class"] == "berserker"
    assert "Character created" in cb2.effective_message.text


async def test_profile_and_hunt_actions(db, player):
    user = FakeUser(player["user_id"], "hero_one")
    ctx = FakeContext(db)
    update = FakeUpdate(user)

    await handlers.profile_command(update, ctx)
    assert "Hero One" in update.effective_message.text

    await handlers.hunt_command(update, ctx)
    assert "Hunting Grounds" in update.effective_message.text

    start = FakeUpdate.callback(user, "hunt:start:forest_slime")
    await handlers.callback_router(start, ctx)
    assert "Battle vs" in start.effective_message.text
    assert player["user_id"] in ctx.bot_data["hunts"]

    action = start
    for _ in range(10):
        if player["user_id"] not in ctx.bot_data["hunts"]:
            break
        action = FakeUpdate.callback(user, "battle:attack")
        await handlers.callback_router(action, ctx)
    assert player["user_id"] not in ctx.bot_data["hunts"]
    assert any(word in action.effective_message.text for word in ("Victory", "Defeat", "Escaped"))


async def test_daily_and_inventory_callbacks(db, player):
    user = FakeUser(player["user_id"], "hero_one")
    ctx = FakeContext(db)

    daily = FakeUpdate.callback(user, "daily:claim")
    await handlers.callback_router(daily, ctx)
    assert "Daily reward claimed" in daily.effective_message.text
    assert daily.callback_query.answered

    inv = FakeUpdate.callback(user, "menu:inventory")
    await handlers.callback_router(inv, ctx)
    assert "Inventory" in inv.effective_message.text

    use = FakeUpdate.callback(user, "inv:use:small_potion")
    await handlers.callback_router(use, ctx)
    # Already at full HP, so the potion must not be consumed.
    assert await db.get_item_quantity(player["user_id"], "small_potion") == 1

    await db.add_item(player["user_id"], "iron_sword", 1)
    equip = FakeUpdate.callback(user, "inv:equip:iron_sword")
    await handlers.callback_router(equip, ctx)
    assert (await db.get_equipment(player["user_id"])).get("weapon") == "iron_sword"
    assert await db.get_item_quantity(player["user_id"], "wooden_sword") == 1


async def test_clan_menu_callback(db, strong_player):
    user = FakeUser(strong_player["user_id"], "champion")
    ctx = FakeContext(db)
    update = FakeUpdate.callback(user, "menu:clan")
    await handlers.callback_router(update, ctx)
    assert "not in a clan" in update.effective_message.text


async def test_leaderboard_callback(db, player):
    user = FakeUser(player["user_id"], "hero_one")
    ctx = FakeContext(db)
    update = FakeUpdate.callback(user, "lb:level")
    await handlers.callback_router(update, ctx)
    assert "Top Heroes" in update.effective_message.text
