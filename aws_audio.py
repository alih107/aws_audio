from flask import Flask, request, jsonify
import requests
import xml.etree.ElementTree as ET
from wit import Wit
from pydub import AudioSegment
import os
import logging
import sys
import linecache
import constants

app = Flask(__name__)
uuid = constants.uuid
api_key = constants.api_key
client = Wit(constants.wit_token)
logging.basicConfig(filename='log_audio.log', level=logging.INFO,
                    format='[%(levelname)s] (%(threadName)-10s) %(message)s')

def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    return 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)

def yandex_api_post(voice_filename_wav, topic, lang=None):
    headers = {'Content-Type': 'audio/x-wav'}
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

@app.route('/bot_audio', methods=['POST'])
def handle_incoming_messages():
    try:
        data = request.json
        logging.info(data)
        voice_url, topic, source, sender = data['url'], data['topic'], data['source'], data['id']
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
        if source == 'telegram':
            AudioSegment.from_file(voice_filename, "ogg").export(voice_filename_wav, format="wav")
            if topic == 'queries':
                try:
                    resp = client.speech(open(voice_filename_wav, 'rb'), None, {'Content-Type': 'audio/wav'})
                    logging.info(resp)
                    os.remove(voice_filename_wav)
                    os.remove(voice_filename)
                    return jsonify(resp), 200
                except:
                    logging.info(PrintException())
                    os.remove(voice_filename)
                    os.remove(voice_filename_wav)
                    return 404
        elif source == 'facebook':
            try:
                AudioSegment.from_file(voice_filename, "mp4").export(voice_filename_wav, format="wav")  # android
            except:
                AudioSegment.from_file(voice_filename, "aac").export(voice_filename_wav, format="wav")  # iphone

        r = yandex_api_post(voice_filename_wav, topic)
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
            return jsonify({'numbers': yandex_numbers}), 200
        elif topic == 'queries':
            try:
                resp = client.message(root[0].text)
            except:
                return 404
            if source == 'telegram':
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
                    return jsonify({'intent': intent}), 200
                else:
                    return 404

        return jsonify({'message': 'idi nahui'}), 404
    except:
        logging.error(PrintException())
        return 404

if __name__ == '__main__':
    app.run(debug=True)
