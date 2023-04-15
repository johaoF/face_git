import os
import sys
import json
from datetime import datetime
from google.cloud import dialogflow_v2 as dialogflow

import requests
from flask import Flask, request

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/clave.json"
project_id = 'barrestaurante-eltri-ngul-xpxa'
session_id = 'me'

session_client = dialogflow.SessionsClient()
session_path = session_client.session_path(project_id, session_id)

app = Flask(__name__)


@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["FB_VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200

@app.route('/', methods=['POST'])
def webhook():

    # endpoint for processing incoming messaging events

    data = request.get_json()
    if data["object"] == "page":

        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:

                if messaging_event.get("message"):  # someone sent us a message

                    sender_id = messaging_event["sender"]["id"]        # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"]["id"]  # the recipient's ID, which should be your page's facebook ID
                    message_text = messaging_event["message"]["text"]  # the message's text
                    tx=message_text
                    text_input = dialogflow.TextInput(text=tx, language_code="es-ES")
                    query_input = dialogflow.QueryInput(text=text_input)

                    response = session_client.detect_intent(session=session_path, query_input=query_input)

                    fulfillment_messages = response.query_result.fulfillment_text
                    
                send_message(sender_id, fulfillment_messages)

                if messaging_event.get("delivery"):  # delivery confirmation
                    pass

                if messaging_event.get("optin"):  # optin confirmation
                    pass

                if messaging_event.get("postback"):  # user clicked/tapped "postback" button in earlier message
                    pass

    return "ok", 200

def send_message(recipient_id, message_text):
    params = {
         "access_token": os.environ["FB_PAGE_ACCESS_TOKEN"]
    }
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        'recipient': {
            'id': recipient_id
        },
        'message': {
            'text': message_text
        }
    }
    response = requests.post('https://graph.facebook.com/v16.0/me/messages', params=params, headers=headers, data=json.dumps(data))
    if response.status_code != 200:
        print('Error al enviar el mensaje: ' + response.text)
