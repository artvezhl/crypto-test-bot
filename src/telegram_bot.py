import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config import Config
from trading_strategy import TradingBot
from database import Database
import json
from datetime import datetime

from virtual_trading_bot import VirtualTradingBot

# Состояния для ConversationHandler
SET_SYMBOL, SET_LEVERAGE = range(2)


class TelegramBot:
    def __init__(self, trading_bot: TradingBot):
        self.trading_bot = VirtualTradingBot()
        # self.trading_bot = trading_bot
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
        self.application.add_handler(CommandHandler("close", self._close))
        self.application.add_handler(CommandHandler("reverse", self._reverse))

        # Команды для настроек
        self.application.add_handler(CommandHandler("set", self._set_setting))
        self.application.add_handler(CommandHandler(
            "set_setting", self._set_setting))  # Альтернативная команда

        # Команды администратора
        self.application.add_handler(
            CommandHandler("admin_users", self._admin_users))
        self.application.add_handler(CommandHandler(
            "reset_settings", self._reset_settings))

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

        # Проверяем, есть ли пользователь в белом списке
        if not self.db.is_user_allowed(user_id):
            await self._send_message(
                update,
                "❌ Доступ запрещен.\n\n"
                "Ваш user ID не найден в списке разрешенных пользователей.\n"
                f"Ваш ID: {user_id}\n"
                "Обратитесь к администратору для получения доступа."
            )
            return

        await self._send_message(
            update,
            "🤖 *Торговый бот запущен*\n\n"
            "*Основные команды:*\n"
            "• /balance - текущий баланс\n"
            "• /positions - открытые позиции\n"
            "• /close [id] - закрыть позицию по ID\n"
            "• /close_all - закрыть все позиции\n"
            "• /reverse - переворот позиции\n\n"
            "*Настройки:*\n"
            "• /settings - текущие настройки\n\n"
            "*Администратор:*\n"
            "• /set [ключ] [значение] - изменить настройку\n"
            "• /set_symbol - изменить торговую пару\n"
            "• /admin_users - управление пользователями\n"
            "• /reset_settings - сброс настроек\n\n"
            "Используйте /settings для просмотра всех доступных настроек.",
            parse_mode='Markdown'
        )

    async def _admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для управления пользователями (только для админов)"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id

        # Проверяем, является ли пользователь администратором
        if not self.db.is_user_admin(user_id):
            await self._send_message(update, "❌ Эта команда доступна только администраторам.")
            return

        if not context.args:
            # Показываем список пользователей
            users = self.db.get_all_users()
            if not users:
                await self._send_message(update, "📝 Список пользователей пуст.")
                return

            message = "👥 *Список пользователей:*\n\n"
            for user in users:
                status = "🟢 Админ" if user.get(
                    'is_admin') else "🔵 Пользователь"
                message += (
                    f"👤 *{user['username']}*\n"
                    f"🆔 ID: `{user['user_id']}`\n"
                    f"📊 {status}\n"
                    f"📅 Добавлен: {user['created_at'][:10]}\n"
                    f"────────────────────\n"
                )

            message += "\nКоманды управления:\n"
            message += "• `/admin_users add <user_id> <username>` - добавить пользователя\n"
            message += "• `/admin_users remove <user_id>` - удалить пользователя\n"
            message += "• `/admin_users admin <user_id>` - сделать администратором\n"
            message += "• `/admin_users user <user_id>` - убрать права администратора\n"

            await self._send_message(update, message, parse_mode='Markdown')
            return

        command = context.args[0].lower()

        if command == 'add' and len(context.args) >= 3:
            try:
                new_user_id = int(context.args[1])
                new_username = ' '.join(context.args[2:])

                if self.db.add_allowed_user(new_user_id, new_username):
                    await self._send_message(update, f"✅ Пользователь {new_username} (ID: {new_user_id}) добавлен.")
                else:
                    await self._send_message(update, "❌ Ошибка при добавлении пользователя.")

            except ValueError:
                await self._send_message(update, "❌ Неверный формат user_id.")

        elif command == 'remove' and len(context.args) >= 2:
            try:
                remove_user_id = int(context.args[1])

                if self.db.remove_user(remove_user_id):
                    await self._send_message(update, f"✅ Пользователь (ID: {remove_user_id}) удален.")
                else:
                    await self._send_message(update, "❌ Пользователь не найден.")

            except ValueError:
                await self._send_message(update, "❌ Неверный формат user_id.")

        elif command == 'admin' and len(context.args) >= 2:
            try:
                admin_user_id = int(context.args[1])

                if self.db.set_user_admin(admin_user_id, True):
                    await self._send_message(update, f"✅ Пользователь (ID: {admin_user_id}) назначен администратором.")
                else:
                    await self._send_message(update, "❌ Пользователь не найден.")

            except ValueError:
                await self._send_message(update, "❌ Неверный формат user_id.")

        elif command == 'user' and len(context.args) >= 2:
            try:
                user_user_id = int(context.args[1])

                if self.db.set_user_admin(user_user_id, False):
                    await self._send_message(update, f"✅ Пользователь (ID: {user_user_id}) лишен прав администратора.")
                else:
                    await self._send_message(update, "❌ Пользователь не найден.")

            except ValueError:
                await self._send_message(update, "❌ Неверный формат user_id.")

        else:
            await self._send_message(update, "❌ Неверная команда. Используйте /admin_users для справки.")

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
        """Показ всех текущих настроек"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен.")
            return

        # Получаем все настройки из бота
        settings = self.trading_bot.get_all_settings()

        message = "⚙️ *Текущие настройки:*\n\n"

        # Группируем настройки для лучшего отображения
        categories = {
            '📊 Торговые настройки': [
                'trading_symbols', 'default_symbol', 'min_confidence', 'leverage',
                'trading_interval_minutes'
            ],
            '🛡️ Риск-менеджмент': [
                'risk_percent', 'max_position_percent', 'max_total_position_percent',
                'min_trade_usdt', 'stop_loss_percent', 'take_profit_percent',
                'trailing_stop_activation_percent', 'trailing_stop_distance_percent'
            ],
            '🔧 Поведение': [
                'allow_short_positions', 'allow_long_positions', 'auto_position_reversal'
            ],
            '🔔 Уведомления': [
                'enable_notifications', 'enable_trade_logging'
            ],
            '🤖 DeepSeek': [
                'deepseek_model', 'deepseek_max_tokens', 'deepseek_temperature',
                'enable_deepseek_reasoning'
            ],
            '💰 Баланс': [
                'initial_balance'
            ]
        }

        for category, keys in categories.items():
            message += f"*{category}:*\n"
            for key in keys:
                if key in settings:
                    value = settings[key]
                    # Сокращаем длинные значения
                    if key == 'trading_symbols' and len(value) > 50:
                        value = value[:50] + "..."
                    message += f"• `{key}: {value}`\n"
            message += "\n"

        message += "*Изменить настройку:*\n"
        message += "`/set <ключ> <значение>`\n\n"
        message += "*Примеры:*\n"
        message += "`/set leverage 5`\n"
        message += "`/set risk_percent 1.5`\n"
        message += "`/set enable_notifications true`\n"
        message += "`/set trading_symbols BTCUSDT,ETHUSDT`"

        await self._send_message(update, message, parse_mode='Markdown')

    async def _set_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Изменение настройки"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id):
            await self._send_message(update, "❌ Доступ запрещен.")
            return

        if not context.args or len(context.args) < 2:
            await self._send_message(update,
                                     "❌ Использование: /set <ключ> <значение>\n\n"
                                     "Примеры:\n"
                                     "`/set trading_symbols BTCUSDT,ETHUSDT,ADAUSDT`\n"
                                     "`/set leverage 10`\n"
                                     "`/set risk_percent 2.0`\n"
                                     "`/set enable_notifications true`\n\n"
                                     "Посмотреть текущие настройки: /settings"
                                     )
            return

        key = context.args[0]
        value = ' '.join(context.args[1:])

        # Валидация числовых значений
        numeric_keys = [
            'leverage', 'min_confidence', 'risk_percent', 'max_position_percent',
            'max_total_position_percent', 'min_trade_usdt', 'stop_loss_percent',
            'take_profit_percent', 'trailing_stop_activation_percent',
            'trailing_stop_distance_percent', 'initial_balance',
            'deepseek_max_tokens', 'deepseek_temperature', 'trading_interval_minutes'
        ]

        if key in numeric_keys:
            try:
                if key == 'leverage':
                    leverage = int(value)
                    if leverage < 1 or leverage > 100:
                        await self._send_message(update, "❌ Леверидж должен быть от 1 до 100")
                        return
                elif key in ['min_confidence', 'deepseek_temperature']:
                    float_value = float(value)
                    if float_value < 0 or float_value > 1:
                        await self._send_message(update, f"❌ {key} должен быть между 0 и 1")
                        return
                else:
                    float_value = float(value)
                    if float_value < 0:
                        await self._send_message(update, f"❌ {key} должен быть положительным числом")
                        return
            except ValueError:
                await self._send_message(update, f"❌ {key} должен быть числом")
                return

        # Валидация булевых значений
        boolean_keys = [
            'enable_notifications', 'enable_trade_logging', 'allow_short_positions',
            'allow_long_positions', 'auto_position_reversal', 'enable_deepseek_reasoning'
        ]
        if key in boolean_keys:
            if value.lower() not in ['true', 'false', '1', '0', 'yes', 'no']:
                await self._send_message(update, f"❌ {key} должен быть true или false")
                return
            # Нормализуем значение
            value = 'true' if value.lower() in [
                'true', '1', 'yes'] else 'false'

        # Валидация trading_symbols
        if key == 'trading_symbols':
            symbols = [s.strip().upper() for s in value.split(',')]
            # Простая валидация формата символов
            for symbol in symbols:
                if not symbol.endswith('USDT'):
                    await self._send_message(update, f"❌ Неверный формат символа: {symbol}. Используйте формат: BTCUSDT,ETHUSDT")
                    return
            value = ','.join(symbols)

        try:
            # Обновляем настройку
            self.trading_bot.update_setting(key, value)
            await self._send_message(update, f"✅ Настройка `{key}` обновлена на `{value}`")

            # Если изменили торговые символы, показываем обновленный список
            if key == 'trading_symbols':
                await self._send_message(update, f"📊 Теперь торгуем: {value}")

        except Exception as e:
            await self._send_message(update, f"❌ Ошибка при обновлении настройки: {str(e)}")

    async def _reset_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сброс настроек к значениям по умолчанию"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.db.is_user_allowed(user_id) or not self.db.is_user_admin(user_id):
            await self._send_message(update, "❌ Эта команда доступна только администраторам.")
            return

        # Подтверждение сброса
        if context.args and context.args[0] == 'confirm':
            # Инициализируем настройки по умолчанию
            self.trading_bot._initialize_default_settings()
            self.trading_bot._load_settings_from_db()

            await self._send_message(update, "✅ Все настройки сброшены к значениям по умолчанию")
        else:
            await self._send_message(
                update,
                "⚠️ *ВНИМАНИЕ:* Вы собираетесь сбросить ВСЕ настройки к значениям по умолчанию.\n\n"
                "Для подтверждения выполните:\n"
                "`/reset_settings confirm`",
                parse_mode='Markdown'
            )

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
