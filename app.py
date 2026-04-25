from flask import Flask, request, jsonify, render_template
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from groq import Groq
from models import db, Business, Chatbot, Conversation, Message
from dotenv import load_dotenv
import os
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///saas.db'
app.config['SECRET_KEY'] = 'chatbotSaaSSecretKey2026SuperLong'
app.config['JWT_SECRET_KEY'] = 'chatbotSaaSJWTSecretKey2026SuperLong'
app.config['JWT_TOKEN_LOCATION'] = ['headers']
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'

db.init_app(app)
jwt = JWTManager(app)
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if Business.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Το email υπάρχει ήδη'}), 400
    business = Business(
        name=data['name'],
        email=data['email'],
        password=generate_password_hash(data['password']),
        business_type=data.get('business_type', '')
    )
    db.session.add(business)
    db.session.commit()
    return jsonify({'message': 'Επιτυχής εγγραφή!'})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    business = Business.query.filter_by(email=data['email']).first()
    if not business or not check_password_hash(business.password, data['password']):
        return jsonify({'error': 'Λάθος email ή κωδικός'}), 401
    token = create_access_token(identity=str(business.id))
    return jsonify({'token': token, 'name': business.name})

@app.route('/chatbot/create', methods=['POST'])
@jwt_required()
def create_chatbot():
    business_id = int(get_jwt_identity())
    data = request.json
    chatbot = Chatbot(
        business_id=business_id,
        name=data['name'],
        description=data.get('description', ''),
        training_data=data.get('training_data', '')
    )
    db.session.add(chatbot)
    db.session.commit()
    return jsonify({'message': 'Chatbot δημιουργήθηκε!', 'id': chatbot.id})

@app.route('/chatbot/list', methods=['GET'])
@jwt_required()
def list_chatbots():
    business_id = int(get_jwt_identity())
    chatbots = Chatbot.query.filter_by(business_id=business_id).all()
    return jsonify([{'id': c.id, 'name': c.name, 'description': c.description} for c in chatbots])

@app.route('/chat/<int:chatbot_id>', methods=['POST'])
def chat(chatbot_id):
    chatbot = Chatbot.query.get_or_404(chatbot_id)
    data = request.json

    conv = Conversation(chatbot_id=chatbot_id)
    db.session.add(conv)
    db.session.commit()

    response = client.chat.completions.create(
  model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": f"""You are the AI assistant of '{chatbot.name}'.
{chatbot.description}

Business information:
{chatbot.training_data}

CRITICAL RULES:
- Answer ONLY in Greek language. Never use any other language.
- Never use English, Vietnamese, French or any other language.
- Only Greek alphabet and words.
- Base answers only on the business information above.
- If you don't know something, say 'Επικοινωνήστε μαζί μας για περισσότερες πληροφορίες'."""
            },
            {"role": "user", "content": data['message']}
        ]
    )

    ai_text = response.choices[0].message.content
    return jsonify({'response': ai_text})
@app.route('/widget/<int:chatbot_id>')
def widget(chatbot_id):
    chatbot = Chatbot.query.get_or_404(chatbot_id)
    return f"""
    <script>
    (function() {{
        var chatbotId = {chatbot_id};
        var btn = document.createElement('div');
        btn.innerHTML = '💬';
        btn.style = 'position:fixed;bottom:20px;right:20px;width:55px;height:55px;background:#a78bfa;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:24px;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,0.3);';
        
        var chat = document.createElement('div');
        chat.style = 'display:none;position:fixed;bottom:85px;right:20px;width:350px;height:500px;background:#1a1a2e;border-radius:16px;z-index:9999;border:1px solid #333;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,0.4);';
        chat.innerHTML = `
            <div style="padding:15px;border-bottom:1px solid #333;display:flex;justify-content:space-between;align-items:center;">
                <span style="color:#a78bfa;font-weight:bold;">🤖 {chatbot.name}</span>
                <span id="close-chat" style="color:#888;cursor:pointer;font-size:18px;">✕</span>
            </div>
            <div id="chat-msgs" style="flex:1;overflow-y:auto;padding:15px;display:flex;flex-direction:column;gap:10px;"></div>
            <div style="padding:12px;border-top:1px solid #333;display:flex;gap:8px;">
                <input id="chat-inp" placeholder="Γράψε μήνυμα..." style="flex:1;padding:10px;border:1px solid #333;border-radius:8px;background:#0f0f1a;color:#fff;font-size:14px;outline:none;" />
                <button id="chat-send" style="background:#a78bfa;border:none;color:#fff;padding:10px 14px;border-radius:8px;cursor:pointer;">➤</button>
            </div>
        `;
        
        document.body.appendChild(btn);
        document.body.appendChild(chat);
        
        btn.onclick = function() {{
            chat.style.display = chat.style.display === 'none' ? 'flex' : 'none';
        }};
        
        document.getElementById('close-chat').onclick = function() {{
            chat.style.display = 'none';
        }};
        
        async function sendMsg() {{
            var inp = document.getElementById('chat-inp');
            var msgs = document.getElementById('chat-msgs');
            var text = inp.value.trim();
            if (!text) return;
            inp.value = '';
            
            var userDiv = document.createElement('div');
            userDiv.style = 'background:#a78bfa;color:#fff;padding:10px 14px;border-radius:10px;align-self:flex-end;max-width:75%;font-size:14px;';
            userDiv.textContent = text;
            msgs.appendChild(userDiv);
            
            var aiDiv = document.createElement('div');
            aiDiv.style = 'background:#0f0f1a;color:#fff;padding:10px 14px;border-radius:10px;align-self:flex-start;max-width:75%;font-size:14px;border:1px solid #333;';
            aiDiv.textContent = '⏳...';
            msgs.appendChild(aiDiv);
            msgs.scrollTop = msgs.scrollHeight;
            
            var res = await fetch('http://127.0.0.1:5000/chat/' + chatbotId, {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{message: text}})
            }});
            var data = await res.json();
            aiDiv.textContent = data.response;
            msgs.scrollTop = msgs.scrollHeight;
        }}
        
        document.getElementById('chat-send').onclick = sendMsg;
        document.getElementById('chat-inp').addEventListener('keypress', function(e) {{
            if (e.key === 'Enter') sendMsg();
        }});
    }})();
    </script>
    """
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Βάση δεδομένων έτοιμη!")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)