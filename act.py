from email.headerregistry import MessageIDHeader
import logging
from operator import is_
import random
import time
import calendar
import datetime
import pandas as pd
import copy
from telegram import Update
from telegram.ext import (ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, ConversationHandler,
    filters, PicklePersistence)

TOKEN = '#### TOKEN #####'
CHAT_ID_FOR_STAT = '## CHAT ID (INT) ##'

TO_ANSWER_SPAN = 60 # Change to 1 hour after finish testing
TO_ANSWER_SPAN_CHECK_INTERVAL = 10 # Change to 60 seconds after finish testing
DELAY_DELETE_QUESTION = 5 # Change to 10 seconds after finish testing
DELAY_ASK_AGAIN = DELAY_DELETE_QUESTION + 5 # Change to +12 hours
FIRST_STAT = 30 # To 12 hours
STAT_INTERVAL = 30 # To 12 hours

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

REPLY = 0
failed_answers = 0
time_of_question_given_out = 0
time_of_question_asked = 0
is_question_asked = False
is_question_given = False
rquestion = None
ranswer = None

# Первичное решение: статистика пользователей хранится в словаре user_data
# и отсылается на выбранный аккаунт раз в 12 часов

user_data = []
record = {}

# the command function of asking a question
# prompts the bot to actually do the script, basically the main starting command

async def ask_question(context):
    global is_question_asked, time_of_question_asked
    global record
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text="Ответьте на вопрос используя команду /answer [ответ], у вас есть час: " + rquestion)

    # takes in the time when the question was asked
    date = datetime.datetime.utcnow()
    time_of_question_asked = calendar.timegm(date.utctimetuple())

    record['question_asked'] = time_of_question_asked

    is_question_asked = True

    # Start a job for time check
    context.job_queue.run_repeating(
        check_time_span, TO_ANSWER_SPAN_CHECK_INTERVAL, chat_id=job.chat_id, name=str(job.chat_id) + ' check_time_span',
    )

'''
Следит за временем и помечает пользователю вопрос как неотвеченный, если он не успевает ответить вовремя
'''
async def check_time_span(context):
    global record
    # Если пользователь закрыл вопрос самостоятельно, остановить задачу
    if not record.get('question_asked'):
        context.job.schedule_removal()
    # Если время пользователя на ответ вышло, принудительно закрыть вопрос и остановить задачу
    elif not time_is_fine():
        context.job.schedule_removal()
        await context.bot.send_message(context.job.chat_id, "Время отвечать на вопрос вышло.")
        record['question_answered'] = 'No'
        reset_defaults()

'''
Проверка правильности временного диапазона для ответа
'''
def time_is_fine(time_span=TO_ANSWER_SPAN):
    date = datetime.datetime.utcnow()
    answer_time = calendar.timegm(date.utctimetuple())
    return time_of_question_asked <= answer_time <= time_of_question_asked + time_span

'''
После того как проверка или пройдена или провалена,
сбрасывает изначальные значения, и можно получать новый вопрос.
'''
def reset_defaults():
    global failed_answers
    global time_of_question_given_out, time_of_question_asked
    global is_question_given, is_question_asked
    global rquestion, ranswer
    global user_data, record
    failed_answers = 0
    time_of_question_given_out = 0
    time_of_question_asked = 0
    is_question_given = False
    is_question_asked = False
    rqueston = None
    ranswer = None
    user_data.append(record)
    record = {}

async def answer(update, context):
    global is_question_given, is_question_asked
    global qa_number, time_of_question_asked
    global record
    chat_id=update.effective_chat.id

    if is_question_given:
        if is_question_asked:
            if time_is_fine():
                if context.args:
                    await check_answer(update, context)
                else:
                    await context.bot.send_message(chat_id, "Введите ответ:")
                return REPLY
            else:
                await context.bot.send_message(chat_id, "Время отвечать на вопрос вышло.")
                await context.bot.delete_message(chat_id, message_id=update.effective_message.id)
                record['question_answered'] = 'No'
                reset_defaults()
        else:
            await context.bot.send_message(chat_id, "Время отвечать на вопрос ещё не пришло.")
    else:
        await context.bot.send_message(chat_id, text="Сначала получите вопрос. /question")

async def check_answer(update, context):
    global failed_answers
    global is_question_given, is_question_asked
    global record
    chat_id = update.effective_chat.id

    date = datetime.datetime.utcnow()
    answer_time = calendar.timegm(date.utctimetuple())

    if context.args:
        user_reply = ' '.join(context.args)
    else:
        if time_is_fine():
            user_reply = update.message.text
        else:
            await context.bot.send_message(chat_id, "Время отвечать на вопрос вышло.")
            record['question_answered'] = 'No'
            reset_defaults()

    if ranswer.lower() == user_reply.lower():
        await context.bot.send_message(chat_id, "Ответ верный. Проверка пройдена.")
        record['question_answered'] = answer_time
        reset_defaults()
    else:
        if failed_answers < 2:
            await context.bot.send_message(chat_id, "Ответ неверный. Попробуйте ещё раз.")
            await context.bot.send_message(chat_id, "Введите ответ:")
            failed_answers += 1
            return REPLY
        else:
            await context.bot.send_message(chat_id, "Ответ неверный. Проверка не пройдена.")
            record['question_answered'] = 'No'
            reset_defaults()

    return ConversationHandler.END

# This function deletes some messages during the question phase and sends some messages, has to be a separate func in order for it to work with telegram bot asyn jobs

