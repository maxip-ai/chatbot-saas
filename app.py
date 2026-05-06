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
CORS(app, origins="*")

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///saas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chatbotSaaSSecretKey2026SuperLong')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'chatbotSaaSJWTSecretKey2026SuperLong')
app.config['JWT_TOKEN_LOCATION'] = ['headers']
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'

db.init_app(app)
jwt = JWTManager(app)
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

with app.app_context():
    db.create_all()  # ✅ ΔΕΝ κάνουμε drop_all — διατηρούμε τα δεδομένα
    print("✅ Βάση δεδομένων έτοιμη!")


# ═══════════════════════════════
#  FRONTEND
# ═══════════════════════════════

@app.route('/')
def home():
    return render_template('index.html')


# ═══════════════════════════════
#  AUTH
# ═══════════════════════════════

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({'error': 'Συμπλήρωσε όλα τα πεδία'}), 400
    if Business.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Το email υπάρχει ήδη'}), 400
    business = Business(
        name=data['name'],
        email=data['email'],
        password=generate_password_hash(data['password']),
        business_type=data.get('business_type', ''),
        is_verified=True
    )
    db.session.add(business)
    db.session.commit()
    token = create_access_token(identity=str(business.id))
    return jsonify({'message': 'Επιτυχής εγγραφή!', 'token': token, 'name': business.name})


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Συμπλήρωσε email και κωδικό'}), 400
    business = Business.query.filter_by(email=data['email']).first()
    if not business or not check_password_hash(business.password, data['password']):
        return jsonify({'error': 'Λάθος email ή κωδικός'}), 401
    token = create_access_token(identity=str(business.id))
    return jsonify({'token': token, 'name': business.name})


# ═══════════════════════════════
#  CHATBOTS (CRUD)
# ═══════════════════════════════

@app.route('/chatbot/create', methods=['POST'])
@jwt_required()
def create_chatbot():
    business_id = int(get_jwt_identity())
    data = request.json
    if not data or not data.get('name'):
        return jsonify({'error': 'Το όνομα είναι υποχρεωτικό'}), 400
    chatbot = Chatbot(
        business_id=business_id,
        name=data['name'],
        description=data.get('description', ''),
        training_data=data.get('training_data', '')
    )
    db.session.add(chatbot)
    db.session.commit()
    return jsonify({
        'message': 'Chatbot δημιουργήθηκε!',
        'id': chatbot.id,
        'name': chatbot.name,
        'description': chatbot.description,
        'training_data': chatbot.training_data
    }), 201


@app.route('/chatbot/list', methods=['GET'])
@jwt_required()
def list_chatbots():
    business_id = int(get_jwt_identity())
    chatbots = Chatbot.query.filter_by(business_id=business_id).order_by(Chatbot.created_at.desc()).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'description': c.description,
        'training_data': c.training_data,
        'created_at': c.created_at.strftime('%d/%m/%Y %H:%M')
    } for c in chatbots])


@app.route('/chatbot/update/<int:chatbot_id>', methods=['PUT'])
@jwt_required()
def update_chatbot(chatbot_id):
    business_id = int(get_jwt_identity())
    chatbot = Chatbot.query.filter_by(id=chatbot_id, business_id=business_id).first_or_404()
    data = request.json
    chatbot.name = data.get('name', chatbot.name)
    chatbot.description = data.get('description', chatbot.description)
    chatbot.training_data = data.get('training_data', chatbot.training_data)
    db.session.commit()
    return jsonify({'message': 'Ενημερώθηκε!', 'id': chatbot.id})


@app.route('/chatbot/delete/<int:chatbot_id>', methods=['DELETE'])
@jwt_required()
def delete_chatbot(chatbot_id):
    business_id = int(get_jwt_identity())
    chatbot = Chatbot.query.filter_by(id=chatbot_id, business_id=business_id).first_or_404()
    for conv in chatbot.conversations:
        for msg in conv.messages:
            db.session.delete(msg)
        db.session.delete(conv)
    db.session.delete(chatbot)
    db.session.commit()
    return jsonify({'message': 'Διαγράφηκε!'})


# ═══════════════════════════════
#  CHAT (public — for widgets)
# ═══════════════════════════════

@app.route('/chat/<int:chatbot_id>', methods=['POST'])
def chat(chatbot_id):
    chatbot = Chatbot.query.get_or_404(chatbot_id)
    data = request.json
    if not data or not data.get('message'):
        return jsonify({'error': 'Δεν υπάρχει μήνυμα'}), 400

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": f"""Είσαι ο AI βοηθός της επιχείρησης '{chatbot.name}'.
{chatbot.description}

Πληροφορίες επιχείρησης:
{chatbot.training_data}

