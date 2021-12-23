import uuid
import nltk
import re
import telebot
import os
import certifi
import calendar
import random
import pytz
from nltk.sem.evaluate import _ELEMENT_SPLIT_RE
from telebot import types
from datetime import time, timedelta, timezone, datetime, timezone
from nltk.tokenize import word_tokenize
from dateutil.relativedelta import relativedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from pymongo import MongoClient
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytz import timezone
from flask import Flask, request

ca = certifi.where()
server = Flask(__name__)

TOKEN = "token"

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

DATABASE_URL = os.environ.get("MONGODB_URI")

cluster = MongoClient(DATABASE_URL)

main_db = cluster["NLPReminders"]
event_collection = main_db["JobInfo"]

jobstore = main_db["jobstores"]

jobstores = {
    "mongo": MongoDBJobStore(database="NLPReminderJobs", collection="jobstores", client=cluster)
}

executors = {
    "default": ThreadPoolExecutor(20),
    "processpool": ProcessPoolExecutor(5)
}

DAYS = {0: ["monday", "mon"], 
        1: ["tuesday", "tues", "tue"], 
        2: ["wednesday", "weds", "wed"], 
        3: ["thursday", "thurs", "thur", "thu"], 
        4: ["friday", "fri"], 5: ["saturday", "sat"], 
        6: ["sunday", "sun"]}

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]

EXTENSIONS = ["th", "st", "nd", "rd"]

MONTHS_SHORT = ["jan", "feb", "mar", "april", "may", "jun", "jul", "aug", "sept", "oct", "nov", "dec"]

FILTERS = ["create a reminder for", 
           "set a reminder for", 
           "remind me to", 
           "create a reminder to", 
           "set a reminder to", 
           "set a reminder", 
           "create a reminder", 
           "remind me about", 
           "remind me", 
           "remind me in"]

ADD_EXTENSION = {0: "th", 1: "st", 2: "nd", 3: "rd", 11: "th", 12: "th", 13: "th"}

DATE_QUERY = ["What day your event on leh?", 
              "Your event on which day ah?", 
              "Can let me know the date also?", 
              "What day you want to set for?"]

TIME_QUERY = ["Your event at what time?", 
              "When your event start?", 
              "What time ah?", 
              "What time should I set this for ah?"]

DETAILS_QUERY = ["Can tell me the date and time?", 
                 "When your event ah? Lemme know the date also :)", 
                 "Tell me what time and when?", 
                 "Lemme know the date and time of the event!"] 

GREETING = ["Let me know when you need me again! :)", 
            "If you got appointment, drop me a text anytime ok?", 
            "Just send me a message anytime ah!", 
            "See you soon ya!", 
            "Bye!",
            "See you later!"]

WELCOME_MESSAGE = "*What can this bot do?*\n\nI'm a scheduling system with the ability to understand natural language (to a certain extent of course 😁). You can send me a text just as you would to a friend and I will try my best to create reminders for you.\
    \n\nYou will receive the notifications right here on Telegram.\
    \n\n\n*How to use?*\n\nYou can create reminders in many different ways. Here are some examples:\
    \n\n- _tell me to go work next mon at 10_\
    \n- _remind me to get groceries next weds at 1700_\
    \n- _exam on 17/2 9am_\
    \n- _clean up my room every tue at 10.30am_\
    \n- _set a reminder for dinner on the 8th Nov_\
    \n\nCurrently, I am unable to process commands such as _every 10 minutes_ or _every 30 seconds_.\
    \n\n\n*Key Features*\n\n- Recognise timings provided in 24-hour or 12-hour formats\
    \n- You can use short forms like _tmr_, _tues_, _dec_\
    \n- Attach a note to each reminder if needed\
    \n- Easily manage reminders via the inline keyboard menu\
    \n\n\n*Keyboard Menu*\
    \n\n✏️  *Edit* - Remove selected reminders\
    \n❌  *Cancel* - Terminate reminder setting process\
    \n📄  *My Reminders* - View all active reminders\
    \n\n\n*Command List*\
    \n\n*/start* - Bring up main menu\
    \n*/help* - Bring up this menu\
    \n\nIf you enjoyed using this project, leave me a ⭐️ on GitHub: https://github.com/nicleejy/DontForgetAh-Bot\
    \n\nThank you for using *DontForgetAh Bot*!"


scheduler = BackgroundScheduler(daemon=True, jobstores=jobstores, executors=executors, timezone="Asia/Singapore")

user_info = {}
tz = pytz.timezone("Asia/Singapore")

def generate_random(arr):
    return arr[random.randint(0, len(arr) - 1)]


def utc_to_local(utc_dt):
    return pytz.utc.localize(utc_dt, is_dst=None).astimezone(timezone("Asia/Singapore"))


def get_current_time():
    utc = datetime.utcnow()
    return utc_to_local(utc)


