import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config import Config
from trading_strategy import TradingBot
from database import Database
import json
from datetime import datetime

# Состояния для ConversationHandler
SET_SYMBOL, SET_LEVERAGE = range(2)


class TelegramBot:
    def __init__(self, trading_bot: TradingBot):
        self.trading_bot = trading_bot
        self.db = Database()
        self.logger = logging.getLogger(__name__)

        # Создаем приложение Telegram
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

        # Добавляем обработчики команд
        self._setup_handlers()

    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        # Сначала ConversationHandler (важно для приоритета)
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('set_symbol', self._set_symbol)],
            states={
                SET_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._set_symbol_receive)],
                SET_LEVERAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._set_leverage_receive)],
            },
            fallbacks=[CommandHandler('cancel', self._cancel)],
        )
        self.application.add_handler(conv_handler)

        # Затем обычные команды
        self.application.add_handler(CommandHandler("start", self._start))
        self.application.add_handler(CommandHandler("balance", self._balance))
        self.application.add_handler(
            CommandHandler("positions", self._positions))
        self.application.add_handler(
            CommandHandler("close_all", self._close_all))
        self.application.add_handler(
            CommandHandler("settings", self._settings))
        self.application.add_handler(CommandHandler("reverse", self._reverse))
        self.application.add_handler(CommandHandler("close", self._close))

        # В самом конце - обработчик для неизвестных команд
        self.application.add_handler(
            MessageHandler(filters.COMMAND, self._unknown))

    async def _send_message(self, update: Update, text: str, parse_mode: str = '', reply_markup=None):
        """Безопасная отправка сообщения"""
        try:
            if update.message:
                await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
            elif update.effective_chat:
                await self.application.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
        except Exception as e:
            self.logger.error(f"Ошибка отправки сообщения: {e}")

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        # Автоматически добавляем пользователя при команде /start
        self.db.add_allowed_user(user_id, username)

        await self._send_message(
            update,
            "🤖 Торговый бот запущен.\n\n"
            "Доступные команды:\n"
            "/balance - текущий баланс\n"
            "/positions - открытые позиции\n"
            "/close [id] - закрыть позицию по ID\n"
            "/close_all - закрыть все позиции\n"
            "/reverse - принудительный переворот позиций\n"
            "/settings - текущие настройки\n"
            # "/set_symbol - изменить торговую пару"
        )

    async def _balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /balance"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен. Используйте /start для активации.")
            return

        # Обновляем баланс
        self.trading_bot.update_balance()
        arrow, balance_change, balance_change_percent, highest, lowest = self.trading_bot.get_balance_change_info()

        balance_info = self.trading_bot.balance_info
        message = (
            f"💰 *Баланс:* {balance_info['total_equity']:.2f} USDT\n"
            f"{arrow} *Изменение:* {balance_change:+.2f} USDT ({balance_change_percent:+.2f}%)\n"
            f"📊 *Начальный баланс:* {self.trading_bot.initial_balance:.2f} USDT\n"
            f"📈 *Максимальный баланс:* {highest:.2f} USDT\n"
            f"📉 *Минимальный баланс:* {lowest:.2f} USDT\n"
            f"💳 *Доступно:* {balance_info['total_available']:.2f} USDT"
        )

        await self._send_message(update, message, parse_mode='Markdown')

    async def _positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /positions"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен. Используйте /start для активации.")
            return

        open_positions = self.db.get_open_positions()
        if not open_positions:
            await self._send_message(update, "📭 Нет открытых позиций.")
            return

        message = "📋 *Открытые позиции:*\n\n"
        for pos in open_positions:
            direction_emoji = "🟢" if pos['side'] == 'BUY' else "🔴"
            direction_text = "ЛОНГ" if pos['side'] == 'BUY' else "ШОРТ"

            message += (
                f"{direction_emoji} *{direction_text}*\n"
                f"🆔 *ID:* {pos['id']}\n"
                f"💹 *Символ:* {pos['symbol']}\n"
                f"📊 *Сторона:* {pos['side']}\n"
                f"🔢 *Размер:* {pos['size']:.4f}\n"
                f"💵 *Цена входа:* {pos['entry_price']:.2f}\n"
                f"💰 *Текущая цена:* {pos['current_price']:.2f}\n"
                f"📉 *Стоп-лосс:* {pos['stop_loss']:.2f}\n"
                f"📈 *Тейк-профит:* {pos['take_profit']:.2f}\n"
                f"📈 *P&L:* {pos['pnl']:.2f} USDT ({pos['pnl_percent']:.2f}%)\n"
                f"⏰ *Открыта:* {pos['created_at'][:19]}\n"
                f"────────────────────\n"
            )

        await self._send_message(update, message, parse_mode='Markdown')

    async def _close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /close [id]"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен. Используйте /start для активации.")
            return

        if not context.args:
            await self._send_message(update, "❌ Укажите ID позиции: /close [id]")
            return

        try:
            position_id = int(context.args[0])
        except ValueError:
            await self._send_message(update, "❌ Неверный ID позиции.")
            return

        position = self.db.get_position(position_id)
        if not position:
            await self._send_message(update, "❌ Позиция не найдена.")
            return

        if position['status'] != 'open':
            await self._send_message(update, "❌ Позиция уже закрыта.")
            return

        # Получаем текущую цену
        market_data = self.trading_bot.bybit.get_market_data(
            position['symbol'])
        if not market_data:
            await self._send_message(update, "❌ Ошибка получения текущей цены.")
            return

        # Закрываем позицию
        success = self.trading_bot.bybit.close_position(
            position['symbol'], position['side'])
        if success:
            self.db.close_position(position_id, market_data['price'])
            await self._send_message(update, f"✅ Позиция #{position_id} закрыта.")
        else:
            await self._send_message(update, f"❌ Ошибка закрытия позиции #{position_id}.")

    async def _close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /close_all"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен. Используйте /start для активации.")
            return

        open_positions = self.db.get_open_positions()
        if not open_positions:
            await self._send_message(update, "📭 Нет открытых позиций.")
            return

        closed_count = 0
        for position in open_positions:
            market_data = self.trading_bot.bybit.get_market_data(
                position['symbol'])
            if market_data:
                success = self.trading_bot.bybit.close_position(
                    position['symbol'], position['side'])
                if success:
                    self.db.close_position(
                        position['id'], market_data['price'])
                    closed_count += 1

        await self._send_message(update, f"✅ Закрыто позиций: {closed_count}/{len(open_positions)}")

    async def _settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /settings"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен. Используйте /start для активации.")
            return

        symbol = self.db.get_setting('symbol', Config.DEFAULT_SYMBOL)
        leverage = self.db.get_setting('leverage', '10')
        risk_percent = self.trading_bot.risk_percent
        stop_loss_percent = self.trading_bot.stop_loss_percent
        take_profit_percent = self.trading_bot.take_profit_percent

        message = (
            f"⚙️ *Текущие настройки:*\n"
            f"• *Торговая пара:* {symbol}\n"
            f"• *Леверидж:* {leverage}x\n"
            f"• *Риск на сделку:* {risk_percent}%\n"
            f"• *Стоп-лосс:* {stop_loss_percent}%\n"
            f"• *Тейк-профит:* {take_profit_percent}%\n"
            f"• *Мин. уверенность:* {self.trading_bot.min_confidence}\n\n"
            f"Изменить пару: `/set_symbol`"
        )

        await self._send_message(update, message, parse_mode='Markdown')

    async def _set_symbol(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса смены символа"""
        if not update.effective_user:
            return ConversationHandler.END

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен. Используйте /start для активации.")
            return ConversationHandler.END

        await self._send_message(
            update,
            "Введите новую торговую пару (например: BTCUSDT, ETHUSDT):",
            reply_markup=ReplyKeyboardRemove()
        )
        return SET_SYMBOL

    async def _set_symbol_receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода символа и запрос левериджа"""
        if not update.message or not update.effective_user:
            return ConversationHandler.END

        if not update.message.text:
            return
        symbol = update.message.text.upper().strip()

        # Простая валидация символа
        if not symbol.endswith('USDT'):
            await self._send_message(update, "❌ Неверный формат. Используйте формат: BTCUSDT, ETHUSDT и т.д.")
            return SET_SYMBOL

        # Проверяем существование символа на бирже
        market_data = self.trading_bot.bybit.get_market_data(symbol)
        if not market_data:
            await self._send_message(update, f"❌ Символ {symbol} не найден на бирже.")
            return SET_SYMBOL

        if not context.user_data:
            return
        context.user_data['new_symbol'] = symbol

        current_leverage = self.db.get_setting('leverage', '10')
        await self._send_message(
            update,
            f"✅ Символ {symbol} доступен.\n"
            f"Текущий леверидж: {current_leverage}x\n"
            f"Введите новый леверидж (1-100):"
        )
        return SET_LEVERAGE

    async def _set_leverage_receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода левериджа и сохранение настроек"""
        if not update.message or not update.effective_user:
            return ConversationHandler.END

        if not update.message.text:
            return
        leverage_text = update.message.text.strip()
        try:
            leverage = int(leverage_text)
            if leverage < 1 or leverage > 100:
                await self._send_message(update, "❌ Леверидж должен быть от 1 до 100.")
                return SET_LEVERAGE
        except ValueError:
            await self._send_message(update, "❌ Введите число от 1 до 100.")
            return SET_LEVERAGE

        if not context.user_data:
            return
        symbol = context.user_data['new_symbol']

        # Сохраняем настройки в базу
        self.db.set_setting('symbol', symbol)
        self.db.set_setting('leverage', str(leverage))

        # Обновляем настройки в торговом боте
        self.trading_bot.symbol = symbol
        self.trading_bot.leverage = leverage

        # Устанавливаем леверидж на бирже
        success = self.trading_bot.bybit.set_leverage(symbol, leverage)

        leverage_status = "✅" if success else "⚠️ (ошибка установки на бирже)"

        await self._send_message(
            update,
            f"✅ Настройки обновлены:\n"
            f"• Торговая пара: {symbol}\n"
            f"• Леверидж: {leverage}x {leverage_status}"
        )

        # Очищаем данные разговора
        if context.user_data:
            context.user_data.clear()

        return ConversationHandler.END

    async def _reverse(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Принудительный переворот позиции"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен. Используйте /start для активации.")
            return

        open_positions = self.db.get_open_positions()
        if not open_positions:
            await self._send_message(update, "📭 Нет открытых позиций для переворота.")
            return

        position = open_positions[0]
        market_data = self.trading_bot.bybit.get_market_data(
            position['symbol'])
        if not market_data:
            await self._send_message(update, "❌ Ошибка получения рыночных данных.")
            return

        # Закрываем текущую позицию
        success = self.trading_bot.bybit.close_position(
            position['symbol'], position['side'])
        if success:
            self.db.close_position(position['id'], market_data['price'])
            await self._send_message(update, f"✅ Позиция #{position['id']} закрыта для переворота.")

            # Открываем противоположную позицию
            new_side = "Sell" if position['side'] == 'BUY' else "Buy"
            position_amount = self.trading_bot.calculate_position_size(
                market_data['price'])

            if new_side == "Buy":
                self.trading_bot._execute_buy(
                    {'action': 'BUY', 'confidence': 1.0,
                        'reason': 'Manual reversal'},
                    market_data,
                    position_amount
                )
            else:
                self.trading_bot._execute_sell(
                    {'action': 'SELL', 'confidence': 1.0,
                        'reason': 'Manual reversal'},
                    market_data,
                    position_amount
                )

            await self._send_message(update, f"✅ Открыта противоположная позиция ({new_side})")
        else:
            await self._send_message(update, f"❌ Ошибка закрытия позиции для переворота.")

    async def _cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена операции"""
        if context.user_data:
            context.user_data.clear()

        await self._send_message(
            update,
            "❌ Операция отменена.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    async def _unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик неизвестных команд"""
        if update.message and update.message.text:
            self.logger.warning(f"Неизвестная команда: {update.message.text}")

        await self._send_message(
            update,
            "❌ Неизвестная команда. Используйте /start для списка команд."
        )

    def run(self):
        """Запуск бота"""
        self.logger.info("🤖 Запуск Telegram бота...")
        self.application.run_polling()

    def stop(self):
        """Остановка бота"""
        self.logger.info("🛑 Остановка Telegram бота...")
        self.application.stop()
