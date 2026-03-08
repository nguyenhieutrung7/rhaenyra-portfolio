from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from datetime import datetime
import json
import os
import uuid
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rhaenyra-secret-key-2026'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Data storage
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
MESSAGES_FILE = DATA_DIR / "messages.json"
CONVERSATIONS_FILE = DATA_DIR / "conversations.json"

# Initialize files
if not MESSAGES_FILE.exists():
    MESSAGES_FILE.write_text("[]")
if not CONVERSATIONS_FILE.exists():
    CONVERSATIONS_FILE.write_text("{}")

# Admin token (simple auth)
# Admin token (simple auth)
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'admin-secret-token-2026')
ADMIN_NAME = os.environ.get('ADMIN_NAME', 'Admin')

# Track connected clients
connected_visitors = {}
connected_admin = None

# ============== Routes ==============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Get all messages (for admin)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    
    messages = json.loads(MESSAGES_FILE.read_text())
    return jsonify(messages)

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """Get all conversations (for admin)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conversations = json.loads(CONVERSATIONS_FILE.read_text())
    return jsonify(conversations)

# ============== WebSocket Events ==============

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    client_id = request.sid
    print(f'Client connected: {client_id}')
    emit('connected', {'client_id': client_id})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    client_id = request.sid
    
    # Remove from visitors
    if client_id in connected_visitors:
        del connected_visitors[client_id]
        print(f'Visitor disconnected: {client_id}')
    
    # Check if admin disconnected
    global connected_admin
    if connected_admin == client_id:
        connected_admin = None
        print(f'Admin disconnected: {client_id}')

@socketio.on('visitor_join')
def handle_visitor_join(data):
    """Visitor joins their room"""
    client_id = request.sid
    visitor_name = data.get('name', 'Anonymous')
    
    connected_visitors[client_id] = {
        'name': visitor_name,
        'joined_at': datetime.now().isoformat(),
        'room': client_id
    }
    
    join_room(client_id)
    print(f'Visitor joined: {visitor_name} ({client_id})')
    
    # Notify admin of new visitor
    if connected_admin:
        emit('visitor_joined', {
            'client_id': client_id,
            'name': visitor_name,
            'joined_at': connected_visitors[client_id]['joined_at']
        }, room=connected_admin)
    
    # Load previous messages for this visitor (if any)
    conversations = json.loads(CONVERSATIONS_FILE.read_text())
    if client_id in conversations:
        emit('previous_messages', conversations[client_id])
    else:
        # Welcome message
        emit('message', {
            'id': str(uuid.uuid4()),
            'from': ADMIN_NAME,
            'text': f"Hi {visitor_name}! 👋 Welcome! How can I help you today?",
            'timestamp': datetime.now().isoformat(),
            'is_me': False
        }, room=client_id)

@socketio.on('admin_join')
def handle_admin_join(data):
    """Admin joins admin room"""
    global connected_admin
    token = data.get('token', '')
    
    if token != ADMIN_TOKEN:
        emit('error', {'message': 'Invalid token'})
        return
    
    client_id = request.sid
    connected_admin = client_id
    join_room('admin')
    
    print(f'Admin connected: {client_id}')
    
    # Send current visitors list
    emit('visitors_list', list(connected_visitors.values()))
    
    # Send all conversations
    conversations = json.loads(CONVERSATIONS_FILE.read_text())
    emit('all_conversations', conversations)

@socketio.on('visitor_message')
def handle_visitor_message(data):
    """Handle message from visitor"""
    client_id = request.sid
    
    if client_id not in connected_visitors:
        emit('error', {'message': 'Not registered'})
        return
    
    visitor_name = connected_visitors[client_id]['name']
    message_text = data.get('text', '').strip()
    
    if not message_text:
        return
    
    message = {
        'id': str(uuid.uuid4()),
        'from': visitor_name,
        'text': message_text,
        'timestamp': datetime.now().isoformat(),
        'is_me': True,
        'client_id': client_id
    }
    
    # Save to conversation
    conversations = json.loads(CONVERSATIONS_FILE.read_text())
    if client_id not in conversations:
        conversations[client_id] = []
    conversations[client_id].append(message)
    CONVERSATIONS_FILE.write_text(json.dumps(conversations, indent=2))
    
    # Send to visitor
    emit('message', message, room=client_id)
    
    # Notify admin
    if connected_admin:
        emit('new_message', {
            **message,
            'room': client_id,
            'visitor_name': visitor_name
        }, room=connected_admin)
    
    print(f'Message from {visitor_name}: {message_text[:50]}...')

@socketio.on('admin_message')
def handle_admin_message(data):
    """Handle message from admin"""
    client_id = request.sid
    
    if client_id != connected_admin:
        emit('error', {'message': 'Not authorized'})
        return
    
    target_room = data.get('room')
    message_text = data.get('text', '').strip()
    
    if not target_room or not message_text:
        return
    
    message = {
        'id': str(uuid.uuid4()),
        'from': ADMIN_NAME,
        'text': message_text,
        'timestamp': datetime.now().isoformat(),
        'is_me': False
    }
    
    # Save to conversation
    conversations = json.loads(CONVERSATIONS_FILE.read_text())
    if target_room not in conversations:
        conversations[target_room] = []
    conversations[target_room].append(message)
    CONVERSATIONS_FILE.write_text(json.dumps(conversations, indent=2))
    
    # Send to visitor
    emit('message', message, room=target_room)
    
    # Confirm to admin
    emit('message_sent', {
        'room': target_room,
        'message': message
    })
    
    print(f'Admin replied to {target_room}: {message_text[:50]}...')

@socketio.on('admin_typing')
def handle_admin_typing(data):
    """Show typing indicator to visitor"""
    client_id = request.sid
    
    if client_id != connected_admin:
        return
    
    target_room = data.get('room')
    if target_room:
        emit('admin_typing', {'typing': True}, room=target_room)

@socketio.on('admin_stop_typing')
def handle_admin_stop_typing(data):
    """Hide typing indicator"""
    client_id = request.sid
    
    if client_id != connected_admin:
        return
    
    target_room = data.get('room')
    if target_room:
        emit('admin_typing', {'typing': False}, room=target_room)

@socketio.on('visitor_typing')
def handle_visitor_typing():
    """Notify admin that visitor is typing"""
    client_id = request.sid
    
    if client_id not in connected_visitors:
        return
    
    if connected_admin:
        emit('visitor_typing', {
            'room': client_id,
            'name': connected_visitors[client_id]['name']
        }, room=connected_admin)

if __name__ == '__main__':
    print("🦊 Rhaenyra Portfolio Chat Server")
    print("================================")
    print(f"Visitor page: http://localhost:3000")
    print(f"Admin panel: http://localhost:3000/admin")
    print(f"Admin token: {ADMIN_TOKEN}")
    print("================================")
    socketio.run(app, host='0.0.0.0', port=3000, debug=True)
