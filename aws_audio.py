from flask import Flask, request, jsonify
import requests
import xml.etree.ElementTree as ET
from wit import Wit
from pydub import AudioSegment
import os
import logging
import sys
import linecache
import time
import constants
from datetime import datetime
from pytz import timezone, utc

def customTime(*args):
    utc_dt = utc.localize(datetime.utcnow())
    my_tz = timezone("Asia/Almaty")
    converted = utc_dt.astimezone(my_tz)
    return converted.timetuple()

app = Flask(__name__)
uuid = constants.uuid
api_key = constants.api_key
client = Wit(constants.wit_token)
logging.Formatter.converter = customTime
logging.basicConfig(filename='log_audio.log', level=logging.INFO,
                    format='[%(levelname)s] %(asctime)s (%(threadName)-10s) %(message)s',
                    datefmt = '%m/%d/%Y %H:%M:%S')

def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    return 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)

def yandex_api_post(voice_filename_wav, topic, lang=None, audio_type=None):
    headers = {'Content-Type': 'audio/x-mpeg-3'}
    if audio_type:
        headers = {'Content-Type': audio_type}
    url = 'http://asr.yandex.net/asr_xml?uuid=' + uuid + '&key=' + api_key + '&topic=' + topic
    if lang == 'en-US':
        url += '&lang=' + lang
    return requests.post(url, data=open(voice_filename_wav, 'rb'), headers=headers)
def extract_digits(message):
    numbers = '0123456789'
    for i in message:
        if not i in numbers:
            message = message.replace(i, '')
    return message

@app.route('/bot_audio', methods=['GET'])
def handle_get_messages():
    try:
        logging.info('GOT GET MESSAGE')
        incoming_time = request.args.get('time')
        return incoming_time + " | " + str(time.time())
    except:
        logging.info(PrintException())
        return 'Hello world! no time!'

@app.route('/bot_audio', methods=['POST'])
def handle_incoming_messages():
    log_message = ''
    try:
        data = request.json
        #logging.info(data)
        voice_url, topic, source, sender = data['url'], data['topic'], data['source'], data['id']
        log_message += topic + ' | ' + source + ' | '
        g = requests.get(voice_url, stream=True)
        count = 0
        while g.status_code != 200 and count < 10:
            g = requests.get(voice_url, stream=True)
            count += 1
        if g.status_code != 200:
            return 404

        voice_filename = "voice_" + sender + ".mp4"
        voice_filename_wav = "voice_" + sender + ".wav"
        with open(voice_filename, "wb") as o:
            o.write(g.content)
        if source == 'telegram' and topic == 'test_queries':
            start = time.time()
            AudioSegment.from_file(voice_filename, "ogg").export(voice_filename_wav, format="mp3")
            resp = client.speech(open(voice_filename_wav, 'rb'), None, {'Content-Type': 'audio/mpeg3'})
            logging.info('client.speech with audio/mpeg3 = ' + str(time.time() - start))

            start = time.time()
            AudioSegment.from_file(voice_filename, "ogg").export(voice_filename_wav, format="wav")
            resp = client.speech(open(voice_filename_wav, 'rb'), None, {'Content-Type': 'audio/wav'})
            logging.info('client.speech with audio/wav = ' + str(time.time() - start))
            return jsonify(resp), 200
        if source == 'telegram':
            AudioSegment.from_file(voice_filename, "ogg").export(voice_filename_wav, format="mp3")
        elif source == 'facebook':
            try:
                AudioSegment.from_file(voice_filename, "mp4").export(voice_filename_wav, format="mp3")  # android
            except:
                AudioSegment.from_file(voice_filename, "aac").export(voice_filename_wav, format="mp3")  # iphone

        if source == 'telegram' and topic == 'queries':
            try:
                resp = client.speech(open(voice_filename_wav, 'rb'), None, {'Content-Type': 'audio/mpeg3'})
                logging.info(log_message + str(resp))
                os.remove(voice_filename_wav)
                os.remove(voice_filename)
                return jsonify(resp), 200
            except:
                logging.error(log_message + PrintException())
                os.remove(voice_filename)
                os.remove(voice_filename_wav)
                return 404

        start = time.time()
        r = yandex_api_post(voice_filename_wav, topic)
        if r.status_code != 200:
            return 404
        logging.info('yandex_api_post time = ' + str(time.time() - start))
        logging.info(r.text)
        try:
            os.remove(voice_filename)
            os.remove(voice_filename_wav)
        except:
            pass
        root = ET.fromstring(r.text)
        if root.attrib['success'] == '0':
            return 404
        if topic == 'numbers':
            yandex_numbers = extract_digits(root[0].text)
            logging.info(log_message + yandex_numbers)
            return jsonify({'numbers': yandex_numbers}), 200
        elif topic == 'queries':
            try:
                resp = client.message(root[0].text)
            except:
                logging.info(log_message + PrintException())
                return 404
            if source == 'telegram':
                logging.info(log_message + str(resp))
                return jsonify(resp), 200
            elif source == 'facebook':
                entities = resp['entities']
                if 'intent' in entities:
                    max_confidence = -1
                    intent = ''
                    for i in entities['intent']:
                        if i['confidence'] > max_confidence:
                            max_confidence = i['confidence']
                            intent = i['value']
                    logging.info(log_message + 'intent = ' + intent)
                    return jsonify({'intent': intent}), 200
                else:
                    return 404

        logging.info(log_message + 'shit happened')
        return 404
    except:
        logging.info(log_message + PrintException())
        return 404

if __name__ == '__main__':
    app.run(debug=True)