class Error(Exception):
    """Base class for other exceptions"""
    pass

class YearError(Error):
    def __init__(self, msg="Year not in the correct range", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
    pass

class DayError(Error):
    def __init__(self, msg="Day not in the correct range", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
    pass

class MonthError(Error):
    def __init__(self, msg="Month not in the correct range", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
    pass

class TimeError(Error):
    def __init__(self, msg="Time not in the correct range, or is in the past", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
    pass

class SetTimeError(Error):
    def __init__(self, msg="Error during time setting", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
    pass


def process_time(time_string, is_today):
    is_morning = False
    raw_time = time_string
    is_24hour = False
    am_pm = False
    #["hr", "min"]
    stage_1_time = None
    if "am" in time_string:
        is_morning = True
        slice = time_string.find("am")
        raw_time = time_string[:slice]
        am_pm = True
    elif "pm" in time_string:
        is_morning = False
        slice = time_string.find("pm")
        raw_time = time_string[:slice]
        am_pm = True

    if ":" in raw_time or "." in raw_time:
        stage_1_time = re.split("\.|\:", raw_time)
        
    else:
        if len(raw_time) == 4:
            is_24hour = True
            hour = raw_time[0:2]
            minute = raw_time[2:4]
            stage_1_time = [hour, minute]
        elif len(raw_time) <= 2:
            stage_1_time = [raw_time, "0"]
        else:
            if is_morning:
                hour = raw_time[0:1]
                minute = raw_time[1:3]
                stage_1_time = [hour, minute]
            else:
                hour = raw_time[0:2]
                minute = raw_time[2:3]
                stage_1_time = [hour, minute]

    if len(stage_1_time[0]) <= 2 and len(stage_1_time[1]) <= 2:
        try:
            stage_1_time = [int(i) for i in stage_1_time]
            if stage_1_time[0] > 23 or stage_1_time[0] < 0:
                raise(TimeError)
            if stage_1_time[1] > 59 or stage_1_time[1] < 0:
                raise(TimeError)
        except Exception as e:
            print(e)
            raise(TimeError)

    if int(stage_1_time[0]) > 12:
        is_24hour = True

    if not is_24hour:
        if stage_1_time[0] > 12 or stage_1_time[0] < 0:
            raise(TimeError)
        if am_pm:
            if not is_morning:
            #pm specified
                if stage_1_time[0] != 12:
                    stage_1_time[0] += 12
            else:
                #am specified
                if stage_1_time[0] == 12:
                    stage_1_time[0] = 0
        else:
            #am, pm not specified, ambiguous, make decision
            if is_today:
                if stage_1_time[0] < 11:
                    stage_1_time[0] += 12
            else:
                if stage_1_time[0] < 6:
                    stage_1_time[0] += 12

    stage_2_time = time(stage_1_time[0], stage_1_time[1])   
    return stage_2_time
           
#10pm, 9am, 1000, 1630, 1.30, 1:50, 2.05
def create_reminder(tokens, ID):
    today = get_current_time()
    day_of_week = today.weekday()
    adv_date = None
    adv_time = None
    set_month = False
    set_year = False
    set_week = False
    year = today.year
    is_today = False
    combined_datetime = today

    if "year" not in user_info[ID]:
        user_info[ID]["year"] = year

    if "month" in tokens:
        #skip by month instead of by week
        set_month = True
    elif "year" in tokens:
        set_year = True
    elif "week" in tokens:
        set_week = True   

    skip_count = tokens.count("next")
    tagged_words = nltk.pos_tag(tokens)
    index_1 = -1
    index_2 = -1 
    
    for words in tagged_words:
        if words[0] == "at" or words[0] == "for":
            index_1 = tagged_words.index(words)
            try:
                next = tagged_words[index_1 + 1][1]
            except IndexError:
                next = ""
                pass
            if next == "CD" and "time" not in user_info[ID]:
                #indicates time
                try:
                    next_word = tagged_words[index_1 + 2][0]
                except IndexError:
                    next_word = ""
                    pass
                if next_word in ["am", "pm"]:
                    user_info[ID]["time"] = tagged_words[index_1 + 1][0] + tagged_words[index_1 + 2][0]
                    break
                else:
                    user_info[ID]["time"] = tagged_words[index_1 + 1][0]
                    break        
        elif words[0].isdigit():
            if len(words[0]) == 4 or len(words[0]) == 1:
                user_info[ID]["time"] = words[0]
        elif "." in words[0] or ":" in words[0]:
            user_info[ID]["time"] = words[0]
        elif "am" in words[0] or "pm" in words[0]:
            if len(words[0]) > 2:
                user_info[ID]["time"] = words[0]
                break
            else:
                try:
                    index_2 = tagged_words.index(words)
                    user_info[ID]["time"] = tagged_words[index_2 - 1][0] + tagged_words[index_2][0]
                    tokens.remove(tagged_words[index_2 - 1][0])
                    tokens.remove(tagged_words[index_2][0])
                    break
                except ValueError:
                    pass
            
    for word in tokens:
        if word in MONTHS_SHORT and "month" not in user_info[ID]:
            user_info[ID]["month"] = MONTHS_SHORT.index(word) + 1
        elif word in MONTHS and "month" not in user_info[ID]:
            user_info[ID]["month"] = MONTHS.index(word) + 1
        elif "days" not in user_info[ID]:
            for key in DAYS:
                if word in DAYS[key]:
                    user_info[ID]["day"] = key
            for ext in EXTENSIONS:
                if ext in word:
                    slice = word.find(ext)
                    if slice > 0:
                        try:
                            user_info[ID]["date"] = int(word[:slice])
                        except Exception as e:
                            print(e)
                            pass
            #if date given is just an integer
            if word.isdigit() and 1 <= len(word) <= 2:
                user_info[ID]["date"] = int(word)
    difference = None            
    #check for next days, if day info is not present, user may have used "tomorrow", "next week"
    if "day" in user_info[ID]:
        difference = user_info[ID]["day"] - day_of_week
        if difference < 0:
            difference += 7
        if skip_count > 0:
            difference += (skip_count * 7)    
        adv_date = today + timedelta(days=difference)
        print(adv_date)
    else:
        if "tomorrow" in tokens or "tmr" in tokens or "tmrw" in tokens:
            adv_date = today + timedelta(days=1)
        elif "today" in tokens:
            adv_date = today
            is_today = True
        elif set_month == True:
            adv_date = today + relativedelta(months=skip_count)
        elif set_year == True:
            adv_date = today + relativedelta(years=skip_count)
        elif set_week == True:
            print(skip_count)
            if skip_count > 0:
                offset = 7 * skip_count
                adv_date = today + timedelta(days=offset)
                user_info[ID]["day"] = adv_date.weekday()
        elif "month" in user_info[ID] and "date" in user_info[ID]:
            adv_date = datetime(year, user_info[ID]["month"], user_info[ID]["date"])
        else:
            #date has been provided directly
            for word in tokens:
                if "/" in word:
                    date_list = [int(i) for i in word.split("/")]
                    if 2 <= len(date_list) <= 3:
                        if len(date_list) == 3:
                            year_info = str(date_list[2])
                            if len(year_info) == 2:
                                curr_year = int(str(year)[2:])
                                diff = date_list[2] - curr_year
                                year += diff
                            elif len(year_info) == 4:
                                year = int(year_info)
                                if get_current_time().year > year:
                                    raise YearError
                            else:
                                raise(YearError)
                        day_info = str(date_list[0])
                        if len(day_info) <= 2 and 0 < int(day_info) < 32:
                            day = int(day_info)
                        else:
                            raise(DayError)
                        month_info = str(date_list[1])
                        if len(month_info) <= 2 and 0 < int(month_info) < 13:
                            month = int(month_info)
                        else:
                            raise(MonthError)
                        #create date, if date is invalid, a value error will be raised
                        adv_date = datetime(year, month, day)
    #if event falls on the same day, do not set earlier timing            
    if "every" in tokens:
        user_info[ID]["set_repeating"] = True
    else:
        user_info[ID]["set_repeating"] = False

    if adv_date != None:
        if adv_date.date() == today.date():
            is_today = True
        set_date = adv_date.date()
        
    if "time" in user_info[ID]:
        adv_time = process_time(user_info[ID]["time"], is_today)
    
    if adv_date != None:
        if adv_time != None:
            combined_datetime = datetime.combine(set_date, adv_time)
            if get_current_time().date() > set_date:
                print("The current date is " + str(get_current_time().date()) + " but date specified " + str(adv_date.date()) + ".")
                print("Offsetting reminder by 1 year.")
                if "day" in user_info[ID]:
                    offset_date = datetime(year + 1, user_info[ID]["month"], user_info[ID]["day"]).date()
                    combined_datetime = datetime.combine(offset_date, adv_time)
                    return tz.localize(combined_datetime)
                elif "date" in user_info[ID] and "month" in user_info[ID]:
                    offset_date = datetime(year + 1, user_info[ID]["month"], user_info[ID]["date"]).date()
                    combined_datetime = datetime.combine(offset_date, adv_time)
                    return tz.localize(combined_datetime)
                else:
                    combined_datetime = combined_datetime + relativedelta(years=1)
                    return tz.localize(combined_datetime)
            elif get_current_time() > tz.localize(combined_datetime):
                if difference != None:
                    if difference == 0:
                        print("The current date is " + str(get_current_time().date()) + " but date specified was " + str(combined_datetime.date()) + ".")
                        print("Offsetting reminder by 1 week.")
                        combined_datetime = combined_datetime + timedelta(days=7)
                        return tz.localize(combined_datetime)
                        #offsetting reminder by 1 week
                else:
                    raise(SetTimeError) #date provided is in the past
            else:
                return tz.localize(combined_datetime)
        else:
            print("Time info not specified.")
            return "time"
    else:
        print(user_info)
        if "month" in user_info[ID] and "day" not in user_info[ID]:
            return "date"
        elif "month" not in user_info[ID] and "date" in user_info[ID]:
            if adv_time != None:
                #event is assumed to be for this month, otherwise, the next month
                current_month = get_current_time().month
                combined_datetime = datetime.combine(datetime(year, current_month, user_info[ID]["date"]), adv_time)
                if get_current_time() > tz.localize(combined_datetime):
                    print("The current date is " + str(get_current_time().date()) + " but date specified was " + str(combined_datetime.date()) + ".")
                    print("Offsetting reminder by 1 month.")
                    combined_datetime += relativedelta(months=1)
                    return tz.localize(combined_datetime)
                else:
                    return tz.localize(combined_datetime)
            else:
                print("Time info not specified.")
                return "time"
        elif "month" not in user_info[ID] and "day" not in user_info[ID]:
            if adv_time != None:
                combined_datetime = datetime.combine(get_current_time().date(), adv_time)
                if get_current_time() > tz.localize(combined_datetime):
                    print("The current time is " + str(get_current_time().time()) + " but time specified was " + str(combined_datetime.time()) + ".")
                    print("Offsetting reminder by 1 day.")
                    combined_datetime += timedelta(days=1)
                    return tz.localize(combined_datetime)
                else:
                    return tz.localize(combined_datetime)
            else:
                print(user_info)
                print("Date and time info not specified.")
                return "all"

def get_event(text):
    stop_words = ["tmr", "tomorrow", "every", "tmrw", "next", "today", "week", "month", "this", "on"]
    event_title = None
    tokenize_raw = word_tokenize(text)
    tokens_lower = []
    for word in tokenize_raw:
        try:
            tokens_lower.append(word.lower())
        except AttributeError:
            tokens_lower.append(word)
    tagged = nltk.pos_tag(tokens_lower)
    print(tagged)
    intents = []
    preposition = []
    filter_words = ["send", "make"]

    for i in range(len(tagged)):
        set = tagged[i]
        if set[1] == "VB" or set[1] == "VBN":
            intents.append(i)
        if set[1] == "IN":
            preposition.append(i)
    
    if len(intents) >= 2:
        start = intents[1]
    elif len(intents) == 1:
        start = intents[0]
    else:
        start = 0

    for filter_word in filter_words:
        if filter_word == tokens_lower[0]:
            start = 0
            break

    end_index = None
    found_extension = False
    slice_start = tokens_lower[start:]
    update_tagged = tagged[start:]
    days = []
    for key, value in DAYS.items():
        day_list = value
        for day in day_list:
            days.append(day)

    ALL_MONTHS = MONTHS + MONTHS_SHORT

    for word in slice_start:
        if word in stop_words or word in days or word in ALL_MONTHS:
            end_index = slice_start.index(word)
            if end_index >= 1:
                if slice_start[end_index - 1].isdigit() and 1 <= len(slice_start[end_index - 1]) <= 2:
                    end_index = slice_start.index(word) - 1
                    break
                else:
                    break
            else:
                break

        if "am" in word or "pm" in word:
            if len(word) == 2:
                end_index = slice_start.index(word) - 1
            else:
                #check if it is a valid digit
                if word[0:len(word) - 2].isdigit():
                    end_index = slice_start.index(word)
                    break

        if "/" in word or "." in word or ":" in word:
            end_index = slice_start.index(word)
            break
        
        if word.isdigit() and len(word) == 4:
            end_index = slice_start.index(word)
            break
        
        for ext in EXTENSIONS:
            if ext in word:
                if word[0:len(word) - 2].isdigit():
                    end_index = slice_start.index(word)
                    found_extension = True
                    break

        if found_extension:
            break

    #no details have been detected
    if end_index == None:
        end_index = len(slice_start)
    
    preposition = [i - start for i in preposition]
    preposition.append(len(slice_start) - 1) #update with the last element of the list
    set_preposition = None
    is_time_data = False

    if len(preposition) >= 2:
        for i in range(len(preposition) - 1):
            for j in range(preposition[i], preposition[i + 1] + 1):
                if slice_start[j] in stop_words or slice_start[j] in days:
                    set_preposition = i
                    is_time_data = True
                    print(slice_start[j])
                    break
                if update_tagged[j][1] == "CD":
                    set_preposition = i
                    is_time_data = True
                    break
            if is_time_data:
                break

    if set_preposition == None:
        prep_end = end_index
    else:
        prep_end = preposition[set_preposition]
        if end_index - prep_end != 1:
            prep_end = end_index
        
    if end_index == None or prep_end == None:
        prep_end = len(slice_start)
    
    slice_end = slice_start[:prep_end]
    event_title = slice_end
    #filter unnecessary command phrases
    event_string = " ".join(event_title)
    new_event_title = []
    new_title = False

    for phrase in FILTERS:
        if phrase in event_string or phrase == event_string:
            words = phrase.split()
            new_event_title = [x for x in event_title if x not in words]
            new_title = True
            break

    if len(event_title) == 0:
        new_event_title = ["appointment"]
    elif new_title == True and len(new_event_title) == 0:
        new_event_title = ["appointment"]
    else:
        new_event_title = event_title

    new_event_title = " ".join(new_event_title)
    reminder_details = slice_start[end_index:]
    return new_event_title, reminder_details


def convert_date(date_str):
    date_info = date_str.split("/")
    day = date_info[0]
    month = date_info[1]
    year = date_info[2]
    ext = "th"
    if int(day) in ADD_EXTENSION:
        ext = ADD_EXTENSION[int(day)]
    else:
        if int(day[-1]) in ADD_EXTENSION:
            ext = ADD_EXTENSION[int(day[-1])] 
    day = str(int(day)) + ext
    month_name = MONTHS[int(month) - 1].capitalize()
    full_date = day + " " + month_name + " " + year
    return full_date


def display_reminders(msg, send_message):
    userID = msg.chat.id
    entry = event_collection.find_one({"_id": userID})
    reminders = "*Your saved reminders:*"
    job_IDs = []
    reminder_count = 0
    if entry != None:
        data = entry["reminders"]
        if data:
            for key, value in data.items():
                date_time = utc_to_local(value[2])
                ID_pair = []
                ID_pair.append(key)
                reminder_count += 1
                event_title = value[0]
                notes = value[1]
                adv_memo = value[3]
                set_repeat = value[4]
                second_id = value[5]
                time = date_time.strftime("%I:%M %p")
                date = calendar.day_name[date_time.weekday()] + " (" + date_time.strftime("%d/%m/%Y") + ")" 
                ID_pair.append(second_id)

                if set_repeat:
                    event_title += " 🔄"
                    date = "Weekly"
                else:
                    date = calendar.day_name[date_time.weekday()] + " (" + date_time.strftime("%d/%m/%Y") + ")"

                if notes != None:
                    result = "*" + str(reminder_count) + ". " + event_title + "*\n\n_Date:_     " + date + "\n_Time:_     " + time + "\n_Notes:_     " + notes + "\n_Alerts:_     " + adv_memo
                else:
                    result = "*" + str(reminder_count) + ". " + event_title + "*\n\n_Date:_     " + date + "\n_Time:_     " + time + "\n_Alerts:_     " + adv_memo
                reminders = reminders + "\n\n" + result
                job_IDs.append(ID_pair)
            return [job_IDs, reminders]
        else:
            if send_message:
                bot.send_message(userID, reminders + "\n\n_No more reminders liao!_")
            return False
    else:
        if send_message:
            bot.send_message(userID, reminders + "\n\n_No more reminders liao!_")
        return False


#Generate the display for reminders
def markup_reminder(date_time, title):
    date = convert_date(date_time.strftime("%d/%m/%Y"))
    time = date_time.strftime("%I:%M %p")
    day = str(calendar.day_name[date_time.weekday()])
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton(title, callback_data="none"))
    markup.add(InlineKeyboardButton(day, callback_data="none"), InlineKeyboardButton(str(date), callback_data="none"))
    markup.add(InlineKeyboardButton(str(time), callback_data="none"))
    return markup


def gen_time_options():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    button1 = types.KeyboardButton("10 minutes")
    button2 = types.KeyboardButton("30 minutes")
    button3 = types.KeyboardButton("1 hour")
    button4 = types.KeyboardButton("2 hours")
    button5 = types.KeyboardButton("1 day")
    button6 = types.KeyboardButton("Night before")
    button7 = types.KeyboardButton("Cancel")
    markup.add(button1, button2, button3, button4, button5, button6, button7)
    return markup


def gen_note_options():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    button1 = types.KeyboardButton("Yes")
    button2 = types.KeyboardButton("No")
    button3 = types.KeyboardButton("Cancel")
    markup.add(button1, button2, button3)
    return markup


def gen_edit_options(list):
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    count = 0
    markup.add(types.KeyboardButton("Delete all"))
    for id_pair in list:
        count += 1
        button = types.KeyboardButton(str(count))
        markup.add(button)
    markup.add("Exit")
    return markup


def gen_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    button1 = types.KeyboardButton("✏️ Edit")
    button2 = types.KeyboardButton("❌ Cancel")
    button3 = types.KeyboardButton("📄 My Reminders")
    markup.add(button1, button2, button3)
    return markup


def gen_uuid(title):
    compressed = "".join(title.split())
    return compressed + str(uuid.uuid4())[0:5]


def generate_reminder(date_time, adj_time, title, userID, notes, advance, memo, repeat):
    job_id1 = gen_uuid(title)
    job_id2 = gen_uuid(title)
    
    entry = event_collection.find_one({"_id": userID})

    if entry != None:
        #{uniqueID : [event title, notes, datetime]}
        event_collection.update_one({"_id": userID}, {"$set":{"reminders." + job_id1: [title, notes, date_time, memo, repeat, job_id2]}}) 
    else:
        event_collection.insert_one({"_id": userID, "reminders": {job_id1: [title, notes, date_time, memo, repeat, job_id2]}})

    if notes != None:
        attached_notes = True
    else:
        attached_notes = False

    if not repeat:
        scheduler.add_job(notify, next_run_time=date_time, args=[job_id1, userID, title, date_time, "now", attached_notes, notes, repeat], jobstore="mongo", replace_existing=True, id=job_id1, misfire_grace_time=30)
        scheduler.add_job(notify, next_run_time=adj_time, args=[job_id2, userID, title, date_time, advance, attached_notes, notes, repeat], jobstore="mongo", replace_existing=True, id=job_id2, misfire_grace_time=30)
    else:
        day_actual = int(date_time.weekday())
        hour_actual = int(date_time.hour)
        minute_actual = int(date_time.minute)
        day_adj = int(adj_time.weekday())
        hour_adj = int(adj_time.hour)
        minute_adj = int(adj_time.minute)
        scheduler.add_job(notify, args=[job_id1, userID, title, date_time, "now", attached_notes, notes, repeat], trigger="cron", hour=hour_actual, minute=minute_actual, day_of_week=day_actual, jobstore="mongo", id=job_id1, replace_existing=True, misfire_grace_time=30)
        scheduler.add_job(notify, args=[job_id2, userID, title, date_time, advance, attached_notes, notes, repeat], trigger="cron", hour=hour_adj, minute=minute_adj, day_of_week=day_adj, jobstore="mongo", id=job_id2, replace_existing=True, misfire_grace_time=30)
    scheduler.print_jobs()


def notify(job_id, userID, title, date_time, advance, attached_notes, notes, repeat):
    bot.send_message(userID, "Your appointment starts " + advance + "!", reply_markup=markup_reminder(date_time, title))
    if not repeat:
        event_collection.update_one({"_id": userID}, {"$unset":{"reminders." + str(job_id): ""}}) 
    if attached_notes:
        bot.send_message(userID, "📝 " + notes)
    scheduler.print_jobs()


@bot.message_handler(commands=["start"])
def send_welcome(message):
    id = message.chat.id
    username = message.from_user.first_name
    bot.send_message(id, "Hello " + username + "!\n\nI'm *Don'tForgetAh Bot* 🇸🇬\n\nI can help you schedule reminders for events or appointments with a Singaporean twist. ⏰\n\nSimply send me a text using natural language!\
    \n\nTo set a reminder, send me a message like\n\n- _remind me to go to work on the 9th oct_\n- _school tmr at 9am_\n- _exam on 2/8 at 1500_\n- _water the plants every tues at 8am_\
    \n- _dentist appointment next fri 10:00am_\
    \n\nIf you need any help, enter the */help* command for more details.", reply_markup=gen_menu())


@bot.message_handler(commands=["help"])
def gen_help_menu(message):
    id = message.chat.id
    bot.send_message(id, WELCOME_MESSAGE, disable_web_page_preview=True)


@bot.message_handler(content_types=["text"], func=lambda message: message.text == "📄 My Reminders")
def show_reminders(message):
    has_reminders = display_reminders(message, True)
    if has_reminders != False:
        reminders = display_reminders(message, True)[1]
        bot.send_message(message.chat.id, reminders)


@bot.message_handler(content_types=["text"], func=lambda message: message.text == "✏️ Edit")
def edit_reminders(message):
    userID = message.chat.id
    has_reminders = display_reminders(message, True)
    if has_reminders != False:
        job_IDs = has_reminders[0]
        reminders = has_reminders[1]
        if userID not in user_info:
            user_info[userID] = {}
        user_info[userID]["state"] = "editing"
        user_info[userID]["job"] = job_IDs
        reminder_list = bot.send_message(userID, reminders) 
        user_info[userID]["edit_message_id"] = reminder_list.message_id
        bot.send_message(userID, "\n\n✏️ Choose the reminder(s) you want to remove.", reply_markup=gen_edit_options(job_IDs))
    

def reminder_setting(message):
    id = message.chat.id
    if id not in user_info:
        user_info[id] = {"state": 0}
        return True
    else:
        if "state" in user_info[id]:
            if user_info[id]["state"] == 0:
                return True
            else:
                return False
        else:
            return False

#func=lambda message: bug_reporting(message)
@bot.message_handler(content_types=["text"], func=lambda message: reminder_setting(message))
def process_text(message):
    event_title = ""
    result = None
    #add new entry to the dictionary
    id = message.chat.id
    if message.text == "❌ Cancel":
        bot.send_message(id, generate_random(GREETING), reply_markup=gen_menu())
        if id in user_info:
            del user_info[id]
    else:
        input_details = []
        for word in message.text.split():
            try:
                input_details.append(word.lower())
            except AttributeError:
                input_details.append(word)
        if "title" not in user_info[id] and "details" not in user_info[id]:
            try:
                event_title, details = get_event(message.text)
                event_title = event_title.title()
                user_info[id]["details"] = details
                user_info[id]["title"] = event_title
            except Exception as e:
                print(e)
                bot.send_message(id, "Hmm, I didn't get that, please try again.")
                print(user_info[id])
                update_input = [elem for elem in user_info[id]["details"] if elem not in input_details]
                user_info[id]["details"] = update_input
                print(user_info[id]["details"])
        else:  
            user_info[id]["details"].extend(input_details)
        if "details" in user_info[id] and "title" in user_info[id]:
            has_exception = False
            updated_details = user_info[id]["details"]
            print(updated_details)
            try:
                result = create_reminder(updated_details, id)
                repeat_reminder = user_info[id]["set_repeating"]                        
                if isinstance(result, datetime):
                    print("Successfully generated datetime object " + str(result))
                    bot.send_message(id, "Alright, here's your new event okay?", reply_markup=markup_reminder(result, user_info[id]["title"]))
                    if repeat_reminder:
                        bot.send_message(id, "This reminder will repeat every week hor! 🔄")
                    user_info[id]["reminder_time"] = result
                    user_info[id]["state"] = 1
                    bot.send_message(id, "You want add note? 📝", reply_markup=gen_note_options())
                else:
                    if result == "date":
                        bot.send_message(id, generate_random(DATE_QUERY))
                    elif result == "time":
                        bot.send_message(id, generate_random(TIME_QUERY))
                    elif result == "all":
                        bot.send_message(id, generate_random(DETAILS_QUERY))
            except MonthError:
                has_exception = True
                bot.send_message(id, "The month like wrong leh, can try again pls? 😅")
            except DayError:
                has_exception = True
                bot.send_message(id, "The day like not correct leh, can try again pls? 😅")
            except SetTimeError:
                has_exception = True
                bot.send_message(id, "I not time traveller la 😅 Can tell me a date for next time pls?")
            except TimeError:
                has_exception = True
                bot.send_message(id, "The format of your timing abit off, can try again pls? 😅")
            except YearError:
                has_exception = True
                bot.send_message(id, "I not time traveller la 😅 Can tell me a year in the present pls?")
            except ValueError:
                has_exception = True
                bot.send_message(id, "This date like not correct leh, can try again?")
            except Exception as e:
                has_exception = True
                print(e)
                bot.send_message(id, "Aiyo, sorry, I didn't get that 😅 Can try send me again?")

            if has_exception:
                update_input = [elem for elem in user_info[id]["details"] if elem not in input_details]
                user_info[id]["details"] = update_input
                print(user_info[id]["details"])
        

def edit_reminder(message):
    id = message.chat.id
    if id in user_info:
        if user_info[id]["state"] == "editing":
            return True
        else:
            return False
    else:
        return False


@bot.message_handler(content_types=["text"], func=lambda message: edit_reminder(message))
def edit_reminder_list(message):
    #handle erroneous responses from user
    id = message.chat.id
    if "job" in user_info[id]:
        id_list = user_info[id]["job"]
        print(id_list)
    print(user_info[id])

    choice = message.text
    reminders_id = user_info[id]["edit_message_id"]
    if choice == "Delete all":
        print(id_list)
        for i in id_list:
            event_collection.update_one({"_id": id}, {"$unset":{"reminders." + str(i[0]): ""}}) 
            try:
                scheduler.remove_job(i[0], jobstore="mongo")
                scheduler.remove_job(i[1], jobstore="mongo")
            except Exception as e:
                print(e)
                continue
        has_reminders = display_reminders(message, False)

        if has_reminders != False:
            reminders = has_reminders[1]
        else:
            reminders = "*Your saved reminders:*\n\n_No more reminders liao!_"   

        print(reminders)
        bot.edit_message_text(chat_id=id, message_id=reminders_id, text=reminders)
        bot.send_message(id, "I delete all your reminders alr ah! ✅", reply_markup=gen_menu())
        del user_info[id]
    elif choice == "Exit":
        bot.send_message(id, generate_random(GREETING), reply_markup=gen_menu())
        del user_info[id]
    elif choice.isdigit():
        if 1 <= int(choice) <= len(id_list):
            i = id_list[int(choice) - 1]
            event_collection.update_one({"_id": id}, {"$unset":{"reminders." + str(i[0]): ""}})  
            user_info[id]["job"].remove(i)
            try:
                scheduler.remove_job(i[0], jobstore="mongo")
                scheduler.remove_job(i[1], jobstore="mongo")
            except:
                pass

            has_reminders = display_reminders(message, False)

            if has_reminders:
                reminders = has_reminders[1]
            else:
                reminders = "*Your saved reminders:*\n\n_No more reminders liao!_"

            bot.edit_message_text(chat_id=id, message_id=reminders_id, text=reminders)

            if has_reminders:
                bot.send_message(id, "Okay! Deleted alr! ✅", reply_markup=gen_edit_options(has_reminders[0]))
            else:
                bot.send_message(id, "I delete all your reminders alr ah! ✅", reply_markup=gen_menu())
                del user_info[id]
        else:
            bot.send_message(id, "Sorry ah I don't understand what you mean, select a time from my buttons.")
    else:
        bot.send_message(id, "Sorry ah I don't understand what you mean, select a time from my buttons.")


def add_note(message):
    id = message.chat.id
    if id in user_info:
        if user_info[id]["state"] == 1:
            return True
        else:
            return False
    else:
        return False


@bot.message_handler(content_types=["text"], func=lambda message: add_note(message))
def create_note(message):
    id = message.chat.id
    if "make_note" not in user_info[id]:
        user_info[id]["make_note"] = False

    make_note = user_info[id]["make_note"]

    if not make_note:
        if message.text == "Yes" or message.text == "yes":
            bot.send_message(id, "Write your note in the next message okay?")
            user_info[id]["make_note"] = True
            make_note = True
        elif message.text == "No" or message.text == "no":
            user_info[id]["make_note"] = False
            bot.send_message(id, "How early you want me to remind you ah?", reply_markup=gen_time_options())
            user_info[id]["state"] = 2
        elif message.text == "Cancel":
            bot.send_message(id, generate_random(GREETING), reply_markup=gen_menu())
            del user_info[id]
        else:
            bot.send_message(id, "Sorry ah I don't understand what you mean, select an option from my buttons.")
    else:
        note = message.text
        user_info[id]["note"] = note
        bot.send_message(id, "How early you want me to remind you ah?", reply_markup=gen_time_options())
        user_info[id]["state"] = 2


timings = {"10 minutes": ["in 10 minutes", 10, "10 minutes before"], 
           "30 minutes": ["in 30 minutes", 30, "30 minutes before"], 
           "1 hour": ["in 1 hour", 60, "1 hour before"], 
           "2 hours": ["in 2 hours", 120, "2 hours before"], 
           "1 day": ["tomorrow", 1440, "1 day before"]}

#Callback handler for reminder setting
def set_timing(timing):
    id = timing.chat.id
    if id in user_info:
        if user_info[id]["state"] == 2:
            return True
        else:
            return False
    else:
        return False


@bot.message_handler(content_types=["text"], func=lambda timing: set_timing(timing))
def set_time(timing):
    id = timing.chat.id
    time_data = timing.text
    set_repeating = user_info[id]["set_repeating"]
    if "note" in user_info[id]:
        note = user_info[id]["note"]
    else:
        note = None

    if time_data in timings or time_data == "Night before":
        title = user_info[id]["title"]
        date_time = user_info[id]["reminder_time"]
        if time_data == "Night before":
            advance_text = "tomorrow"
            advance_memo = "8pm the day before"
            day_before = date_time.date() - timedelta(days=1)
            adj_time = datetime.combine(day_before, time(20, 0, 0))
            print(adj_time)
        else:
            advance = timings[time_data][1]
            advance_text = timings[time_data][0]
            advance_memo = timings[time_data][2]
            adj_time = date_time - timedelta(minutes=advance)

        generate_reminder(date_time, adj_time, title, id, note, advance_text, advance_memo, set_repeating)
        bot.send_message(id, "Steady la! Your reminder saved alr! ✅", reply_markup=gen_menu())
        del user_info[id]

    elif time_data == "Cancel":
        bot.send_message(id, generate_random(GREETING), reply_markup=gen_menu())
        del user_info[id]
    else:
        bot.send_message(id, "Sorry ah I don't understand what you mean, select a time from my buttons okay?")


@bot.callback_query_handler(func=lambda x: True)
def handle_unknown_callbacks(call):
    bot.answer_callback_query(call.id, text=False, show_alert=False)

scheduler.start()
scheduler.print_jobs()

bot.polling(True)

@server.route("/" + TOKEN, methods=["POST"])
def getMessage():
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200


@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url="https://nlp-reminders-bot.herokuapp.com/" + TOKEN)
    return "!", 200


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))