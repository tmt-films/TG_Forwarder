from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
)

from forwarder import bot, OWNER_ID
from forwarder.config import ADMINS
from forwarder.modules.forward import FORWARD_HANDLER, forwarder
from forwarder.utils.chat import get_config, save_config, ForwardConfig, PARSED_CONFIG


def owner_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != OWNER_ID:
            await update.message.reply_text("You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


@owner_only
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide a user ID.")
        return
    try:
        user_id = int(context.args[0])
        if user_id in ADMINS:
            await update.message.reply_text("This user is already an admin.")
            return
        ADMINS.append(user_id)
        await update.message.reply_text(f"User {user_id} has been added to the admin list.")
    except (IndexError, ValueError):
        await update.message.reply_text("Invalid user ID.")


@owner_only
async def del_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide a user ID.")
        return
    try:
        user_id = int(context.args[0])
        if user_id not in ADMINS:
            await update.message.reply_text("This user is not an admin.")
            return
        ADMINS.remove(user_id)
        await update.message.reply_text(f"User {user_id} has been removed from the admin list.")
    except (IndexError, ValueError):
        await update.message.reply_text("Invalid user ID.")


def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMINS:
            await update.message.reply_text("You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


@admin_only
async def add_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "Invalid format. Use: /addforward <source_id> <destination_id>"
        )
        return
    try:
        source_id = context.args[0]
        dest_id = context.args[1]

        config = get_config()

        # Check if the source already exists
        for forward_config in config:
            if forward_config.source.__repr__() == source_id:
                forward_config.destination.append(dest_id)
                break
        else:
            # If source doesn't exist, create a new ForwardConfig
            new_config = ForwardConfig(source_id, [dest_id])
            config.append(new_config)

        save_config(config)
        await update.message.reply_text(f"Forward rule from {source_id} to {dest_id} has been added.")

        # Reload the forwarder
        bot.remove_handler(FORWARD_HANDLER)
        PARSED_CONFIG.clear()
        new_config = get_config()
        from telegram.ext import MessageHandler
        bot.add_handler(MessageHandler(
            filters.Chat([config.source.get_id() for config in new_config])
            & ~filters.COMMAND
            & ~filters.StatusUpdate.ALL,
            forwarder,
        ))

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid chat ID.")


@admin_only
async def del_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "Invalid format. Use: /delforward <source_id> <destination_id>"
        )
        return
    try:
        source_id = context.args[0]
        dest_id = context.args[1]

        config = get_config()

        for forward_config in config:
            if forward_config.source.__repr__() == source_id:
                for destination in forward_config.destination:
                    if destination.__repr__() == dest_id:
                        forward_config.destination.remove(destination)
                        if not forward_config.destination:
                            config.remove(forward_config)
                        break
                break

        save_config(config)
        await update.message.reply_text(f"Forward rule from {source_id} to {dest_id} has been deleted.")

        # Reload the forwarder
        bot.remove_handler(FORWARD_HANDLER)
        PARSED_CONFIG.clear()
        new_config = get_config()
        from telegram.ext import MessageHandler
        bot.add_handler(MessageHandler(
            filters.Chat([config.source.get_id() for config in new_config])
            & ~filters.COMMAND
            & ~filters.StatusUpdate.ALL,
            forwarder,
        ))

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid chat ID.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Add Forward", callback_data="add_forward")],
        [InlineKeyboardButton("Delete Forward", callback_data="del_forward")],
        [InlineKeyboardButton("List Forwards", callback_data="list_forwards")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose an option:", reply_markup=reply_markup)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "add_forward":
        await query.message.reply_text("Please send me the source chat ID.")
        return 1
    elif query.data == "del_forward":
        await query.message.reply_text("Please send me the source chat ID of the forward rule to delete.")
        return 3
    elif query.data == "list_forwards":
        config = get_config()
        if not config:
            await query.message.reply_text("No forwarding rules have been set.")
            return ConversationHandler.END

        message = "Here are the current forwarding rules:\n\n"
        for forward_config in config:
            message += f"Source: {forward_config.source.__repr__()}\n"
            message += "Destinations:\n"
            for dest in forward_config.destination:
                message += f"- {dest.__repr__()}\n"
            message += "\n"

        await query.message.reply_text(message)
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


async def get_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["source_id"] = [
        item.strip() for item in update.message.text.split(",")
    ]
    await update.message.reply_text(
        "Please send me the destination chat IDs, separated by commas."
    )
    return 2


async def get_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["dest_id"] = [
        item.strip() for item in update.message.text.split(",")
    ]
    await update.message.reply_text("Do you want to add any filters? (yes/no)")
    return 5


async def get_source_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["source_id_to_delete"] = [
        item.strip() for item in update.message.text.split(",")
    ]
    await update.message.reply_text(
        "Please send me the destination chat IDs to delete, separated by commas."
    )
    return 4


async def get_destination_to_delete(update: Update, context: ContextTypes.DEFAULT_T) -> int:
    context.user_data["dest_id_to_delete"] = [
        item.strip() for item in update.message.text.split(",")
    ]

    source_ids = context.user_data["source_id_to_delete"]
    dest_ids = context.user_data["dest_id_to_delete"]

    config = get_config()

    for source_id in source_ids:
        for forward_config in config:
            if forward_config.source.__repr__() == source_id:
                for dest_id in dest_ids:
                    for destination in forward_config.destination:
                        if destination.__repr__() == dest_id:
                            forward_config.destination.remove(destination)
                if not forward_config.destination:
                    config.remove(forward_config)
                break

    save_config(config)
    await update.message.reply_text(f"Forward rule from {source_id} to {dest_id} has been deleted.")

    # Reload the forwarder
    bot.remove_handler(FORWARD_HANDLER)
    PARSED_CONFIG.clear()
    new_config = get_config()
    bot.add_handler(MessageHandler(
        filters.Chat([config.source.get_id() for config in new_config])
        & ~filters.COMMAND
        & ~filters.StatusUpdate.ALL,
        forwarder,
    ))

    return ConversationHandler.END


ADD_ADMIN_HANDLER = CommandHandler("addadmin", add_admin)
DEL_ADMIN_HANDLER = CommandHandler("deladmin", del_admin)
ADD_FORWARD_HANDLER = CommandHandler("addforward", add_forward)
DEL_FORWARD_HANDLER = CommandHandler("delforward", del_forward)
START_HANDLER = CommandHandler("start", start)

async def get_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.lower()
    if text == "yes":
        await update.message.reply_text(
            "Please send me the filters, separated by commas."
        )
        return 6
    else:
        context.user_data["filters"] = None
        await update.message.reply_text(
            "Do you want to add a blacklist? (yes/no)"
        )
        return 7


async def get_blacklist_question(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data["filters"] = [
        item.strip() for item in update.message.text.split(",")
    ]
    await update.message.reply_text("Do you want to add a blacklist? (yes/no)")
    return 7


async def get_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.lower()
    if text == "yes":
        await update.message.reply_text(
            "Please send me the blacklist, separated by commas."
        )
        return 8
    else:
        context.user_data["blacklist"] = None
        await save_forward_rule(update, context)
        return ConversationHandler.END


async def save_forward_rule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    source_id = context.user_data["source_id"]
    dest_id = context.user_data["dest_id"]
    filters = context.user_data["filters"]
    blacklist = context.user_data["blacklist"]

    config = get_config()

    # Check if the source already exists
    for forward_config in config:
        if forward_config.source.__repr__() == source_id:
            forward_config.destination.append(dest_id)
            if filters:
                if forward_config.filters:
                    forward_config.filters.extend(filters)
                else:
                    forward_config.filters = filters
            if blacklist:
                if forward_config.blacklist:
                    forward_config.blacklist.extend(blacklist)
                else:
                    forward_config.blacklist = blacklist
            break
    else:
        # If source doesn't exist, create a new ForwardConfig
        new_config = ForwardConfig(source_id, [dest_id], filters, blacklist)
        config.append(new_config)

    save_config(config)
    await update.message.reply_text(f"Forward rule from {source_id} to {dest_id} has been added.")

    # Reload the forwarder
    bot.remove_handler(FORWARD_HANDLER)
    PARSED_CONFIG.clear()
    new_config = get_config()
    from telegram.ext import MessageHandler
    bot.add_handler(MessageHandler(
        filters.Chat([config.source.get_id() for config in new_config])
        & ~filters.COMMAND
        & ~filters.StatusUpdate.ALL,
        forwarder,
    ))


CONVERSATION_HANDLER = ConversationHandler(
    entry_points=[CallbackQueryHandler(button)],
    states={
        1: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_source)],
        2: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_destination)],
        3: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_source_to_delete)],
        4: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_destination_to_delete)],
        5: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_filters)],
        6: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_blacklist_question)],
        7: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_blacklist)],
        8: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_forward_rule)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

bot.add_handler(ADD_ADMIN_HANDLER)
bot.add_handler(DEL_ADMIN_HANDLER)
bot.add_handler(ADD_FORWARD_HANDLER)
bot.add_handler(DEL_FORWARD_HANDLER)
bot.add_handler(START_HANDLER)
bot.add_handler(CONVERSATION_HANDLER)
