from functools import wraps
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, filters

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
        bot.add_handler(MessageHandler(
            filters.Chat([config.source.get_id() for config in new_config])
            & ~filters.COMMAND
            & ~filters.StatusUpdate.ALL,
            forwarder,
        ))

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid chat ID.")


ADD_ADMIN_HANDLER = CommandHandler("addadmin", add_admin)
DEL_ADMIN_HANDLER = CommandHandler("deladmin", del_admin)
ADD_FORWARD_HANDLER = CommandHandler("addforward", add_forward)
DEL_FORWARD_HANDLER = CommandHandler("delforward", del_forward)

bot.add_handler(ADD_ADMIN_HANDLER)
bot.add_handler(DEL_ADMIN_HANDLER)
bot.add_handler(ADD_FORWARD_HANDLER)
bot.add_handler(DEL_FORWARD_HANDLER)
