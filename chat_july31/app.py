from flask import Flask, render_template, request, jsonify
import re
import random
import pandas as pd

app = Flask(__name__)

# Load the CSV file
df = pd.read_csv('data/claims_data.csv')

class RuleBot:
    def __init__(self):
        self.intent_responses = {
            'lodge_claim_intent': self.lodge_claim_intent,
            'track_claim_status_intent': self.track_claim_status_intent,
            'greeting_intent': self.greeting_intent,
            'offer_options_intent': self.offer_options_intent,
            'no_match_intent': self.no_match_intent,
            'end_conversation_intent': self.end_conversation_intent,
            'rating_intent': self.rating_intent
        }
        self.intents = {
            'lodge_claim_intent': r'.*\blodge\b.*\bclaim\b.*',
            'track_claim_status_intent': r'.*\b(track|status|claim status)\b.*',
            'greeting_intent': r'.*\b(hi|hello|hey|how are you|good day|greetings|what\'s up|howdy|how do you do|evening|good morning|good afternoon)\b.*',
            'offer_options_intent': r'.*\b(menu|report|help|assist|question|questions|guide|what to do|yes|confused|confuse|confusion|options|options)\b.*',
            'end_conversation_intent': r'.*\b(bye|goodbye|quit|exit|end|terminate|stop|no more|farewell|see you|take care|ciao|no)\b.*',
            'rating_intent': r'.*\b(\d\s?star\b).*'
        }
        self.affirmative_responses = ['yes', 'y', 'sure', 'of course', 'yes you are right', 'absolutely']
        self.user_state = {}
        self.user_data = {}

    def match_intent(self, message):
        for intent, pattern in self.intents.items():
            if re.search(pattern, message, re.IGNORECASE):
                return intent
        return 'no_match_intent'

    def seamless_intent_switch(self, user_id, new_intent):
        current_state = self.user_state[user_id]['state']
        self.user_state[user_id]['intent'] = new_intent
        print(f"DEBUG: Seamless intent switch to {new_intent} from {current_state}")
        if new_intent == 'lodge_claim_intent' and current_state != 'awaiting_follow_up':
            self.user_state[user_id]['state'] = 'awaiting_incident_description'
            return self.lodge_claim_intent(user_id, "")
        elif new_intent == 'track_claim_status_intent' and current_state != 'awaiting_follow_up':
            self.user_state[user_id]['state'] = 'awaiting_claim_number'
            return self.track_claim_status_intent(user_id, "")
        return self.intent_responses[new_intent](user_id, "")

    def respond(self, user_id, message):
        if user_id not in self.user_state:
            self.user_state[user_id] = {'intent': None, 'state': 'initial'}
            self.user_data[user_id] = {}

        state = self.user_state[user_id]['state']
        intent = self.match_intent(message)
        print(f"DEBUG: Respond: Intent: {intent}, State: {state}, Message: {message}")

        # Check for end conversation intent first
        if intent == 'end_conversation_intent':
            return self.end_conversation_intent(user_id, message)
        if intent == 'rating_intent':
            return self.rating_intent(user_id, message)

        # Check for intent change during conversation or if user asks for menu/report
        if intent in ['lodge_claim_intent', 'track_claim_status_intent', 'offer_options_intent'] and state != 'initial':
            return self.seamless_intent_switch(user_id, intent)

        # Initial State and Intent Handling
        if state == 'initial':
            if intent == 'track_claim_status_intent':
                self.user_state[user_id]['intent'] = intent
                self.user_state[user_id]['state'] = 'awaiting_claim_number'
                return self.track_claim_status_intent(user_id, message)
            elif intent == 'lodge_claim_intent':
                self.user_state[user_id]['intent'] = intent
                self.user_state[user_id]['state'] = 'awaiting_incident_description'
                return self.lodge_claim_intent(user_id, message)
            elif intent == 'greeting_intent':
                self.user_state[user_id]['intent'] = intent
                return self.greeting_intent(user_id, message)
            else:
                self.user_state[user_id]['intent'] = 'offer_options_intent'
                self.user_state[user_id]['state'] = 'awaiting_follow_up'
                return self.offer_options_intent(user_id, message)

        # Handle ongoing states for lodging a claim
        if self.user_state[user_id]['intent'] == 'lodge_claim_intent':
            if state == 'awaiting_incident_description':
                if 'incident_description' not in self.user_data[user_id]:
                    self.user_data[user_id]['incident_description'] = message
                else:
                    self.user_data[user_id]['incident_description'] += ' ' + message

                print(f"DEBUG: Incident description length: {len(self.user_data[user_id]['incident_description'])}")

                if len(self.user_data[user_id]['incident_description']) <= 75:
                    return "Can you provide more details about the incident?"
                else:
                    self.user_state[user_id]['state'] = 'awaiting_incident_date'
                    return "Thank you! When did the incident happen? Choose the date below."

            if state == 'awaiting_incident_date':
                self.user_data[user_id]['incident_date'] = message
                self.user_state[user_id]['state'] = 'awaiting_incident_location'
                return "Thank you! Where did it happen? Be specific with the address."

            if state == 'awaiting_incident_location':
                self.user_data[user_id]['incident_location'] = message
                self.user_state[user_id]['state'] = 'awaiting_policy_number'
                return "Thank you! What is your policy number?"

            if state == 'awaiting_policy_number':
                self.user_data[user_id]['policy_number'] = message
                if self.check_policy_number_exists(message):
                    self.user_state[user_id]['state'] = 'awaiting_driver_name'
                    return "Got it. Lastly, please provide the FIRST NAME of the person involved in the incident."
                else:
                    return ("Sorry, the policy number you entered does not exist.\n" 
                            "Please, enter the correct policy number.")

            if state == 'awaiting_driver_name':
                self.user_data[user_id]['driver_name'] = message
                return self.summarize_claim(user_id)

        # Handle ongoing states for tracking claim status
        if self.user_state[user_id]['intent'] == 'track_claim_status_intent':
            if state == 'awaiting_claim_number':
                self.user_data[user_id]['claim_number'] = message
                if self.check_claim_number(message):
                    self.user_state[user_id]['state'] = 'awaiting_policy_number'
                    return "Thank you! What is your policy number?"
                else:
                    return ("Sorry, you have entered an incorrect claim number.\n" 
                            "Please, enter the correct claim number.")

            if state == 'awaiting_policy_number':
                claim_number = self.user_data[user_id]['claim_number']
                self.user_data[user_id]['policy_number'] = message
                if self.check_policy_number(claim_number, message):
                    self.user_state[user_id]['state'] = 'awaiting_customer_message'
                    return self.show_claim_summary(user_id) + "Provide additional information or a message for @QBE."
                else:
                    return ("Sorry, you have entered an incorrect policy number.\n" 
                            "Please, enter the correct policy number.")

            if state == 'awaiting_customer_message':
                self.user_data[user_id]['customer_message'] = message
                return self.thank_user_for_information(user_id)

        if state in ['awaiting_follow_up', 'initial'] and any(word in message.lower() for word in self.affirmative_responses):
            return self.offer_options_intent(user_id, message)

        if intent in ['lodge_claim_intent', 'track_claim_status_intent']:
            self.user_state[user_id]['intent'] = intent
            self.user_state[user_id]['state'] = 'processing'
            return self.intent_responses[intent](user_id, message)

        self.user_state[user_id]['intent'] = intent
        self.user_state[user_id]['state'] = 'initial'
        return self.intent_responses[intent](user_id, message)

    def show_claim_summary(self, user_id):
        data = self.user_data[user_id]
        claim_number = str(data.get('claim_number', 'N/A')).strip().upper()
        policy_number = str(data.get('policy_number', 'N/A')).strip().upper()
        registration_number = str(data.get('registration_number', 'N/A')).strip().upper()
        driver_name = str(data.get('driver_name', 'N/A')).strip().upper()
        claim_info = df[
            (df['CLAIM'].astype(str).str.upper() == claim_number) & 
            (df['POLICY'].astype(str).str.upper() == policy_number)
        ]

        if not claim_info.empty:
            claim_details = claim_info.iloc[-1]
            summary = (
                f"Here are the details of your claim:<br>\n"
                f"<strong>Claim Number</strong>: {claim_details['CLAIM']}<br>"
                f"<strong>Policy Number</strong>: {claim_details['POLICY']}<br>"
                f"<strong>Registration Number</strong>: {registration_number}<br>"
                f"<strong>Driver Name</strong>: {driver_name}<br>"
                f"<strong>Product</strong>: {claim_details['PRODUCT']}<br>"
                f"<strong>Risk Class</strong>: {claim_details['RISK_CLAS']}<br>"
                f"<strong>Risk Description</strong>: {claim_details['RISK_DESCRIPTION']}<br>"
                f"<strong>Status</strong>: {claim_details['DENIED_DESCRIPTION']}<br>"
                f"<strong>Reported Date</strong>: {claim_details['REPORTED_DATE']}<br>\n"
            )
            return summary
        else:
            self.user_state[user_id]['state'] = 'initial'
            return f"Claim Number: {claim_number}<br>Status: Not Found<br>Details: N/A"

    def thank_user_for_information(self, user_id):
        self.user_state[user_id]['state'] = 'awaiting_follow_up'
        follow_up = (
            "Thank you for the information. Your claim status has been provided above.<br>\n"
            "Is there anything else I can assist you with?"
        )
        return follow_up

    def summarize_claim(self, user_id):
        data = self.user_data[user_id]
        summary = (
            f"Here is the information you provided:<br>\n"
            f"<strong>Incident Description</strong>: {data.get('incident_description', 'N/A')}<br>"
            f"<strong>Incident Date</strong>: {data.get('incident_date', 'N/A')}<br>"
            f"<strong>Incident Location</strong>: {data.get('incident_location', 'N/A')}<br>"
            f"<strong>Policy Number</strong>: {data.get('policy_number', 'N/A')}<br>"
            f"<strong>Registration Number</strong>: {data.get('registration_number', 'N/A')}<br>"
            f"<strong>Person Involved</strong>: {data.get('driver_name', 'N/A')}\n"
        )
        self.user_state[user_id]['state'] = 'awaiting_follow_up'
        follow_up = ("Thank you for the information. Your claim has been lodged successfully. You will receive a confirmation email shortly.\n"
                     "An assessor will now investigate further and may contact you for additional information if required.\n"
                    "Is there anything else I can assist you with?")
        return summary + '<br>' + follow_up

    def check_claim_number(self, claim_number):
        result = not df[df['CLAIM'].astype(str).str.strip().str.upper() == str(claim_number).strip().upper()].empty
        return result

    def check_policy_number(self, claim_number, policy_number):
        df['CLAIM'] = df['CLAIM'].astype(str).str.strip()
        df['POLICY'] = df['POLICY'].astype(str).str.strip()

        claim_number = str(claim_number).strip().upper()
        policy_number = str(policy_number).strip().upper()

        result = not df[
            (df['CLAIM'].astype(str).str.upper() == claim_number) & 
            (df['POLICY'].astype(str).str.upper() == policy_number)
        ].empty

        return result

    def check_policy_number_exists(self, policy_number):
        result = not df[df['POLICY'].astype(str).str.strip().str.upper() == str(policy_number).strip().upper()].empty
        return result

    def lodge_claim_intent(self, user_id, message):
        self.user_state[user_id]['state'] = 'awaiting_incident_description'
        return ("Great! Let’s get this sorted out for you quickly.<br>\n" 
                "Can you tell me a bit about what happened?")

    def track_claim_status_intent(self, user_id, message):
        self.user_state[user_id]['state'] = 'awaiting_claim_number'
        return "To track your claim status, please enter your claim number."

    def greeting_intent(self, user_id, message):
        responses = ["Hello! How can I assist you today?",
                     "Hi there! How can I help you?",
                     "Greetings! How can I assist you with your insurance needs?",
                     "Good day! How can I help you today?"]
        return random.choice(responses)

    def offer_options_intent(self, user_id, message):
        response = "I’ve got several options to help you out. Please choose one of the following:<br>\n"
        options = [
            "Lodge a Claim",
            "Track Your Claim Status"
        ]
        options_html = '<div class="options">' + '<br>'.join([f'<a href="#" class="option-link" data-intent="{option.strip().lower().replace(" ", "_")}">{option}</a>' for option in options]) + '</div>'
        return response + '<br>' + options_html

    def no_match_intent(self, user_id, message):
        if self.user_state[user_id]['state'] == 'awaiting_follow_up' and any(word in message.lower() for word in self.affirmative_responses):
            return self.offer_options_intent(user_id, message)
        responses = ["I’m not sure how to help with that. Can you please clarify?",
                     "I didn't understand. Can you provide more details?",
                     "Sorry, I didn't get that. Could you please be more specific?",
                     "Please, tell me more so I can help more.",
                     "I see. Can you elaborate further on what you mean?",
                     "What do you hope to achieve with this?",
                     "What are your thoughts on this matter?",
                     "Can you provide further information?",
                     "Could you share your perspective on this matter?",
                     "Could you expand on that a bit more?",
                     "Can you give me more context on this?"]
        return random.choice(responses)

    def end_conversation_intent(self, user_id, message):
        last_message = (
            "Thank you for choosing our service! If you have any more questions, don't hesitate to reach out.<br>\n"
            "Have a wonderful day!<br>\n"
            "We'd love to hear your feedback. How would you rate our service on a scale of 1 to 5??<br>\n"
            "<div class='rating-options'>"
            "<button class='rating-btn' data-rating='1'>1 ⭐</button>"
            "<button class='rating-btn' data-rating='2'>2 ⭐</button>"
            "<button class='rating-btn' data-rating='3'>3 ⭐</button>"
            "<button class='rating-btn' data-rating='4'>4 ⭐</button>"
            "<button class='rating-btn' data-rating='5'>5 ⭐</button>"
            "</div>"
        )
        self.user_state[user_id]['state'] = 'awaiting_rating'
        return last_message

    def rating_intent(self, user_id, message):
        rating = re.search(r'(\d)\s?star', message).group(1)
        response = [f"Thank you for your {rating} star rating!\n"
                    "Type <strong>menu</strong> if you want to use other services."]
        self.user_state[user_id]['state'] = 'awaiting_follow_up'
        return response

bot = RuleBot()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get', methods=['POST'])
def get_bot_response():
    user_message = request.form['msg'].strip()
    user_id = request.remote_addr
    print(f"DEBUG: User message: {user_message}, User ID: {user_id}")
    response = bot.respond(user_id, user_message)
    print(f"DEBUG: Response: {response}")
    return jsonify({'response': response})

if __name__ == "__main__":
    app.run(debug=True)