ΚΑΝΟΝΕΣ:
- Απάντα ΜΟΝΟ στα ελληνικά
- Χρησιμοποίησε ΜΟΝΟ ελληνικούς και λατινικούς χαρακτήρες
- Αν δεν ξέρεις κάτι: 'Επικοινωνήστε μαζί μας για περισσότερες πληροφορίες'
- Βάσισε τις απαντήσεις ΜΟΝΟ στις πληροφορίες που έχεις
- Να είσαι φιλικός και επαγγελματικός"""
                },
                {"role": "user", "content": data['message']}
            ],
            max_tokens=600
        )
        reply = response.choices[0].message.content
        return jsonify({'response': reply})
    except Exception as e:
        print(f"Groq error: {e}")
        return jsonify({'response': 'Παρουσιάστηκε σφάλμα. Δοκιμάστε ξανά.'}), 500


# ═══════════════════════════════
#  WIDGET (embed script)
# ═══════════════════════════════

@app.route('/widget/<int:chatbot_id>')
def widget(chatbot_id):
    chatbot = Chatbot.query.get_or_404(chatbot_id)
    base_url = request.host_url.rstrip('/')
    return f"""(function(){{
var BASE='{base_url}',ID={chatbot_id};
var btn=document.createElement('div');
btn.innerHTML='💬';
btn.style='position:fixed;bottom:22px;right:22px;width:56px;height:56px;background:linear-gradient(135deg,#5B4CFF,#00D4AA);border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:23px;z-index:99999;box-shadow:0 6px 24px rgba(91,76,255,0.5);transition:transform .3s';
btn.onmouseover=function(){{this.style.transform='scale(1.1)'}};
btn.onmouseout=function(){{this.style.transform='scale(1)'}};
var box=document.createElement('div');
box.style='display:none;position:fixed;bottom:88px;right:22px;width:340px;height:490px;background:#0A0A1A;border-radius:20px;z-index:99999;border:1px solid rgba(91,76,255,0.25);flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,0.6);font-family:system-ui,sans-serif;overflow:hidden';
box.innerHTML=`<div style="padding:14px 16px;background:linear-gradient(135deg,rgba(91,76,255,0.2),rgba(0,212,170,0.1));border-bottom:1px solid rgba(255,255,255,0.07);display:flex;justify-content:space-between;align-items:center"><div style="display:flex;align-items:center;gap:10px"><div style="width:32px;height:32px;background:linear-gradient(135deg,#5B4CFF,#00D4AA);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:15px">🤖</div><div><div style="font-size:14px;font-weight:600;color:#EEF0FF">{chatbot.name}</div><div style="font-size:10px;color:#10B981;font-weight:600">● Online</div></div></div><span id="wx-close" style="color:#555;cursor:pointer;font-size:18px;line-height:1">✕</span></div><div id="wx-msgs" style="flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:9px"></div><div style="padding:10px;border-top:1px solid rgba(255,255,255,0.06);display:flex;gap:8px"><input id="wx-inp" placeholder="Γράψτε μήνυμα..." style="flex:1;background:rgba(255,255,255,0.05);border:1px solid rgba(91,76,255,0.2);border-radius:8px;padding:9px 13px;color:#EEF0FF;font-size:13px;outline:none"/><button id="wx-snd" style="background:linear-gradient(135deg,#5B4CFF,#00D4AA);border:none;color:#fff;width:36px;height:36px;border-radius:8px;cursor:pointer;font-size:14px">➤</button></div>`;
document.body.appendChild(btn);document.body.appendChild(box);
btn.onclick=function(){{box.style.display=box.style.display==='none'?'flex':'none'}};
document.getElementById('wx-close').onclick=function(){{box.style.display='none'}};
var msgs=document.getElementById('wx-msgs');
function addM(t,u){{var d=document.createElement('div');d.style='padding:9px 13px;border-radius:12px;font-size:13px;line-height:1.5;max-width:82%;'+(u?'background:linear-gradient(135deg,#5B4CFF,#00D4AA);color:#fff;align-self:flex-end;border-radius:12px 4px 12px 12px':'background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.07);color:#94A3B8;align-self:flex-start;border-radius:4px 12px 12px 12px');d.textContent=t;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d}}
addM('Γεια σας! 👋 Πώς μπορώ να σας βοηθήσω;',false);
async function send(){{var i=document.getElementById('wx-inp'),t=i.value.trim();if(!t)return;i.value='';addM(t,true);var b=addM('⏳',false);try{{var r=await fetch(BASE+'/chat/'+ID,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:t}})}});var d=await r.json();b.textContent=d.response}}catch(e){{b.textContent='Παρουσιάστηκε σφάλμα. Δοκιμάστε αργότερα.'}}}}
document.getElementById('wx-snd').onclick=send;
document.getElementById('wx-inp').addEventListener('keypress',function(e){{if(e.key==='Enter')send()}});
}})();""", 200, {'Content-Type': 'application/javascript'}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)