async def delmessage(context):
    job = context.job
    bid, qid, aid = job.data
    await context.bot.delete_message(
        chat_id=job.chat_id, message_id=bid)
    await context.bot.delete_message(
        chat_id=job.chat_id, message_id=qid)
    await context.bot.delete_message(
        chat_id=job.chat_id, message_id=aid)
    await context.bot.send_message(chat_id=job.chat_id, text='Через 12 часов вам снова придёт вопрос, на который вы должны будете верно ответить. После этого вы сможете получить новый вопрос.')


# Basic start command, just gives you some info about what you're supposed to do

async def start(update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Доброго времени суток! Этот бот будет использоваться для подтвердждения вашей активности. Используйте команду /question чтобы получить вопрос.")


# Gives question from file
# Randomly rolls a question from a file, i of question matches i of answer

async def give_question(update, context):
    global time_of_question_given_out
    global is_question_given
    global rquestion, ranswer
    global record

    chat_id = update.effective_message.chat_id

    if is_question_given:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы уже получили вопрос.")
        return

    qa_number = random.randint(0, 2)

    # Пара вопрос-ответ должна быть статична на протяжении 12 часов, поэтому читать файлы нужно 1 раз.
    # Таким образом избегается ошибка несовпадения, если файл или файлы будут изменены в промежуток, когда пользователь уже получил вопрос, но ещё не дал ответ.
    try:
        with open('./files/questions.txt', encoding='utf8') as f:
            linesq = f.readlines()
            rquestion = linesq[qa_number].strip()
        with open('./files/answers.txt', encoding='utf8') as a:
            linesa = a.readlines()
            ranswer = linesa[qa_number].strip()
    except Exception as e:
        print('Error while opening file:', e)
        await context.bot.send_message(chat_id, text="Возникла ошибка, на этот раз обойдёмся без вопросов!")
        return

    await context.bot.send_message(chat_id, text="Вот ваш вопрос. У вас есть 10 секунд чтобы запомнить на него ответ.")

    # Gives out the question and answer intitially
    bid = update.effective_message.id + 1
    await context.bot.send_message(chat_id, text='Вопрос: '+rquestion)
    qid = update.effective_message.id + 2
    await context.bot.send_message(chat_id, text='Ответ: '+ranswer)
    aid = update.effective_message.id + 3

    record['user_id'] = update.effective_user.id
    record['username'] = update.effective_user.username
    record['full_name'] = update.effective_user.full_name

    # Question given out
    date = datetime.datetime.utcnow()
    time_of_question_given_out = calendar.timegm(date.utctimetuple())
    print("Time of question given out: ", time_of_question_given_out)

    record['question_given'] = time_of_question_given_out

    is_question_given = True

    # Deletes message with question and answer
    context.job_queue.run_once(
        delmessage, DELAY_DELETE_QUESTION, chat_id=chat_id, name=str(chat_id) + ' delmessage',
        data=(bid, qid, aid)
    )

    # Asks question once again
    context.job_queue.run_once(
        ask_question, DELAY_ASK_AGAIN, chat_id=chat_id, name=str(chat_id) + ' ask_question',
    )


'''
В идеале нужно делать базу данных, и потом из неё рисовать таблицу, например, раз в 12 часов.
Для начала можно собирать данные в словарь внутри основного скрипта.
Если сервер поддерживает изменение файлов в процессе выполнения, то можно обойтись и без базы данных.
'''
async def send_user_data(context, chat_id=CHAT_ID_FOR_STAT):
    # Трасляция дат в human readable
    user_data_h = copy.deepcopy(user_data)
    for record in user_data_h:
        for key in record:
            if key in ['question_given', 'question_asked', 'question_answered']:
                try:
                    record[key] = datetime.datetime.fromtimestamp(record[key]).strftime('%d %b %H:%M:%S')
                except TypeError:
                    pass

    df = pd.DataFrame(user_data_h)

    await context.bot.send_message(chat_id, '<pre>' + df.to_string(index=False) + '</pre>', parse_mode='html')


if __name__ == '__main__':
    # application = ApplicationBuilder().token(TOKEN).build()
    '''
    У меня на машине новая версия телеграма начала часто обрывать соединения по таймаутам,
    поэтому я увеличил все виды таймаутов. Возможно на сервере не должно быть такой проблемы,
    и можно использовать стандартный билд.
    '''
    builder = ApplicationBuilder().token(TOKEN)
    builder.read_timeout(20)
    builder.write_timeout(20)
    builder.connect_timeout(20)
    builder.pool_timeout(20)
    builder.get_updates_read_timeout(20)

    # Persistence позволяет не потерять значения переменных Conversation при перезагрузке сервера, при maintenance и т.д.
    persistence = PicklePersistence(filepath='persistence.pickle')
    builder.persistence(persistence=persistence)

    application = builder.build()

    start_handler = CommandHandler('start', start)
    give_question_handler = CommandHandler('question', give_question)
    answer_handler = CommandHandler('answer', answer)
    reply_handler = ConversationHandler(
        entry_points=[answer_handler],
        states={
            REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_answer)],
        },
        fallbacks=[],
        allow_reentry=True
    )

    application.add_handler(start_handler)
    application.add_handler(give_question_handler)
    application.add_handler(reply_handler)

    # Первичный вариант вывода статистики
    application.job_queue.run_repeating(send_user_data, interval=STAT_INTERVAL, first=FIRST_STAT)

    application.run_polling()
