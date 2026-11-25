"""Telegram CHARBON TEST MVP. Does not touch the official channel.

Single worker with a persistent SQLite volume. Uses Telegram long polling only when
Make's webhook is no longer attached to the bot.
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import (Application, ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler, filters)

from config import Settings
from content import COACH_RULES, POST_RULES, THEMES
from storage import Store

PARIS = ZoneInfo('Europe/Paris')
LOG = logging.getLogger('charbon_test')


def local_now() -> datetime:
    return datetime.now(PARIS)


def buttons(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Approuver', callback_data=f'post:{post_id}:approve'),
         InlineKeyboardButton('✏️ Modifier', callback_data=f'post:{post_id}:edit')],
        [InlineKeyboardButton('❌ Refuser', callback_data=f'post:{post_id}:reject')],
    ])


def settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data['settings']


def store(context: ContextTypes.DEFAULT_TYPE) -> Store:
    return context.application.bot_data['store']


async def owner_notice(context: ContextTypes.DEFAULT_TYPE, message: str):
    await context.bot.send_message(chat_id=settings(context).owner_id, text=message)


async def generate_text(context: ContextTypes.DEFAULT_TYPE, day: datetime):
    cfg = settings(context)
    if not cfg.openai_key:
        raise RuntimeError('OPENAI_API_KEY absente : aucune génération IA possible')
    client = AsyncOpenAI(api_key=cfg.openai_key, timeout=45.0)
    recent = '\n---\n'.join(store(context).recent_bodies())
    response = await client.responses.create(
        model=cfg.openai_model,
        instructions=POST_RULES,
        input=(f'Date : {day.date().isoformat()}. Thème : {THEMES[day.weekday()]}.\n'
               f'Évite de répéter ces anciennes publications :\n{recent[:1600]}'),
        max_output_tokens=550,
        store=False,
    )
    body = (response.output_text or '').strip()
    if not 80 <= len(body) <= 3200:
        raise RuntimeError('La réponse IA est vide ou de longueur anormale')
    return body


async def send_preview(context: ContextTypes.DEFAULT_TYPE, post: dict):
    msg = await context.bot.send_message(
        chat_id=settings(context).owner_id,
        text=(f'📝 CHARBON TEST — {post["local_day"]}\n'
              'Projet de publication prévu à 10 h.\n\n'
              f'{post["body"]}\n\n'
              '⚠️ Sans ton approbation avant 10 h, rien ne sera publié.'),
        reply_markup=buttons(post['id']),
    )
    store(context).mark_preview(post['id'], msg.message_id)


async def prepare_post(context: ContextTypes.DEFAULT_TYPE):
    now = local_now()
    day = now.date().isoformat()
    if existing := find_today(store(context), day):
        LOG.info('Publication de %s déjà préparée (%s)', day, existing['status'])
        return
    try:
        body = await generate_text(context, now)
        post, created = store(context).create_post(day, body)
        if created:
            await send_preview(context, post)
    except Exception:
        LOG.exception('Daily preparation failed')
        await owner_notice(context, '⚠️ CHARBON TEST : génération à 9 h échouée. Aucune publication automatique.')


def find_today(db: Store, day: str):
    # Only a few entries need checking; SQLite uniqueness is the final protection.
    with db._db() as con:
        row = con.execute('SELECT * FROM posts WHERE local_day=?', (day,)).fetchone()
        return dict(row) if row else None


async def publish_post(context: ContextTypes.DEFAULT_TYPE):
    now = local_now()
    day = now.date().isoformat()
    db = store(context)
    db.expire_unapproved(day)
    # Never publish late after downtime, manual run, or clock drift.
    if now.hour != 10 or now.minute > 1:
        LOG.warning('Publication ignored outside 10:00–10:01 Europe/Paris')
        return
    cfg = settings(context)
    if not cfg.publishing_enabled:
        candidate = find_today(db, day)
        if candidate and candidate['status'] == 'approved':
            await owner_notice(context, '🔒 CHARBON TEST : publication approuvée non envoyée (ENABLE_PUBLISH=false).')
        return
    post = db.claim_publication(day)
    if post is None:
        LOG.info('Nothing approved to publish for %s', day)
        return
    try:
        result = await context.bot.send_message(chat_id=cfg.channel_id, text=post['body'])
    except Exception:
        db.finish_publication(post['id'], None)
        LOG.exception('Publication send outcome may be uncertain; held for manual review')
        await owner_notice(context, '⚠️ CHARBON TEST : envoi incertain/échoué. Aucun nouvel essai automatique pour éviter les doublons.')
    else:
        db.finish_publication(post['id'], result.message_id)
        await owner_notice(context, '✅ CHARBON TEST : publication envoyée à 10 h.')


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = settings(context)
    if not update.effective_user or not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return
    if update.effective_user.id == cfg.owner_id:
        await update.message.reply_text('CHARBON TEST prêt. /preview pour tester les boutons, /generate pour tester l’IA, /status pour voir le brouillon.')
    elif cfg.assistant_enabled:
        await update.message.reply_text('Salut ! Je suis l’assistant IA Charbon, pas le créateur du canal. Tu peux m’écrire pour parler discipline, sport ou objectifs.')
    else:
        await update.message.reply_text('L’assistant Charbon est encore en test et n’est pas ouvert au public.')


async def preview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_private(update, settings(context)):
        return
    day = local_now().date().isoformat()
    post, _ = store(context).create_post(day, 'TEST UNIQUEMENT — Ne pas publier.\n\nAujourd’hui, avance sur un objectif concret pendant 20 minutes.')
    await send_preview(context, post)


async def generate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_private(update, settings(context)):
        return
    await prepare_post(context)
    await update.message.reply_text('Commande traitée. Vérifie le brouillon privé ci-dessus ou /status.')


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_private(update, settings(context)):
        return
    post = find_today(store(context), local_now().date().isoformat())
    await update.message.reply_text(f'Charbon TEST — {post["status"] if post else "aucun brouillon"}. Publication autorisée : {settings(context).publishing_enabled}.')


def is_owner_private(update: Update, cfg: Settings) -> bool:
    return bool(update.effective_user and update.effective_chat and
                update.effective_chat.type == ChatType.PRIVATE and
                update.effective_user.id == cfg.owner_id and
                update.effective_chat.id == cfg.owner_id)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    cfg = settings(context)
    if not is_owner_private(update, cfg):
        await query.answer('Non autorisé.', show_alert=True)
        return
    try:
        _, number, action = query.data.split(':')
        post_id = int(number)
    except (ValueError, AttributeError):
        await query.answer('Bouton invalide.', show_alert=True)
        return
    if not store(context).decide(post_id, action, local_now()):
        await query.answer('Bouton expiré ou déjà utilisé.', show_alert=True)
        return
    await query.answer('Décision enregistrée.')
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        LOG.warning('Could not remove old buttons for post %s', post_id)
    if action == 'approve':
        await owner_notice(context, '✅ Publication approuvée. Elle ne partira qu’à 10 h et seulement si la publication TEST est activée.')
    elif action == 'reject':
        await owner_notice(context, '❌ Publication refusée : rien ne sera envoyé aujourd’hui.')
    else:
        await owner_notice(context, '✏️ Envoie maintenant ton texte corrigé dans cette conversation privée. Il te sera reproposé avec les boutons.')


async def owner_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = settings(context)
    if not is_owner_private(update, cfg) or not update.message or not update.message.text:
        return
    now = local_now()
    editing = store(context).pending_edit(now.date().isoformat())
    if editing is None:
        return
    text = update.message.text.strip()
    if len(text) < 25 or len(text) > 3000:
        await update.message.reply_text('Ton texte doit contenir entre 25 et 3 000 caractères.')
        return
    if store(context).replace_edit(editing['id'], now.date().isoformat(), text, now):
        await send_preview(context, store(context).get_post(editing['id']))


async def coach_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = settings(context)
    if not cfg.assistant_enabled or not cfg.openai_key or not update.message or not update.message.text:
        return
    if not update.effective_user or not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return
    if update.effective_user.id == cfg.owner_id:
        return
    now = local_now()
    if not store(context).check_quota(update.effective_user.id, now.date().isoformat(), int(now.timestamp())):
        await update.message.reply_text('Tu as atteint ta limite de messages ou tu écris trop vite. Reviens un peu plus tard.')
        return
    try:
        client = AsyncOpenAI(api_key=cfg.openai_key, timeout=35.0)
        response = await client.responses.create(
            model=cfg.openai_model,
            instructions=COACH_RULES,
            input=update.message.text[:1000],
            max_output_tokens=400,
            store=False,
        )
        text = (response.output_text or '').strip()[:3000]
        if not text:
            raise RuntimeError('Empty coach response')
        await update.message.reply_text(text)
    except Exception:
        LOG.exception('Coach response failed')
        await update.message.reply_text('Je suis momentanément indisponible. Réessaie plus tard.')


async def on_start(application: Application):
    cfg: Settings = application.bot_data['settings']
    webhook = await application.bot.get_webhook_info()
    if webhook.url and not cfg.allow_webhook_takeover:
        raise RuntimeError('Make webhook actif. Arrêter Make et autoriser explicitement la migration avant de lancer ce bot.')
    if application.job_queue is None:
        raise RuntimeError('Installer python-telegram-bot[job-queue]')
    application.job_queue.run_daily(prepare_post, time=time(9, 0, tzinfo=PARIS),
                                    name='prepare-at-09-paris', job_kwargs={'misfire_grace_time': 60})
    application.job_queue.run_daily(publish_post, time=time(10, 0, tzinfo=PARIS),
                                    name='publish-at-10-paris', job_kwargs={'misfire_grace_time': 60})
    LOG.info('Started CHARBON TEST, publish enabled=%s, assistant enabled=%s',
             cfg.publishing_enabled, cfg.assistant_enabled)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    cfg = Settings.load()
    db = Store(cfg.sqlite_path)
    app = ApplicationBuilder().token(cfg.bot_token).post_init(on_start).build()
    app.bot_data.update(settings=cfg, store=db)
    app.add_handler(CommandHandler('start', start_cmd))
    app.add_handler(CommandHandler('preview', preview_cmd))
    app.add_handler(CommandHandler('generate', generate_cmd))
    app.add_handler(CommandHandler('status', status_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r'^post:\d+:(approve|edit|reject)$'))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, owner_message), group=0)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, coach_message), group=1)
    # Updates from group chats and channels are never handled by this application.
    app.run_polling(allowed_updates=['message','callback_query'], drop_pending_updates=True)


if __name__ == '__main__':
    main()
